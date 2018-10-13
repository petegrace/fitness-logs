from datetime import datetime
from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, PasswordField, DateTimeField, SelectField, IntegerField, SubmitField, HiddenField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from app.models import User, ExerciseType


class LogNewExerciseTypeForm(FlaskForm):
	name = StringField("Exercise Name", validators=[DataRequired(), Length(min=1, max=100)])
	# measured_by will be hardcoded to reps for now

	# fields for the first exercise to be logged (reps will also serve as the default)
	exercise_datetime = DateTimeField("Exercise Date & Time (UTC)", format="%Y-%m-%d %H:%M:%S",
										validators=[DataRequired()], default=datetime.utcnow)
	measured_by = SelectField('Measured By', choices=[('reps', 'Reps'), ('seconds', 'Time (seconds)')])
	reps = IntegerField("Reps", validators=[Optional()])
	seconds = IntegerField("Seconds", validators=[Optional()])
	submit = SubmitField("Log Exercise")

	def validate_name(self, name):
		exercise_type = ExerciseType.query.filter_by(name=name.data).filter_by(owner=current_user).first()
		if exercise_type is not None:
			raise ValidationError("You already have an Exercise Type with that name.")


class ScheduleNewExerciseTypeForm(FlaskForm):
	name = StringField("Exercise Name", validators=[DataRequired(), Length(min=1, max=100)])
	# measured_by will be hardcoded to reps for now

	# fields for the scheduled exercise (reps will also serve as the default)
	measured_by = SelectField('Measured By', choices=[('reps', 'Reps'), ('seconds', 'Time (seconds)')])
	reps = IntegerField("Reps", validators=[Optional()])
	seconds = IntegerField("Seconds", validators=[Optional()])
	submit = SubmitField("Schedule Exercise")

	def validate_name(self, name):
		exercise_type = ExerciseType.query.filter_by(name=name.data).filter_by(owner=current_user).first()
		if exercise_type is not None:
			raise ValidationError("You already have an Exercise Type with that name.")

		
class EditExerciseForm(FlaskForm):
	# fields for the first exercise to be logged (reps will also serve as the default)
	exercise_datetime = DateTimeField("Exercise Date & Time (UTC)", format="%Y-%m-%d %H:%M:%S",
										validators=[DataRequired()], default=datetime.utcnow)
	measured_by = HiddenField("measured_by")
	reps = IntegerField("Reps", validators=[Optional()])
	seconds = IntegerField("Seconds", validators=[Optional()])
	update_default = BooleanField("Update default?")
	submit = SubmitField("Update Exercise")

		
class EditScheduledExerciseForm(FlaskForm):
	# fields for the first exercise to be logged (reps will also serve as the default)
	sets = IntegerField("Sets", validators=[DataRequired()])
	measured_by = HiddenField("measured_by")
	reps = IntegerField("Reps", validators=[Optional()])
	seconds = IntegerField("Seconds", validators=[Optional()])
	update_default = BooleanField("Update default?")
	submit = SubmitField("Update Exercise")
