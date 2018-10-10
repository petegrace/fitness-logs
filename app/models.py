from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db
from app import login

class User(UserMixin, db.Model):
	id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(120), index=True, unique=True)
	auth_type = db.Column(db.String(50))
	password_hash = db.Column(db.String(128))
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)
	exercise_types = db.relationship("ExerciseType", backref="owner", lazy="dynamic")

	def __repr__(self):
		return "<User {email}>".format(email=self.email)

	def set_password(self, password):
		self.password_hash = generate_password_hash(password)

	def check_password(self, password):
		return check_password_hash(self.password_hash, password)

	@login.user_loader
	def load_user(id):
		return User.query.get(int(id))

	def exercises(self):
		return Exercise.query.join(ExerciseType,
			(ExerciseType.id == Exercise.exercise_type_id)).filter(ExerciseType.owner == self).order_by(Exercise.exercise_datetime.desc())
		

class ExerciseType(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), index=True)
	measured_by = db.Column(db.String(50))
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	default_reps = db.Column(db.Integer)
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)
	exercises = db.relationship("Exercise", backref="type", lazy="dynamic")

	def __repr__(self):
		return "<ExerciseType {name} for {user}>".format(name=self.name, user=self.owner.email)


class Exercise(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	exercise_type_id = db.Column(db.Integer, db.ForeignKey("exercise_type.id"))
	exercise_datetime = db.Column(db.DateTime, index=True, default=datetime.utcnow)
	reps = db.Column(db.Integer)
	created_datetime = db.Column(db.DateTime, default=datetime.utcnow)

	def __repr__(self):
		return "<Exercise {name} for {user} at {time}>".format(
			name=self.type.name, user=self.type.owner.email, time=self.exercise_datetime)