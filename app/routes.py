from datetime import datetime
import requests
from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import app, db
from app.forms import LogNewExerciseTypeForm, EditExerciseForm
from app.models import User, ExerciseType, Exercise

# Helpers

def track_event(category, action, label=None, value=0, userId="0"):
    data = {
        'v': '1',  # API Version.
        'tid': app.config["GA_TRACKING_ID"],  # Tracking ID / Property ID.
        # Anonymous Client Identifier. Ideally, this should be a UUID that
        # is associated with particular user, device, or browser instance.
        'cid': userId,
        't': 'event',  # Event hit type.
        'ec': category,  # Event category.
        'ea': action,  # Event action.
        'el': label,  # Event label.
        'ev': value,  # Event value, must be an integer
    }

    response = requests.post(
        'http://www.google-analytics.com/collect', data=data)


# Routes

@app.route("/")
@app.route("/index")
@login_required
def index():
	page = request.args.get("page", 1, type=int)
	exercises = current_user.exercises().paginate(page, app.config["EXERCISES_PER_PAGE"], False) # Pagination object
	next_url = url_for("index", page=exercises.next_num) if exercises.has_next else None
	prev_url = url_for("index", page=exercises.prev_num) if exercises.has_prev else None
	exercise_types = current_user.exercise_types
	return render_template("index.html", title="Home", exercises=exercises.items, exercise_types=exercise_types,
							next_url=next_url, prev_url=prev_url)


@app.route("/log_exercise/<id>")
@login_required
def log_exercise(id):
	track_event(category="Exercises", action="Exercise logged", userId = str(current_user.id))
	exercise_type = ExerciseType.query.get(int(id))

	# Log the exercise based on defaults
	# TODO: This should be a function somewhere to avoid duplication with new_exercise, just not sure where yet!
	exercise = Exercise(type=exercise_type,
						exercise_datetime=datetime.utcnow(),
						reps=exercise_type.default_reps,
						seconds=exercise_type.default_seconds)
	db.session.add(exercise)
	db.session.commit()
	flash("Added {type} at {datetime}".format(type=exercise_type.name, datetime=exercise.exercise_datetime))
	return redirect(url_for("index"))


@app.route("/new_exercise", methods=["GET", "POST"])
@login_required
def new_exercise():
	form = LogNewExerciseTypeForm()

	# for the post...
	if form.validate_on_submit():
		track_event(category="Exercises", action="New Exercise created", userId = str(current_user.id))
		# Ensure that seconds and reps are none if the other is selected
		if form.measured_by.data == "reps":
			form.seconds.data = None
		elif form.measured_by.data == "seconds":
			form.reps.data = None

		exercise_type = ExerciseType(name=form.name.data,
									 owner=current_user,
									 measured_by=form.measured_by.data,
									 default_reps=form.reps.data,
									 default_seconds=form.seconds.data)
		db.session.add(exercise_type)
		exercise = Exercise(type=exercise_type,
							exercise_datetime=form.exercise_datetime.data,
							reps=form.reps.data,
							seconds=form.seconds.data)		
		db.session.add(exercise)
		db.session.commit()
		flash("Added {type} at {datetime}".format(type=exercise_type.name, datetime=exercise.exercise_datetime))
		return redirect(url_for("index"))

	#for the get...
	track_event(category="Exercises", action="New Exercise form loaded", userId = str(current_user.id))
	return render_template("new_exercise.html", title="Log New Exercise Type", form=form)


@app.route('/edit_exercise/<id>', methods=['GET', 'POST'])
@login_required
def edit_exercise(id):
	form = EditExerciseForm()
	exercise = Exercise.query.get(int(id))

	if form.validate_on_submit():
		track_event(category="Exercises", action="Exercise updated", userId = str(current_user.id))
		exercise.exercise_datetime = form.exercise_datetime.data
		exercise.reps = form.reps.data
		exercise.seconds = form.seconds.data
		db.session.commit()
		flash("Updated {type} at {datetime}".format(type=exercise.type.name, datetime=exercise.exercise_datetime))

		if form.update_default.data:
			track_event(category="Exercises", action="Exercise default reps/secs updated", userId = str(current_user.id))
			exercise.type.default_reps = form.reps.data
			exercise.type.default_seconds = form.seconds.data
			db.session.commit()
			flash("Updated default {measured_by} for {type}".format(type=exercise.type.name, measured_by=exercise.type.measured_by))

		return redirect(url_for("index"))

	# If it's a get...
	form.exercise_datetime.data = exercise.exercise_datetime
	form.measured_by.data = exercise.type.measured_by
	form.reps.data = exercise.reps
	form.seconds.data = exercise.seconds
		
	track_event(category="Exercises", action="Edit Exercise form loaded", userId = str(current_user.id))
	return render_template("edit_exercise.html", title="Edit Exercise", form=form, exercise_name=exercise.type.name)