import re
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, SelectField, DecimalField, TextAreaField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from flask_wtf.file import MultipleFileField, FileAllowed

def validate_password_strength(password):
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if not re.search(r'[A-Z]', password):
        raise ValidationError("Password must contain an uppercase letter.")
    if not re.search(r'[a-z]', password):
        raise ValidationError("Password must contain a lowercase letter.")
    if not re.search(r'\d', password):
        raise ValidationError("Password must contain a digit.")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError("Password must contain a special character.")

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class CreateHallForm(FlaskForm):
    name = StringField('Hall Name', validators=[DataRequired(), Length(min=2, max=100)])
    slug = StringField('Hall Slug', validators=[DataRequired(), Length(min=2, max=100)])
    morning_description = TextAreaField('Morning Description', validators=[DataRequired()])
    evening_description = TextAreaField('Evening Description', validators=[DataRequired()])
    morning_highlights = TextAreaField('Morning Highlights (comma separated)', validators=[DataRequired()])
    evening_highlights = TextAreaField('Evening Highlights (comma separated)', validators=[DataRequired()])
    morning_discount = TextAreaField('Morning Discount Info', validators=[DataRequired()])
    evening_discount = TextAreaField('Evening Discount Info', validators=[DataRequired()])
    morning_pricing = TextAreaField('Morning Pricing', validators=[DataRequired()])  # Hidden field filled by JS
    evening_pricing = TextAreaField('Evening Pricing', validators=[DataRequired()])  # Hidden field filled by JS
    instructions = TextAreaField('Instructions (displayed after booking)', validators=[DataRequired()])
    phone = StringField('Contact Phone', validators=[DataRequired()])
    email = StringField('Contact Email', validators=[DataRequired()])
    latitude = DecimalField('Latitude', validators=[DataRequired()])
    longitude = DecimalField('Longitude', validators=[DataRequired()])
    pictures = MultipleFileField('Upload Pictures (max 6)', validators=[FileAllowed(['jpg','jpeg','png','gif'], 'Images only!')])
    submit = SubmitField('Create Hall')

class EditHallForm(FlaskForm):
    name = StringField('Hall Name', validators=[DataRequired(), Length(min=2, max=100)])
    slug = StringField('Hall Slug', validators=[DataRequired(), Length(min=2, max=100)])
    morning_description = TextAreaField('Morning Description', validators=[DataRequired()])
    evening_description = TextAreaField('Evening Description', validators=[DataRequired()])
    morning_highlights = TextAreaField('Morning Highlights (comma separated)', validators=[DataRequired()])
    evening_highlights = TextAreaField('Evening Highlights (comma separated)', validators=[DataRequired()])
    morning_discount = TextAreaField('Morning Discount Info', validators=[DataRequired()])
    evening_discount = TextAreaField('Evening Discount Info', validators=[DataRequired()])
    morning_pricing = TextAreaField('Morning Pricing', validators=[DataRequired()])  # Hidden field filled by JS
    evening_pricing = TextAreaField('Evening Pricing', validators=[DataRequired()])
    instructions = TextAreaField('Instructions (displayed after booking)', validators=[DataRequired()])
    phone = StringField('Contact Phone', validators=[DataRequired()])
    email = StringField('Contact Email', validators=[DataRequired()])
    latitude = DecimalField('Latitude', validators=[DataRequired()])
    longitude = DecimalField('Longitude', validators=[DataRequired()])
    pictures = MultipleFileField('Upload New Pictures (optional, max 6)', validators=[FileAllowed(['jpg','jpeg','png','gif'], 'Images only!')])
    submit = SubmitField('Save Changes')

class BookingForm(FlaskForm):
    booking_date = DateField('Booking Date (YYYY-MM-DD)', format='%Y-%m-%d', validators=[DataRequired()])
    time_slot = SelectField('Time Slot', choices=[('morning','Morning'), ('evening','Evening')], validators=[DataRequired()])
    user_name = StringField('Your Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone_number = StringField('Phone Number (confirmation)')
    id_number = StringField('ID Number (confirmation)')
    submit = SubmitField('Submit Booking')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Old Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_new_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')
    
    def validate_new_password(self, new_password):
        validate_password_strength(new_password.data)
