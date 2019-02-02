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


class AddNewExerciseTypeForm(FlaskForm):
	name = StringField("Exercise Name", validators=[DataRequired(), Length(min=1, max=100)])
	user_categories_count = HiddenField("user_categories_count")
	# fields for the scheduled exercise (reps will also serve as the default)
	measured_by = SelectField('Measured By', choices=[('reps', 'Reps'), ('seconds', 'Time (seconds)')])
	reps = IntegerField("Reps", validators=[Optional()])
	seconds = IntegerField("Seconds", validators=[Optional()])
	exercise_category_id = SelectField('Category', choices=[], validators=[Optional()])
	submit = SubmitField("Add Exercise Type")

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

		
class ScheduledActivityForm(FlaskForm):
	description = StringField("Description", validators=[Length(max=500)], render_kw={"placeholder": "(optional)"})
	planned_distance = IntegerField("Planned Distance (km)", render_kw={"placeholder": "(optional)"}, validators=[Optional()])
	submit = SubmitField("Save Activity")

		
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

class ActivitiesCompletedGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	target_activities_to_complete = IntegerField("Target Runs to Complete", validators=[DataRequired()])
	minimum_distance = IntegerField("Of at least... (km)", validators=[DataRequired()])
	submit = SubmitField("Set Goal")

	def get_dimension_value_input(self):
		return self.minimum_distance

	def get_target_input(self):
		return self.target_activities_to_complete

class TotalDistanceGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	target_distance = IntegerField("Target Weekly Distance (km)", validators=[DataRequired()])
	submit = SubmitField("Set Goal")

	def get_dimension_value_input(self):
		return None

	def get_target_input(self):
		return self.target_distance

class TotalMovingTimeGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	target_moving_time = IntegerField("Target Moving Time (minutes)", validators=[DataRequired()])
	submit = SubmitField("Set Goal")

	def get_dimension_value_input(self):
		return None

	def get_target_input(self):
		return self.target_moving_time

class TotalElevationGainGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	target_elevation_gain = IntegerField("Target Elevation Gain (m)", validators=[DataRequired()])
	submit = SubmitField("Set Goal")

	def get_dimension_value_input(self):
		return None

	def get_target_input(self):
		return self.target_elevation_gain

class CadenceGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	cadence = IntegerField("Cadence", validators=[DataRequired()])
	target_minutes_above_cadence = IntegerField("Target Minutes Above Cadence", validators=[DataRequired()])
	submit = SubmitField("Set Goal")

	def get_dimension_value_input(self):
		return self.cadence

	def get_target_input(self):
		return self.target_minutes_above_cadence

	def validate_cadence(self, cadence):
		if cadence.data % 2 == 1:
			raise ValidationError("Cadence must be an even number due to precision at which data is stored.")

class GradientGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	gradient = IntegerField("Gradient %", validators=[DataRequired()])
	target_km_above_gradient = IntegerField("Target Kilometres Above Gradient", validators=[DataRequired()])
	submit = SubmitField("Set Goal")

	def get_dimension_value_input(self):
		return self.gradient

	def get_target_input(self):
		return self.target_km_above_gradient

class ExerciseSetsGoalForm(FlaskForm):
	goal_relative_week = SelectField('Goal For', choices=[('this', 'This Week'), ('next', 'Next Week')])
	exercise_category_id = SelectField('Category', choices=[], validators=[Optional()])
	target_sets_to_complete = IntegerField("Target Sets to Complete", validators=[DataRequired()])
	submit = SubmitField("Set Goal")