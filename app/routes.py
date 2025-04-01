import os
import uuid
import json
import calendar
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from PIL import Image
from app import db, cache, login_manager
from app.models import Hall, User, Booking, Logging
from app.forms import LoginForm, CreateHallForm, EditHallForm, BookingForm, ChangePasswordForm

main = Blueprint('main', __name__)

# --- Custom Decorators ---
def site_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_site_admin:
            flash("Site admin access required.")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

def hall_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ["manager", "owner"]:
            flash("Manager or owner access required.")
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def log_action(hall_id, user, action, details=""):
    log_entry = Logging(hall_id=hall_id, user_id=user.id, username=user.username,
                        action=action, details=details)
    db.session.add(log_entry)
    current_app.logger.info(f"Log action: Hall {hall_id}, User {user.username}, Action: {action}, Details: {details}")

# def get_booking_status(hall, date, timeslot):
#     booking = Booking.query.filter_by(hall_id=hall.id, booking_date=date, time_slot=timeslot).first()
#     if booking:
#         if booking.status == 'approved':
#             return 'red'
#         elif booking.status == 'pending':
#             return 'orange'
#     return 'green'

def generate_month_calendar(hall, year, month, timeslot):
    # Determine first and last day of the month
    first_day = datetime(year, month, 1).date()
    last_day = datetime(year, month, calendar.monthrange(year, month)[1]).date()

    # Pre-fetch bookings for the month and timeslot
    bookings = Booking.query.filter(
        Booking.hall_id == hall.id,
        Booking.booking_date >= first_day,
        Booking.booking_date <= last_day,
        Booking.time_slot == timeslot
    ).all()
    booking_status_map = {}
    for booking in bookings:
        if booking.status == 'approved':
            booking_status_map[booking.booking_date] = 'red'
        elif booking.status == 'pending' and booking.booking_date not in booking_status_map:
            booking_status_map[booking.booking_date] = 'orange'

    # Pre-parse pricing data once
    if timeslot == 'morning':
        pricing_str = hall.morning_pricing
        price_key = 'morning_prices'
    else:
        pricing_str = hall.evening_pricing
        price_key = 'evening_prices'
    try:
        pricing_data = json.loads(pricing_str) if pricing_str else {}
    except Exception:
        pricing_data = {}

    # Build lookup for override prices
    override_lookup = {}
    for override in pricing_data.get("overrides", []):
        try:
            o_date = datetime.strptime(override["date"], "%Y-%m-%d").date()
            if "price" in override:
                override_lookup[o_date] = override["price"]
            elif "prices" in override:
                override_lookup[o_date] = override["prices"]
            elif timeslot == 'morning' and "morning_price" in override:
                override_lookup[o_date] = override["morning_price"]
            elif timeslot == 'evening' and "evening_price" in override:
                override_lookup[o_date] = override["evening_price"]
        except Exception:
            continue

    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdatescalendar(year, month)
    weeks = []
    for week in month_days:
        week_data = []
        for day in week:
            if day.month != month:
                week_data.append(None)
            else:
                status = booking_status_map.get(day, 'green')
                if day in override_lookup:
                    price = override_lookup[day]
                else:
                    price = "N/A"
                    for interval in pricing_data.get("intervals", []):
                        try:
                            start_date = datetime.strptime(interval["start_date"], "%Y-%m-%d").date()
                            end_date = datetime.strptime(interval["end_date"], "%Y-%m-%d").date()
                        except Exception:
                            continue
                        if start_date <= day <= end_date:
                            day_index = day.weekday()
                            if "prices" in interval:
                                prices_list = interval["prices"]
                            elif price_key in interval:
                                prices_list = interval[price_key]
                            else:
                                prices_list = []
                            if len(prices_list) == 7:
                                price = prices_list[day_index]
                            break
                week_data.append({'day': day.day, 'date': str(day), 'status': status, 'price': price})
        weeks.append(week_data)
    return {
        "year": year,
        "month": month,
        "weeks": weeks
    }

# Global variable for daily cleanup
LAST_CLEANUP_DATE = None

@main.before_app_request
def expire_pending_bookings():
    global LAST_CLEANUP_DATE
    today_date = datetime.now(timezone.utc).date()
    if LAST_CLEANUP_DATE != today_date:
        expired_count = Booking.query.filter(
            Booking.status == 'pending', 
            Booking.created_at < datetime.now(timezone.utc) - timedelta(days=1)
        ).update({"status": "cancelled"}, synchronize_session=False)
        db.session.commit()
        current_app.logger.info(f"Expired {expired_count} pending bookings on {today_date}")
        LAST_CLEANUP_DATE = today_date

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
    
# --- Routes ---
@cache.memoize()
def get_all_halls():
    return Hall.query.all()

@main.route('/')
def index():
    halls = get_all_halls()
    return render_template('index.html', halls=halls)

@main.route('/login', methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash("Logged in successfully.")
            if current_user.is_site_admin:
                return redirect(url_for('main.website_admin'))
            return redirect(url_for('main.dashboard'))
        else:
            flash("Invalid credentials.")
    return render_template('login.html', form=form)

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out.")
    return redirect(url_for('main.login'))

@main.route('/website_admin/create_hall', methods=['GET','POST'])
@site_admin_required
def create_hall_admin():
    form = CreateHallForm()
    if form.validate_on_submit():
        name = form.name.data
        slug = form.slug.data

        try:
            hall = Hall(
                name=name,
                slug=slug,
                morning_description=form.morning_description.data,
                evening_description=form.evening_description.data,
                morning_highlights=json.dumps([h.strip() for h in form.morning_highlights.data.split(',')]),
                evening_highlights=json.dumps([h.strip() for h in form.evening_highlights.data.split(',')]),
                morning_discount=form.morning_discount.data,
                evening_discount=form.evening_discount.data,
                morning_pricing=form.morning_pricing.data,
                evening_pricing=form.evening_pricing.data,
                instructions=form.instructions.data,
                phone=form.phone.data,
                email=form.email.data,
                latitude=float(form.latitude.data),
                longitude=float(form.longitude.data),
                created_at=datetime.utcnow()
            )
            picture_filenames = []
            if form.pictures.data:
                for file in form.pictures.data[:6]:
                    if file:
                        ext = file.filename.split('.')[-1]
                        unique_filename = f"{slug}_{uuid.uuid4().hex}.{ext}"
                        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                        image = Image.open(file)
                        image.thumbnail((10000, 400), Image.Resampling.LANCZOS)
                        image.save(filepath)
                        picture_filenames.append(unique_filename)
            hall.pictures = json.dumps(picture_filenames)
        except IntegrityError:
            db.session.rollback()
            flash("A hall with this slug already exists. Please choose a different slug.")
            return redirect(url_for('main.create_hall_admin'))
        db.session.add(hall)
        db.session.commit()
        cache.delete_memoized(get_all_halls)
        random_uuid_letters_lower = str(uuid.uuid4()).replace('-', '')[:2].lower()
        default_password = "Hall%-2000"
        owner_username = f"{slug}_admin{random_uuid_letters_lower}"
        manager_username = f"{slug}1{random_uuid_letters_lower}"
        viewer_username = f"{slug}2{random_uuid_letters_lower}"

        owner = User(username=owner_username, role="owner", hall_id=hall.id)
        owner.set_password(default_password)

        manager = User(username=manager_username, role="manager", hall_id=hall.id)
        manager.set_password(default_password)

        viewer = User(username=viewer_username, role="viewer", hall_id=hall.id)
        viewer.set_password(default_password)

        users = [ owner, manager, viewer]
        db.session.bulk_save_objects(users)
        db.session.commit()
        
        hall.admin_id = owner.id
        db.session.commit()

        log_action(hall.id, current_user, "Hall Created", f"Hall '{hall.name}' created with users: {owner.username}, {manager.username}, {viewer.username}.")
        db.session.commit()
        flash("Hall created successfully with associated users.")
        return redirect(url_for('main.hall_detail', slug=slug))
    else:
        current_app.logger.error(form.errors)
    return render_template('create_hall.html', form=form)

@main.route('/<slug>')
def hall_detail(slug):
    hall = Hall.query.options(joinedload(Hall.bookings)).filter_by(slug=slug).first_or_404()
    pictures = json.loads(hall.pictures) if hall.pictures else []
    today = datetime.today().date()
    calendars = {"morning": [], "evening": []}
    # Generate calendars for 12 months starting from the current month
    for i in range(12):
        month_date = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        year = month_date.year
        month = month_date.month
        calendars["morning"].append(generate_month_calendar(hall, year, month, "morning"))
        calendars["evening"].append(generate_month_calendar(hall, year, month, "evening"))
    morning_highlights = json.loads(hall.morning_highlights) if hall.morning_highlights else []
    evening_highlights = json.loads(hall.evening_highlights) if hall.evening_highlights else []
    return render_template('hall_detail.html', hall=hall, pictures=pictures,
                           calendars=calendars,
                           morning_description=hall.morning_description,
                           evening_description=hall.evening_description,
                           morning_highlights=morning_highlights,
                           evening_highlights=evening_highlights,
                           morning_discount=hall.morning_discount,
                           evening_discount=hall.evening_discount,
                           instructions=hall.instructions)

@main.route('/<slug>/book', methods=['GET','POST'])
def book_hall(slug):
    hall = Hall.query.filter_by(slug=slug).first_or_404()
    form = BookingForm()
    if form.validate_on_submit():
        booking_date = form.booking_date.data
        time_slot = form.time_slot.data
        user_name = form.user_name.data
        existing = db.session.query(Booking.id).filter(
            Booking.hall_id == hall.id,
            Booking.booking_date == booking_date,
            Booking.time_slot == time_slot,
            Booking.status.in_(["approved", "pending"])
        ).first()       
        if existing:
            flash("This slot is already booked.")
            return redirect(url_for('main.book_hall', slug=slug))
        booking = Booking(hall_id=hall.id, booking_date=booking_date, time_slot=time_slot,
                          user_name=user_name, status='pending', created_at=datetime.now(timezone.utc))
        db.session.add(booking)
        db.session.commit()
        return redirect(url_for('main.booking_confirmation', booking_code=booking.booking_code))
    return render_template('book_hall.html', hall=hall, form=form)

@main.route('/booking/confirmation/<booking_code>')
def booking_confirmation(booking_code):
    booking = Booking.query.filter_by(booking_code=booking_code).first_or_404()
    hall = Hall.query.get(booking.hall_id)
    return render_template('booking_confirmation.html', booking=booking, hall=hall)

@main.route('/website_admin', methods=['GET','POST'])
@site_admin_required
def website_admin():
    halls = get_all_halls()
    users = User.query.all()
    logs = Logging.query.order_by(Logging.timestamp.desc()).all()
    return render_template('website_admin.html', halls=halls, users=users, logs=logs)

@main.route('/dashboard')
@login_required
def dashboard():
    if current_user.hall_id is None:
        flash("You need to login with your account.")
        return redirect(url_for('main.login'))
    hall = Hall.query.get(current_user.hall_id)
    bookings = Booking.query.filter_by(hall_id=hall.id).order_by(Booking.booking_date).all()
    approved_bookings = [b for b in bookings if b.status == 'approved']
    pending_bookings = [b for b in bookings if b.status == 'pending']
    logs = Logging.query.filter_by(hall_id=hall.id).order_by(Logging.timestamp.desc()).all() if current_user.role=="owner" else []
    return render_template('dashboard.html', hall=hall,
                           approved_bookings=approved_bookings,
                           pending_bookings=pending_bookings,
                           logs=logs)

@main.route('/dashboard/edit_hall', methods=['GET','POST'])
@login_required
def edit_hall():
    if current_user.role != "owner":
        flash("Only hall owners can edit hall details.")
        return redirect(url_for('main.dashboard'))
    hall = Hall.query.get(current_user.hall_id)
    form = EditHallForm(obj=hall)
    if form.validate_on_submit():
        hall.name = form.name.data
        hall.slug = form.slug.data
        hall.morning_description = form.morning_description.data
        hall.evening_description = form.evening_description.data
        hall.morning_highlights = json.dumps([h.strip() for h in form.morning_highlights.data.split(',')])
        hall.evening_highlights = json.dumps([h.strip() for h in form.evening_highlights.data.split(',')])
        hall.morning_discount = form.morning_discount.data
        hall.evening_discount = form.evening_discount.data
        # If the pricing fields are left blank, retain the previous value.
        if form.morning_pricing.data.strip():
            hall.morning_pricing = form.morning_pricing.data
        if form.evening_pricing.data.strip():
            hall.evening_pricing = form.evening_pricing.data
        hall.instructions = form.instructions.data
        hall.phone = form.phone.data
        hall.email = form.email.data
        hall.latitude = float(form.latitude.data)
        hall.longitude = float(form.longitude.data)
        delete_pics = request.form.getlist("delete_pictures")
        picture_filenames = json.loads(hall.pictures) if hall.pictures else []
        if delete_pics:
            picture_filenames = [p for p in picture_filenames if p not in delete_pics]
            hall.pictures = json.dumps(picture_filenames)
        if form.pictures.data:
            for file in form.pictures.data[:6]:
                if file:
                    ext = file.filename.split('.')[-1]
                    unique_filename = f"{hall.slug}_{uuid.uuid4().hex}.{ext}"
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                    image = Image.open(file)
                    image.thumbnail((10000, 400), Image.Resampling.LANCZOS)
                    image.save(filepath)
                    picture_filenames.append(unique_filename)
            picture_filenames = picture_filenames[:6]
            hall.pictures = json.dumps(picture_filenames)
        db.session.commit()
        log_action(hall.id, current_user, "Edit Hall", f"Hall '{hall.name}' updated.")
        db.session.commit()
        flash("Hall details updated.")
        return redirect(url_for('main.dashboard'))
    return render_template('edit_hall.html', form=form, hall=hall)

@main.route('/booking/<int:booking_id>/edit', methods=['GET','POST'])
@login_required
@hall_manager_required
def edit_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.hall_id != current_user.hall_id:
        flash("Unauthorized action.")
        return redirect(url_for('main.dashboard'))
    form = BookingForm(obj=booking)
    if form.validate_on_submit():
        booking.booking_date = form.booking_date.data
        booking.time_slot = form.time_slot.data
        booking.user_name = form.user_name.data
        if form.phone_number.data:
            booking.phone_number = form.phone_number.data
        if form.id_number.data:
            booking.id_number = form.id_number.data
        action = request.form.get("action")
        if action == "approve":
            booking.status = 'approved'
        db.session.commit()
        log_action(current_user.hall_id, current_user, "Edit Booking", f"Booking {booking.booking_code} edited.")
        db.session.commit()
        flash("Booking updated.")
        return redirect(url_for('main.dashboard'))
    return render_template('edit_booking.html', form=form, booking=booking)

@main.route('/booking/<int:booking_id>/cancel')
@login_required
@hall_manager_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.hall_id != current_user.hall_id:
        flash("Unauthorized action.")
        return redirect(url_for('main.dashboard'))
    booking.status = 'cancelled'
    db.session.commit()
    log_action(current_user.hall_id, current_user, "Cancel Booking", f"Booking {booking.booking_code} cancelled.")
    db.session.commit()
    flash("Booking cancelled.")
    return redirect(url_for('main.dashboard'))

@main.route('/change_password', methods=['GET','POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.old_password.data):
            flash("Old password is incorrect.")
            return redirect(url_for('main.change_password'))
        current_user.set_password(form.new_password.data)
        db.session.commit()
        log_action(current_user.hall_id, current_user, "Change Password", "User changed their password.")
        db.session.commit()
        flash("Password changed successfully.")
        return redirect(url_for('main.dashboard'))
    return render_template('change_password.html', form=form)

@main.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@main.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403
