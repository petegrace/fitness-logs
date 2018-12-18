from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, PasswordField, SubmitField, HiddenField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from app.models import User

class LoginForm(FlaskForm):
	email = StringField("Email", validators=[DataRequired()])
	password = PasswordField("Password", validators=[DataRequired()])
	submit = SubmitField("Sign In")


class RegisterForm(FlaskForm):
	google_email = HiddenField("google_email")
	consent_privacy = BooleanField("I consent for Training Ticks to store and process my data as per the Privacy Policy.", validators=[DataRequired("You must consent to our Privacy Policy in order to register.")])
	submit = SubmitField("Complete Registration")