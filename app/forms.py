from datetime import datetime
from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, PasswordField, DateTimeField, SelectField, IntegerField, SubmitField, HiddenField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from app.models import User, ExerciseType


class LogNewExerciseTypeForm(FlaskForm):
	name = StringField("Exercise Name", validators=[DataRequired(), Length(min=1, max=100)])
	user_categories_count = HiddenField("user_categories_count")
	# fields for the first exercise to be logged (reps will also serve as the default)
	exercise_datetime = DateTimeField("Exercise Date & Time (UTC)", format="%Y-%m-%d %H:%M:%S",
										validators=[DataRequired()], default=datetime.utcnow)
	measured_by = SelectField('Measured By', choices=[('reps', 'Reps'), ('seconds', 'Time (seconds)')])
	reps = IntegerField("Reps", validators=[Optional()])
	seconds = IntegerField("Seconds", validators=[Optional()])
	exercise_category_id = SelectField('Category', choices=[], validators=[Optional()])
	submit = SubmitField("Log Exercise")

	def validate_name(self, name):
		exercise_type = ExerciseType.query.filter_by(name=name.data).filter_by(owner=current_user).first()
		if exercise_type is not None:
			raise ValidationError("You already have an Exercise Type with that name.")


class ScheduleNewExerciseTypeForm(FlaskForm):
	name = StringField("Exercise Name", validators=[DataRequired(), Length(min=1, max=100)])
	user_categories_count = HiddenField("user_categories_count")
	# fields for the scheduled exercise (reps will also serve as the default)
	measured_by = SelectField('Measured By', choices=[('reps', 'Reps'), ('seconds', 'Time (seconds)')])
	reps = IntegerField("Reps", validators=[Optional()])
	seconds = IntegerField("Seconds", validators=[Optional()])
	exercise_category_id = SelectField('Category', choices=[], validators=[Optional()])
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

		
class EditExerciseTypeForm(FlaskForm):
	# TODO: Allowing editing of name will require some more advanced validation to allow the current name but not a separate name
	user_categories_count = HiddenField("user_categories_count")
	measured_by = SelectField('Measured By', choices=[('reps', 'Reps'), ('seconds', 'Time (seconds)')])
	default_reps = IntegerField("Default Reps", validators=[Optional()])
	default_seconds = IntegerField("Default Seconds", validators=[Optional()])
	exercise_category_id = SelectField('Category', choices=[], validators=[Optional()])
	submit = SubmitField("Update Exercise Type")

		
class ExerciseCategoriesForm(FlaskForm):
	cat_green = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	cat_green_outline = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	cat_blue = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	cat_blue_outline = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	cat_red = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	cat_red_outline = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	cat_yellow = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	cat_yellow_outline = StringField(validators=[Length(max=25)], render_kw={"placeholder": "Enter a category name", "class": "form-control"})
	submit = SubmitField("Save Changes", render_kw={"class": "btn btn-light border border-secondary"})

class CadenceGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	cadence = IntegerField("Cadence", validators=[DataRequired()])
	target_minutes_above_cadence = IntegerField("Target Minutes Above Cadence", validators=[DataRequired()])
	submit = SubmitField("Set Goal")
