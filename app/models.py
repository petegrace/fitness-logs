from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import func, literal, desc, and_, or_, null
from app import db
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

	def __repr__(self):
		return "<User {email}>".format(email=self.email)

	def set_password(self, password):
		self.password_hash = generate_password_hash(password)

	def check_password(self, password):
		return check_password_hash(self.password_hash, password)

	def most_recent_strava_activity_datetime(self):
		most_recent_strava_activity_datetime_result = db.session.query(
					func.max(Activity.start_datetime).label("max_date")
				).filter(Activity.owner == self
				).filter(Activity.external_source == "Strava").first()
		return most_recent_strava_activity_datetime_result.max_date

	@login.user_loader
	def load_user(id):
		return User.query.get(int(id))

	def exercises(self):
		return Exercise.query.join(ExerciseType,
			(ExerciseType.id == Exercise.exercise_type_id)).filter(ExerciseType.owner == self).order_by(Exercise.exercise_datetime.desc())

	def recent_activities(self):
		exercises = db.session.query(
						Exercise.id,
						literal("Exercise").label("source"),
						Exercise.created_datetime.label("created_datetime"),
						Exercise.exercise_datetime.label("activity_datetime"),
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
						Activity.name,
						null().label("scheduled_exercise_id"),
						Activity.is_race,
						null().label("reps"),
						null().label("seconds"),
						Activity.distance,
						literal("distance").label("measured_by"),
						Activity.external_id
				).filter(Activity.owner == self)

		exercises_and_activities = exercises.union(activities).order_by(desc("created_datetime"), desc("activity_datetime"))
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


	def daily_exercise_summary(self):
		daily_exercise_summary = db.session.query(
					ExerciseType.name,
					ExerciseType.measured_by,
					func.date(Exercise.exercise_datetime).label("exercise_date"),
					func.sum(Exercise.reps).label("total_reps"),
					func.sum(Exercise.seconds).label("total_seconds")
				).join(ExerciseType.exercises
				).filter(ExerciseType.owner == self
				).group_by(
					ExerciseType.name,
					ExerciseType.measured_by,
					func.date(Exercise.exercise_datetime)
				).order_by(ExerciseType.measured_by, func.sum(Exercise.reps).desc(), func.sum(Exercise.seconds).desc(), ExerciseType.name)

		return daily_exercise_summary


	def exercises_by_category_and_day(self):
		exercises_by_category_and_day = db.session.query(
					func.date(Exercise.exercise_datetime).label("exercise_date"),
					func.coalesce(ExerciseCategory.category_key, "Uncategorised").label("category_key"),
					func.count(Exercise.id).label("exercise_sets_count"),
					func.sum(Exercise.reps).label("total_reps"),
					func.sum(Exercise.seconds).label("total_seconds")
				).join(ExerciseType.exercises
				).outerjoin(ExerciseType.exercise_category
				).filter(ExerciseType.owner == self
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
	average_heartrate = db.Column(db.Numeric())
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)

	def __repr__(self):
		return "<Activity {name} with external ID of {external_id}>".format(name=self.name, external_id=self.external_id)


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