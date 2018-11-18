from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import func, literal, desc, and_, or_, null, extract, distinct
from app import db, utils
from app import login
from itertools import groupby

class ExerciseDateGroup:
	def __init__(self, exercise_date, exercises):
		self.exercise_date = exercise_date
		self.exercises = exercises

class User(UserMixin, db.Model):
	id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(120), index=True, unique=True)
	auth_type = db.Column(db.String(50))
	password_hash = db.Column(db.String(128))
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)
	exercise_types = db.relationship("ExerciseType", backref="owner", lazy="dynamic")
	exercise_categories = db.relationship("ExerciseCategory", backref="owner", lazy="dynamic")
	activities = db.relationship("Activity", backref="owner", lazy="dynamic")
	training_goals = db.relationship("TrainingGoal", backref="owner", lazy="dynamic")

	def __repr__(self):
		return "<User {email}>".format(email=self.email)

	def set_password(self, password):
		self.password_hash = generate_password_hash(password)

	def check_password(self, password):
		return check_password_hash(self.password_hash, password)

	def most_recent_strava_activity_datetime(self):
		most_recent_strava_activity_datetime_result = db.session.query(
					func.max(Activity.start_datetime).label("max_datetime")
				).filter(Activity.owner == self
				).filter(Activity.external_source == "Strava").first()
		return most_recent_strava_activity_datetime_result.max_datetime

	def first_active_year(self):
		first_activity_datetime_result = db.session.query(
					func.min(Activity.start_datetime).label("min_datetime")
				).filter(Activity.owner == self).first()

		first_exercise_datetime_result = db.session.query(
					func.min(Exercise.exercise_datetime).label("min_datetime")
				).join(ExerciseType, (ExerciseType.id == Exercise.exercise_type_id)
				).filter(ExerciseType.owner == self).first()

		# Probably a better way to do this but dealing with the bug when comparing None
		if first_activity_datetime_result.min_datetime is None and first_exercise_datetime_result.min_datetime is None:
			first_active_year = 2018
		elif first_activity_datetime_result.min_datetime is None:
			first_active_year = first_exercise_datetime_result.min_datetime.year
		elif first_exercise_datetime_result.min_datetime is None:
			first_active_year = first_activity_datetime_result.min_datetime.year
		elif first_activity_datetime_result.min_datetime < first_exercise_datetime_result.min_datetime:
			first_active_year = first_activity_datetime_result.min_datetime.year
		else:
			first_active_year = first_exercise_datetime_result.min_datetime.year

		return first_active_year

	@login.user_loader
	def load_user(id):
		return User.query.get(int(id))

	def exercises(self):
		return Exercise.query.join(ExerciseType,
			(ExerciseType.id == Exercise.exercise_type_id)).filter(ExerciseType.owner == self).order_by(Exercise.exercise_datetime.desc())

	def exercises_filtered(self, exercise_category_id=None, week=None):
		return Exercise.query.join(ExerciseType, (ExerciseType.id == Exercise.exercise_type_id)
			).join(CalendarDay, (func.date(Exercise.exercise_datetime) == CalendarDay.calendar_date)
			).filter(ExerciseType.owner == self
			).filter(or_(ExerciseType.exercise_category_id == exercise_category_id, exercise_category_id is None)
			).filter(or_(CalendarDay.calendar_week_start_date == week, week is None)
			)

	def activities_filtered(self, activity_type=None, week=None):
		return Activity.query.join(CalendarDay, (func.date(Activity.start_datetime) == CalendarDay.calendar_date)
			).filter(Activity.owner == self
			).filter(or_(Activity.activity_type == activity_type, activity_type is None)
			).filter(or_(CalendarDay.calendar_week_start_date == week, week is None)
			)

	def recent_activities(self):
		exercises = db.session.query(
						Exercise.id,
						literal("Exercise").label("source"),
						Exercise.created_datetime.label("created_datetime"),
						Exercise.exercise_datetime.label("activity_datetime"),
						func.date(Exercise.exercise_datetime).label("activity_date"),
						ExerciseType.name,
						Exercise.scheduled_exercise_id,
						null().label("is_race"),
						Exercise.reps,
						Exercise.seconds,
						null().label("distance"),
						ExerciseType.measured_by,
						null().label("external_id")
				).join(ExerciseType, (ExerciseType.id == Exercise.exercise_type_id)
				).filter(ExerciseType.owner == self)

		activities = db.session.query(
						Activity.id,
						func.coalesce(Activity.external_source, "Activity").label("source"),
						Activity.created_datetime.label("created_datetime"),
						Activity.start_datetime.label("activity_datetime"),
						func.date(Activity.start_datetime).label("activity_date"),
						Activity.name,
						null().label("scheduled_exercise_id"),
						Activity.is_race,
						null().label("reps"),
						null().label("seconds"),
						Activity.distance,
						literal("distance").label("measured_by"),
						Activity.external_id
				).filter(Activity.owner == self)

		exercises_and_activities = exercises.union(activities)
		return exercises_and_activities

	def scheduled_exercises(self, scheduled_day):
		return ScheduledExercise.query.join(ExerciseType,
			(ExerciseType.id == ScheduledExercise.exercise_type_id)
			).filter(ExerciseType.owner == self
			).filter(ScheduledExercise.is_removed == False
			).filter(ScheduledExercise.scheduled_day == scheduled_day
			).order_by(ExerciseType.name)

	def scheduled_exercises_remaining(self, scheduled_day, exercise_date):
		scheduled_exercises_remaining = db.session.query(
					ScheduledExercise.id,
					ExerciseType.id.label("exercise_type_id"),
					ExerciseType.name,
					ExerciseCategory.category_key,
					ExerciseCategory.category_name,
					ExerciseType.measured_by,
					ScheduledExercise.sets,
					ScheduledExercise.reps,
					ScheduledExercise.seconds,
					func.count(Exercise.id).label("completed_sets")
				).join(ExerciseType.scheduled_exercises
				).outerjoin(ExerciseType.exercise_category
				).outerjoin(Exercise, and_((ScheduledExercise.id == Exercise.scheduled_exercise_id),
										   (func.date(Exercise.exercise_datetime) == exercise_date))
				).filter(ExerciseType.owner == self
				).filter(ScheduledExercise.scheduled_day == scheduled_day
				).filter(ScheduledExercise.is_removed == False
				).group_by(
					ScheduledExercise.id,
					ExerciseType.id,
					ExerciseType.name,
					ExerciseCategory.category_key,
					ExerciseCategory.category_name,
					ExerciseType.measured_by,
					ScheduledExercise.sets,
					ScheduledExercise.reps,
					ScheduledExercise.seconds
				).having((ScheduledExercise.sets - func.count(Exercise.id)) > 0)

		return scheduled_exercises_remaining

	def weekly_activity_summary(self, year=None, week=None):
		exercises = db.session.query(
						func.coalesce(ExerciseCategory.category_name, "Uncategorised").label("category_name"),
						func.coalesce(ExerciseCategory.category_key, "Uncategorised").label("category_key"),
						CalendarDay.calendar_week_start_date.label("week_start_date"),
						func.count(distinct(func.date(Exercise.exercise_datetime))).label("total_activities"),
						func.count(Exercise.id).label("total_sets"),
						func.sum(Exercise.reps).label("total_reps"),
						func.sum(Exercise.seconds).label("total_seconds"),
						null().label("total_distance")
				).join(ExerciseType.exercises
				).join(ExerciseType.exercise_category
				).join(CalendarDay, func.date(Exercise.exercise_datetime)==CalendarDay.calendar_date
				).filter(ExerciseType.owner == self
				).filter(or_(CalendarDay.calendar_year == year, year is None)
				).filter(or_(CalendarDay.calendar_week_start_date == week, week is None)
				).group_by(
						CalendarDay.calendar_week_start_date,
						ExerciseCategory.category_key,
						ExerciseCategory.category_name
				)

		activities = db.session.query(
						Activity.activity_type.label("category_name"),
						func.coalesce(ExerciseCategory.category_key, Activity.activity_type).label("category_key"),
						CalendarDay.calendar_week_start_date.label("week_start_date"),
						func.count(distinct(func.date(Activity.start_datetime))).label("total_activities"),
						func.count(Activity.id).label("total_sets"),
						null().label("total_reps"),
						extract("epoch", func.sum(Activity.moving_time)).label("total_seconds"),
						func.sum(Activity.distance).label("total_distance")
				).join(CalendarDay, func.date(Activity.start_datetime)==CalendarDay.calendar_date
				).outerjoin(ExerciseCategory, and_(Activity.activity_type==ExerciseCategory.category_name, ExerciseCategory.user_id==Activity.user_id)
				).filter(Activity.owner == self
				).filter(or_(CalendarDay.calendar_year == year, year is None)
				).filter(or_(CalendarDay.calendar_week_start_date == week, week is None)
				).group_by(
					CalendarDay.calendar_week_start_date,
						ExerciseCategory.category_key,
						Activity.activity_type.label("category_name")
				)

		weekly_activity_summary = exercises.union(activities)
		return weekly_activity_summary

	def weekly_cadence_stats(self, week=None):
		weekly_cadence_stats = db.session.query(
						ActivityCadenceAggregate.cadence,
						CalendarDay.calendar_week_start_date,
						func.sum(ActivityCadenceAggregate.total_seconds_at_cadence).label("total_seconds_at_cadence"),
						func.sum(ActivityCadenceAggregate.total_seconds_above_cadence).label("total_seconds_above_cadence"),
						literal("").label("total_seconds_above_cadence_formatted")
				).join(ActivityCadenceAggregate.activity
				).join(CalendarDay, func.date(Activity.start_datetime)==CalendarDay.calendar_date
				).filter(Activity.owner == self
				).filter(or_(CalendarDay.calendar_week_start_date == week, week is None)
				).group_by(
						ActivityCadenceAggregate.cadence,
						CalendarDay.calendar_week_start_date
				).order_by(ActivityCadenceAggregate.cadence.desc()) # Descending to support running total calcs

		return weekly_cadence_stats

	def daily_activity_summary(self):
		daily_exercise_summary = db.session.query(
					ExerciseType.id,
					ExerciseType.name,
					literal("Exercise").label("source"),
					ExerciseType.measured_by,
					func.date(Exercise.exercise_datetime).label("activity_date"),
					null().label("is_race"),
					func.sum(Exercise.reps).label("total_reps"),
					func.sum(Exercise.seconds).label("total_seconds"),
					null().label("total_distance"),
					null().label("external_id")
				).join(ExerciseType.exercises
				).filter(ExerciseType.owner == self
				).group_by(
					ExerciseType.id,
					ExerciseType.name,
					ExerciseType.measured_by,
					func.date(Exercise.exercise_datetime)
				).order_by(ExerciseType.measured_by, func.sum(Exercise.reps).desc(), func.sum(Exercise.seconds).desc(), ExerciseType.name)

		activities = db.session.query(
						Activity.id,
						Activity.name,
						func.coalesce(Activity.external_source, "Activity").label("source"),
						literal("distance").label("measured_by"),
						func.date(Activity.start_datetime).label("activity_date"),
						Activity.is_race,
						null().label("total_reps"),
						null().label("total_seconds"),
						Activity.distance.label("total_distance"),
						Activity.external_id
				).filter(Activity.owner == self)

		daily_activity_summary = daily_exercise_summary.union(activities)
		return daily_activity_summary


	def exercises_by_category_and_day(self, week=None):
		exercises_by_category_and_day = db.session.query(
					func.date(Exercise.exercise_datetime).label("exercise_date"),
					func.coalesce(ExerciseCategory.category_key, "Uncategorised").label("category_key"),
					func.count(Exercise.id).label("exercise_sets_count"),
					func.sum(Exercise.reps).label("total_reps"),
					func.sum(Exercise.seconds).label("total_seconds")
				).join(ExerciseType.exercises
				).join(CalendarDay, func.date(Exercise.exercise_datetime)==CalendarDay.calendar_date
				).outerjoin(ExerciseType.exercise_category
				).filter(ExerciseType.owner == self
				).filter(or_(CalendarDay.calendar_week_start_date == week, week is None)
				).group_by(
					func.date(Exercise.exercise_datetime).label("exercise_date"),
					ExerciseCategory.category_name,
					ExerciseCategory.category_key
				)

		return exercises_by_category_and_day


	def exercises_by_type(self):
		exercises_by_category_and_day = db.session.query(
					ExerciseType.name.label("exercise_type"),
					func.coalesce(ExerciseCategory.category_key, "Uncategorised").label("category_key"),
					func.count(Exercise.id).label("exercise_sets_count"),
					func.sum(Exercise.reps).label("total_reps"),
					func.sum(Exercise.seconds).label("total_seconds")
				).join(ExerciseType.exercises
				).outerjoin(ExerciseType.exercise_category
				).filter(ExerciseType.owner == self
				).group_by(
					ExerciseType.name,
					ExerciseCategory.category_name,
					ExerciseCategory.category_key
				)

		return exercises_by_category_and_day


	def exercise_types_ordered(self):		
		exercise_types_last_7_days = db.session.query(
					ExerciseType.id,
					ExerciseType.name,
					ExerciseCategory.category_key,
					ExerciseCategory.category_name,
					ExerciseType.measured_by,
					ExerciseType.default_reps,
					ExerciseType.default_seconds,
					func.count(Exercise.id).label("exercise_count"),
					func.max(Exercise.exercise_datetime).label("max_datetime")
				).join(ExerciseType.exercises
				).outerjoin(ExerciseType.exercise_category
				).filter(ExerciseType.owner == self
				).filter((Exercise.exercise_datetime >= datetime.utcnow() - timedelta(days=7))
				).group_by(
					ExerciseType.id,
					ExerciseType.name,
					ExerciseCategory.category_key,
					ExerciseCategory.category_name,
					ExerciseType.measured_by,
					ExerciseType.default_reps,
					ExerciseType.default_seconds
				).order_by(func.count(Exercise.id).desc())

		exercise_types_other = db.session.query(
					ExerciseType.id,
					ExerciseType.name,
					ExerciseCategory.category_key,
					ExerciseCategory.category_name,
					ExerciseType.measured_by,
					ExerciseType.default_reps,
					ExerciseType.default_seconds,
					literal(0).label("exercise_count"),
					func.max(Exercise.exercise_datetime).label("max_datetime")
				).outerjoin(ExerciseType.exercises
				).outerjoin(ExerciseType.exercise_category
				).filter(ExerciseType.owner == self
				).group_by(
					ExerciseType.id,
					ExerciseType.name,
					ExerciseCategory.category_key,
					ExerciseCategory.category_name,
					ExerciseType.measured_by,
					ExerciseType.default_reps,
					ExerciseType.default_seconds
				).having(or_(func.max(Exercise.exercise_datetime) < datetime.utcnow() - timedelta(days=7),
							 func.max(Exercise.exercise_datetime) == None)
				).order_by(func.max(Exercise.exercise_datetime).desc())

		ordered_exercise_types = exercise_types_last_7_days.union(exercise_types_other).order_by(desc("exercise_count"), desc("max_datetime"))

		return ordered_exercise_types


class ExerciseCategory(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	category_key = db.Column(db.String(25))
	category_name = db.Column(db.String(25))
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)
	exercise_types = db.relationship("ExerciseType", backref="exercise_category", lazy="dynamic")
	fill_color = db.Column(db.String(25))
	line_color = db.Column(db.String(25))

	def __repr__(self):
		return "<ExerciseCategory {name} for {user}>".format(name=self.category_name, user=self.owner.email)
		

class ExerciseType(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), index=True)
	measured_by = db.Column(db.String(50))
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	exercise_category_id = db.Column(db.Integer, db.ForeignKey("exercise_category.id"))
	default_reps = db.Column(db.Integer)
	default_seconds = db.Column(db.Integer)
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)
	exercises = db.relationship("Exercise", backref="type", lazy="dynamic")
	scheduled_exercises = db.relationship("ScheduledExercise", backref="type", lazy="dynamic")

	def __repr__(self):
		return "<ExerciseType {name} for {user}>".format(name=self.name, user=self.owner.email)


class Activity(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	external_source = db.Column(db.String(50))
	external_id = db.Column(db.String(50)) # string in case we ever use anyting other than Strava
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	name = db.Column(db.String(200))
	start_datetime = db.Column(db.DateTime)
	activity_type = db.Column(db.String(50))
	is_race = db.Column(db.Boolean, default=False)
	distance = db.Column(db.Numeric())
	elapsed_time = db.Column(db.Interval())
	moving_time = db.Column(db.Interval())
	average_speed = db.Column(db.Numeric())
	average_cadence = db.Column(db.Numeric())
	median_cadence = db.Column(db.Numeric())
	average_heartrate = db.Column(db.Numeric())
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)
	activity_cadence_aggregates = db.relationship("ActivityCadenceAggregate", backref="activity", lazy="dynamic")

	def __repr__(self):
		return "<Activity {name} with external ID of {external_id}>".format(name=self.name, external_id=self.external_id)

	@property
	def category(self):
		category = ExerciseCategory.query.filter_by(category_name=self.activity_type).filter_by(owner=self.owner).first()
		return category

	@property
	def activity_date(self):
		return self.start_datetime.date()

	@property
	def distance_formatted(self):
		if self.distance >= 1000:
			distance_formatted = "{value} km".format(value=utils.convert_m_to_km(self.distance))
		else:
			distance_formatted = "{value} m".format(value=self.distance)
		return distance_formatted

	@property
	def average_pace_formatted(self):
		km_pace = utils.convert_mps_to_km_pace(self.average_speed)
		average_pace_formatted = "{value} /km".format(value=utils.format_timedelta_minutes(km_pace))
		return average_pace_formatted


class ActivityCadenceAggregate(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	activity_id = db.Column(db.Integer, db.ForeignKey("activity.id"))
	cadence = db.Column(db.Integer)
	total_seconds_at_cadence = db.Column(db.Integer)
	total_seconds_above_cadence = db.Column(db.Integer)
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)

	def __repr__(self):
		return "<ActivityCadenceAggregate for {cadence} on {name}>".format(cadence=self.cadence, name=self.activity.name)

	@property
	def total_seconds_at_cadence_formatted(self):
		return utils.format_timedelta_minutes(timedelta(seconds=self.total_seconds_at_cadence))

	@property
	def total_seconds_above_cadence_formatted(self):
		return utils.format_timedelta_minutes(timedelta(seconds=self.total_seconds_above_cadence))


class Exercise(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	exercise_type_id = db.Column(db.Integer, db.ForeignKey("exercise_type.id"))
	scheduled_exercise_id = db.Column(db.Integer, db.ForeignKey("scheduled_exercise.id"))
	exercise_datetime = db.Column(db.DateTime, index=True, default=datetime.utcnow)
	reps = db.Column(db.Integer)
	seconds = db.Column(db.Integer)
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)

	def __repr__(self):
		return "<Exercise {name} for {user} at {time}>".format(
			name=self.type.name, user=self.type.owner.email, time=self.exercise_datetime)

	@property
	def exercise_date(self):
		return self.exercise_datetime.date()

	@property
	def owner(self):
		return self.type.owner


class ScheduledExercise(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	exercise_type_id = db.Column(db.Integer, db.ForeignKey("exercise_type.id"))
	scheduled_day = db.Column(db.String(10))
	sets = db.Column(db.Integer)
	reps = db.Column(db.Integer)
	seconds = db.Column(db.Integer)
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)
	is_removed = db.Column(db.Boolean, default=False)
	exercises = db.relationship("Exercise", backref="scheduled_exercise", lazy="dynamic")

	def __repr__(self):
		return "<ScheduledExercise {name} for {user} on {day}>".format(
			name=self.type.name, user=self.type.owner.email, day=self.scheduled_day)


class TrainingGoal(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	goal_period = db.Column(db.String(20))
	goal_start_date = db.Column(db.Date)
	goal_metric = db.Column(db.String(50))
	goal_metric_units = db.Column(db.String(50))
	goal_dimension_value = db.Column(db.String(50)) # The will be optional and might be an integer most of the time, e.g. Cadence of 168
	goal_target = db.Column(db.Numeric())
	current_metric_value = db.Column(db.Numeric())
	goal_status = db.Column(db.String(20))
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)

	def __repr__(self):
		return "<TrainingGoal for {metric} starting on {start_date}>".format(metric=self.goal_metric, start_date=self.goal_start_date)

	@property
	def percent_progress(self):
		return (self.current_metric_value / self.goal_target) * 100

	@property
	def goal_description(self):
		if self.goal_metric == "Exercise Sets Completed" and self.goal_dimension_value != "None":
			goal_dimension_friendly_value = ExerciseCategory.query.get(int(self.goal_dimension_value)).category_name
		else:	
			goal_dimension_friendly_value = self.goal_dimension_value
		return "{metric} of {value}".format(metric=self.goal_metric, value=goal_dimension_friendly_value)

	@property
	def goal_category(self):
		if self.goal_metric == "Exercise Sets Completed" and self.goal_dimension_value != "None":
			category = ExerciseCategory.query.get(int(self.goal_dimension_value))
		elif self.goal_metric == "Time Spent Above Cadence":
			category = ExerciseCategory.query.filter(ExerciseCategory.owner == self.owner).filter(ExerciseCategory.category_name == "Run").first()
		else:
			category=None
		return category


class CalendarDay(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	calendar_date = db.Column(db.Date, index=True)
	day_of_week = db.Column(db.String(10))
	calendar_week_start_date = db.Column(db.Date)
	calendar_year = db.Column(db.Integer)

	def __repr__(self):
		return "<CalendarDay {date}>".format(date=self.calendar_date)