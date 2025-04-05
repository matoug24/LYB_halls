import uuid
from datetime import datetime, timezone
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class Hall(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    admin_name = db.Column(db.String(100), nullable=True)
    admin_phone = db.Column(db.String(20), nullable=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    morning_description = db.Column(db.Text, nullable=True)
    evening_description = db.Column(db.Text, nullable=True)
    morning_highlights = db.Column(db.Text, nullable=True)  # JSON list
    evening_highlights = db.Column(db.Text, nullable=True)  # JSON list
    morning_discount = db.Column(db.Text, nullable=True)
    evening_discount = db.Column(db.Text, nullable=True)
    morning_pricing = db.Column(db.Text, nullable=True)  
    evening_pricing = db.Column(db.Text, nullable=True)  
    instructions = db.Column(db.Text, nullable=True)
    pictures = db.Column(db.Text, nullable=True)  # JSON array of filenames
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    bookings = db.relationship('Booking', backref='hall', lazy=True)
    users = db.relationship('User', backref='hall', lazy=True, foreign_keys='User.hall_id')

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index =True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_site_admin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20))  # "owner", "manager", "viewer"
    hall_id = db.Column(db.Integer, db.ForeignKey('hall.id'), index = True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_code = db.Column(db.String(10), unique=True, nullable=False, default=lambda: str(uuid.uuid4()).replace('-', '')[:10])
    hall_id = db.Column(db.Integer, db.ForeignKey('hall.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)  # "morning" or "evening"
    status = db.Column(db.String(20), default='pending')    # "pending", "approved", "cancelled"
    user_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    phone_number = db.Column(db.String(20), nullable=True)
    id_number = db.Column(db.String(50), nullable=True)

class Logging(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hall_id = db.Column(db.Integer, db.ForeignKey('hall.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(50))
    action = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    details = db.Column(db.Text)
