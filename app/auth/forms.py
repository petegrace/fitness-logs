from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, PasswordField, SubmitField, HiddenField, BooleanField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from app.models import User

class LoginForm(FlaskForm):
	email = StringField("Email", validators=[DataRequired()])
	password = PasswordField("Password", validators=[DataRequired()])
	submit = SubmitField("Sign In")

class RegisterForm(FlaskForm):
	google_email = HiddenField("google_email")
	consent_privacy = BooleanField("I consent for Training Ticks to store and process my data as per the Privacy Policy.", validators=[DataRequired("You must consent to our Privacy Policy in order to register.")])
	opt_in_to_marketing_emails = BooleanField("(Optional) I'd like to receive occasional updates from Training Ticks to tell me about new features being released or in development that might help me out with my training.")
	submit = SubmitField("Complete Registration")

class ResetPasswordForm(FlaskForm):
	password = PasswordField("New Password", validators=[DataRequired()])
	password2 = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("password")])
	submit = SubmitField("Set Password")

class PreferencesForm(FlaskForm):
	opt_in_to_marketing_emails = BooleanField("Subscribe to email updates.")
	enable_flexible_planning = SelectField('Enable Flexible Planning?', choices=[("false", "No thanks, I'll plan my activity for specific days"), ("true", "Yes please, let me plan activities to do on any day during the week")])
	submit = SubmitField("Save Changes")