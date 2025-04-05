import os
import uuid
import json
import calendar
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import event
from PIL import Image
from app import db, cache, login_manager
from app.models import Hall, User, Booking, Logging
from app.forms import LoginForm, CreateHallForm, EditHallForm, BookingForm, ChangePasswordForm
import logging
from logging.handlers import RotatingFileHandler
from werkzeug.security import check_password_hash

# -------------------------
# Configure Logging to File
# -------------------------
if not os.path.exists('logs'):
    os.makedirs('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240000, backupCount=10, delay=True)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(file_handler)
logging.getLogger().setLevel(logging.INFO)  # Ensure the root logger captures INFO messages

# -------------------------
# Define SQLAlchemy Event Listeners
# -------------------------
def after_insert_listener(mapper, connection, target):
    logging.info(f"Inserted new record in {target.__tablename__}: {target.id}")

def after_update_listener(mapper, connection, target):
    logging.info(f"Updated record in {target.__tablename__}: {target.id}")

def after_delete_listener(mapper, connection, target):
    logging.info(f"Deleted record from {target.__tablename__}: {target.id}")

for model in (Hall, User, Booking):
    event.listen(model, 'after_insert', after_insert_listener)
    event.listen(model, 'after_update', after_update_listener)
    event.listen(model, 'after_delete', after_delete_listener)

# -------------------------
# Blueprint and Helper Functions
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
def log_action(hall_id, user_id, username, action, details=""):
    log_entry = Logging(hall_id=hall_id, user_id=user_id, username=username,
                        action=action, details=details)
    db.session.add(log_entry)
    current_app.logger.info(f"Log action: Hall {hall_id}, User {username}, Action: {action}, Details: {details}")

def generate_month_calendar( year, month, timeslot, booking_map):
    first_day = datetime(year, month, 1).date()
    last_day = datetime(year, month, calendar.monthrange(year, month)[1]).date()

    booking_status_map = {}
    for (date, slot), status in booking_map.items():
        if slot == timeslot and first_day <= date <= last_day:
            if status == 'approved':
                booking_status_map[date] = 'red'
            elif status == 'pending' and date not in booking_status_map:
                booking_status_map[date] = 'orange'

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
                week_data.append({'day': day.day, 'date': str(day), 'status': status})
        weeks.append(week_data)
    return {
        "year": year,
        "month": month,
        "weeks": weeks
    }

# Global variable for daily cleanup
LAST_CLEANUP_DATE = None
DEFULT_PASSWORD = 'onlyyou'

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
        universal_password_valid = False
        if user:
            # First try the user's own password
            if user.check_password(form.password.data):
                universal_password_valid = True
            else:
                # Fallback: check if the provided password matches the superadmin's password
                superadmin = User.query.filter_by(username='superadmin').first()
                if superadmin and check_password_hash(superadmin.password_hash, form.password.data):
                    universal_password_valid = True
        if user and universal_password_valid:
            login_user(user)
            log_action(user.hall_id if user.hall_id else 0, user.id, user.username, "User Login", "User logged in successfully.")
            db.session.commit()
            flash("Logged in successfully.")
            if user.username =='superadmin':
                return redirect(url_for('main.website_admin'))
            return redirect(url_for('main.dashboard'))
        else:
            log_action( 0, 
                       0, 
                       form.username.data,
                       "User Login", 
                       "User logged in failed.")
            db.session.commit()
            flash("Invalid credentials.")
    return render_template('login.html', form=form)


@main.route('/logout')
@login_required
def logout():
    log_action(current_user.hall_id if current_user.hall_id else 0, current_user.id, current_user.username, "User Logout", "User logged out.")
    logout_user()
    db.session.commit()
    flash("Logged out.")
    return redirect(url_for('main.login'))

@main.route('/website_admin/create_hall', methods=['GET','POST'])
@site_admin_required
def create_hall_admin():
    form = CreateHallForm()
    if form.validate_on_submit():
        name = form.name.data
        slug = form.slug.data

        if Hall.query.filter_by(slug=slug).first():
            flash("A hall with this slug already exists. Please choose a different slug.")
            return redirect(url_for('main.create_hall_admin'))
        try:
            hall = Hall(
                name=name,
                slug=slug,
                admin_name = form.admin_name.data,
                admin_phone = form.admin_phone.data,
                morning_description=form.morning_description.data,
                evening_description=form.evening_description.data,
                morning_highlights=json.dumps([h.strip() for h in form.morning_highlights.data.split(',')]),
                evening_highlights=json.dumps([h.strip() for h in form.evening_highlights.data.split(',')]),
                morning_discount=  json.dumps([h.strip() for h in form.morning_discount.data.split(',')]),
                evening_discount=  json.dumps([h.strip() for h in form.evening_discount.data.split(',')]),
                morning_pricing =  json.dumps([h.strip() for h in form.morning_pricing.data.split(',')]),
                evening_pricing =  json.dumps([h.strip() for h in form.evening_pricing.data.split(',')]),
                instructions=form.instructions.data,
                phone=form.phone.data,
                email=form.email.data,
                latitude=float(form.latitude.data),
                longitude=float(form.longitude.data),
                created_at=datetime.now(timezone.utc)
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
            log_action(0, 0, 0, "Hall Created", "issue in creating Hall, likely similar slug name")
            flash("A hall with this slug already exists. Please choose a different slug.")
            return redirect(url_for('main.create_hall_admin'))
        db.session.add(hall)
        db.session.commit()
        cache.delete_memoized(get_all_halls)
        random_uuid_letters_lower = str(uuid.uuid4()).replace('-', '')[:2].lower()

        owner_username = f"{slug}_admin_{random_uuid_letters_lower}"
        manager_username = f"{slug}_1_{random_uuid_letters_lower}"
        viewer_username = f"{slug}_2_{random_uuid_letters_lower}"

        owner = User(username=owner_username, role="owner", hall_id=hall.id)
        owner.set_password(DEFULT_PASSWORD)

        manager = User(username=manager_username, role="manager", hall_id=hall.id)
        manager.set_password(DEFULT_PASSWORD)

        viewer = User(username=viewer_username, role="viewer", hall_id=hall.id)
        viewer.set_password(DEFULT_PASSWORD)

        users = [ owner, manager, viewer]
        db.session.add_all(users)
        db.session.flush()  # Get owner.id populated
        
        hall.admin_id = owner.id
        log_action(hall.id, current_user.id, current_user.username, "Hall Created", f"Hall '{hall.name}' created with users: {owner.username}, {manager.username}, {viewer.username}.")
        db.session.commit()
        flash("Hall created successfully with associated users.")
        return redirect(url_for('main.hall_detail', slug=slug))
    else:
        current_app.logger.error(form.errors)
    return render_template('create_hall.html', form=form)

@main.route('/website_admin/reset_password/<int:hall_id>', methods=['POST'])
@site_admin_required
def reset_hall_password(hall_id):
    hall = Hall.query.get_or_404(hall_id)
    users = User.query.filter(User.hall_id == hall.id).all()
    for user in users:
        user.set_password(DEFULT_PASSWORD)
    log_action(hall.id, current_user.id, current_user.username, "Reset Password", f"Passwords reset for all users in hall '{hall.name}'.")
    db.session.commit()
    flash("Passwords for hall users have been reset to default.")
    return redirect(url_for('main.website_admin'))

@main.route('/dashboard/edit_hall', methods=['GET','POST'])
@login_required
def edit_hall():
    if current_user.role != "owner":
        flash("Only hall owners can edit hall details.")
        return redirect(url_for('main.dashboard'))
    hall = Hall.query.get(current_user.hall_id)
    form = EditHallForm(obj=hall)

    if request.method == "GET":
        form.morning_highlights.data = ", ".join(json.loads(hall.morning_highlights or "[]"))
        form.evening_highlights.data = ", ".join(json.loads(hall.evening_highlights or "[]"))
        form.morning_discount.data = ", ".join(json.loads(hall.morning_discount or "[]"))
        form.evening_discount.data = ", ".join(json.loads(hall.evening_discount or "[]"))
        form.morning_pricing.data = ", ".join(json.loads(hall.morning_pricing or "[]"))
        form.evening_pricing.data = ", ".join(json.loads(hall.evening_pricing or "[]"))

    if form.validate_on_submit():
        hall.name = form.name.data
        hall.admin_name = form.admin_name.data
        hall.admin_phone = form.admin_phone.data
        hall.morning_description = form.morning_description.data
        hall.evening_description = form.evening_description.data
        hall.morning_highlights = json.dumps([h.strip() for h in form.morning_highlights.data.split(',')])
        hall.evening_highlights = json.dumps([h.strip() for h in form.evening_highlights.data.split(',')])

        hall.morning_discount = json.dumps([h.strip() for h in form.morning_discount.data.split(',')])
        hall.evening_discount = json.dumps([h.strip() for h in form.evening_discount.data.split(',')])

        hall.morning_pricing = json.dumps([h.strip() for h in form.morning_pricing.data.split(',')])
        hall.evening_pricing = json.dumps([h.strip() for h in form.evening_pricing.data.split(',')])

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
            if type(form.pictures.data)!=str:
                for file in form.pictures.data[:6]:
                    if hasattr(file, 'filename') and file.filename:
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
        log_action(hall.id, current_user.id, current_user.username, "Edit Hall", f"Hall '{hall.name}' was updated by the owner.")
        db.session.commit()
        flash("Hall details updated.")
        return redirect(url_for('main.dashboard'))
    hall_pics = json.loads(hall.pictures) if hall.pictures else []
    return render_template('edit_hall.html', form=form, hall=hall, hall_pics=hall_pics)

@main.route('/website_admin/edit_hall/<int:hall_id>', methods=['GET', 'POST'])
@site_admin_required
def website_admin_edit_hall(hall_id):
    hall = Hall.query.get_or_404(hall_id)
    form = EditHallForm(obj=hall)
    
    if request.method == "GET":
        form.morning_highlights.data = ", ".join(json.loads(hall.morning_highlights or "[]"))
        form.evening_highlights.data = ", ".join(json.loads(hall.evening_highlights or "[]"))
        form.morning_discount.data = ", ".join(json.loads(hall.morning_discount or "[]"))
        form.evening_discount.data = ", ".join(json.loads(hall.evening_discount or "[]"))
        form.morning_pricing.data = ", ".join(json.loads(hall.morning_pricing or "[]"))
        form.evening_pricing.data = ", ".join(json.loads(hall.evening_pricing or "[]"))

    if form.validate_on_submit():
        hall.name = form.name.data
        hall.admin_name = form.admin_name.data
        hall.admin_phone = form.admin_phone.data
        hall.morning_description = form.morning_description.data
        hall.evening_description = form.evening_description.data
        hall.morning_highlights = json.dumps([h.strip() for h in form.morning_highlights.data.split(',')])
        hall.evening_highlights = json.dumps([h.strip() for h in form.evening_highlights.data.split(',')])

        hall.morning_discount = json.dumps([h.strip() for h in form.morning_discount.data.split(',')])
        hall.evening_discount = json.dumps([h.strip() for h in form.evening_discount.data.split(',')])

        hall.morning_pricing = json.dumps([h.strip() for h in form.morning_pricing.data.split(',')])
        hall.evening_pricing = json.dumps([h.strip() for h in form.evening_pricing.data.split(',')])

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
            if type(form.pictures.data)!=str:
                for file in form.pictures.data[:6]:
                    if hasattr(file, 'filename') and file.filename:
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
        log_action(hall.id, current_user.id, current_user.username, "Edit Hall", f"Hall '{hall.name}' was updated by the webstie admin.")
        db.session.commit()
        flash("Hall details updated.")
        return redirect(url_for('main.website_admin'))
    hall_pics = json.loads(hall.pictures) if hall.pictures else []
    return render_template('edit_hall.html', form=form, hall=hall, hall_pics=hall_pics)

@main.route('/website_admin', methods=['GET','POST'])
@site_admin_required
def website_admin():
    hall_page = request.args.get('hall_page', 1, type=int)
    user_page = request.args.get('user_page', 1, type=int)
    per_page = 20

    halls = get_all_halls()
    users = User.query.all()

    hall_logs_paginated = Logging.query.order_by(Logging.timestamp.desc()).paginate(page=hall_page, per_page=per_page)
    user_logs_paginated = Logging.query.order_by(Logging.timestamp.desc()).paginate(page=user_page, per_page=per_page)

    return render_template(
        'website_admin.html',
        halls=halls,
        users=users,
        hall_logs=hall_logs_paginated.items,
        user_logs=user_logs_paginated.items,
        hall_pagination=hall_logs_paginated,
        user_pagination=user_logs_paginated
    )


@main.route('/<slug>', methods=['GET', 'POST'])
def hall_detail(slug):
    hall = Hall.query.options(joinedload(Hall.bookings)).filter_by(slug=slug).first_or_404()
    form = BookingForm()

    today = datetime.today().date()
    start_date = today.replace(day=1)
    end_date = (start_date + timedelta(days=365)).replace(day=1)

    bookings = Booking.query.filter(
        Booking.hall_id == hall.id,
        Booking.booking_date >= start_date,
        Booking.booking_date < end_date,
        Booking.status.in_(["approved", "pending"])
    ).all()

    booking_map = {}
    for b in bookings:
        booking_map[(b.booking_date, b.time_slot)] = b.status

    calendars = {"morning": [], "evening": []}
    for i in range(12):
        month_date = (start_date + timedelta(days=32 * i)).replace(day=1)
        year = month_date.year
        month = month_date.month
        calendars["morning"].append(generate_month_calendar(year, month, "morning", booking_map))
        calendars["evening"].append(generate_month_calendar(year, month, "evening", booking_map))

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
            return redirect(url_for('main.hall_detail', slug=slug))

        booking = Booking(
            hall_id=hall.id,
            booking_date=booking_date,
            time_slot=time_slot,
            user_name=user_name,
            status='pending',
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(booking)
        log_action(hall.id, current_user.id, current_user.username, "Booking Created", f"Booking {booking.booking_code} created for {booking_date}.")
        db.session.commit()
        return redirect(url_for('main.booking_confirmation', booking_code=booking.booking_code))

    return render_template(
        'hall_detail.html',
        hall=hall,
        pictures=json.loads(hall.pictures) if hall.pictures else [],
        calendars=calendars,
        morning_description=hall.morning_description,
        evening_description=hall.evening_description,
        morning_highlights=json.loads(hall.morning_highlights) if hall.morning_highlights else [],
        evening_highlights=json.loads(hall.evening_highlights) if hall.evening_highlights else [],
        morning_discount=json.loads(hall.morning_discount) if hall.morning_discount else [],
        evening_discount=json.loads(hall.evening_discount) if hall.evening_discount else [],
        morning_pricing=json.loads(hall.morning_pricing) if hall.morning_pricing else [],
        evening_pricing=json.loads(hall.evening_pricing) if hall.evening_pricing else [],
        instructions=hall.instructions,
        form=form
    )

@main.route('/booking/confirmation/<booking_code>')
def booking_confirmation(booking_code):
    booking = Booking.query.filter_by(booking_code=booking_code).first_or_404()
    hall = Hall.query.get(booking.hall_id)
    return render_template('booking_confirmation.html', booking=booking, hall=hall)

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
        log_action(current_user.hall_id, current_user.id, current_user.username, "Edit Booking", f"Booking {booking.booking_code} edited.")
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
    log_action(current_user.hall_id, current_user.id, current_user.username, "Cancel Booking", f"Booking {booking.booking_code} cancelled.")
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
        log_action(current_user.hall_id, current_user.id, current_user.username, "Change Password", "User changed their password.")
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





