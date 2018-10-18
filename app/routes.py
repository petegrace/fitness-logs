from datetime import datetime, date
import calendar
import requests
from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from wtforms import HiddenField
from app import app, db
from app.forms import LogNewExerciseTypeForm, EditExerciseForm, ScheduleNewExerciseTypeForm, EditScheduledExerciseForm, EditExerciseTypeForm, ExerciseCategoriesForm
from app.models import User, ExerciseType, Exercise, ScheduledExercise, ExerciseCategory

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
        'userId': userId
    }

    response = requests.post(
        'http://www.google-analytics.com/collect', data=data)


# Routes

@app.route("/")
@app.route("/index")
@login_required
def index():
	track_event(category="Main", action="Home page opened or refreshed", userId = str(current_user.id))
	page = request.args.get("page", 1, type=int)
	exercises = current_user.exercises().paginate(page, app.config["EXERCISES_PER_PAGE"], False) # Pagination object
	next_url = url_for("index", page=exercises.next_num) if exercises.has_next else None
	prev_url = url_for("index", page=exercises.prev_num) if exercises.has_prev else None

	today = date.today()
	current_day = calendar.day_abbr[today.weekday()]
	scheduled_exercises_remaining = current_user.scheduled_exercises_remaining(scheduled_day=current_day, exercise_date=today).all()

	has_completed_schedule = False

	if not scheduled_exercises_remaining:
		if current_user.scheduled_exercises(scheduled_day=current_day).all():
		   has_completed_schedule = True

	exercise_types = current_user.exercise_types_ordered().all()
	scheduled_exercises_remaining_type_ids = [scheduled_exercise.exercise_type_id for scheduled_exercise in scheduled_exercises_remaining]

	other_exercise_types = [exercise_type for exercise_type in exercise_types if exercise_type.id not in scheduled_exercises_remaining_type_ids]

	return render_template("index.html", title="Home", exercises=exercises.items, next_url=next_url, prev_url=prev_url,
							exercise_types=other_exercise_types, scheduled_exercises=scheduled_exercises_remaining, has_completed_schedule=has_completed_schedule)


@app.route("/log_exercise/<scheduled>/<id>")
@login_required
def log_exercise(scheduled, id):
	if scheduled == "other":
		track_event(category="Exercises", action="Exercise (non-scheduled) logged", userId = str(current_user.id))
		exercise_type = ExerciseType.query.get(int(id))

		# Log the exercise based on defaults
		exercise = Exercise(type=exercise_type,
							exercise_datetime=datetime.utcnow(),
							reps=exercise_type.default_reps,
							seconds=exercise_type.default_seconds)
	elif scheduled == "scheduled":
		track_event(category="Exercises", action="Exercise (scheduled) logged", userId = str(current_user.id))
		scheduled_exercise = ScheduledExercise.query.get(int(id))

		exercise = Exercise(type=scheduled_exercise.type,
							scheduled_exercise=scheduled_exercise,
							exercise_datetime=datetime.utcnow(),
							reps=scheduled_exercise.reps,
							seconds=scheduled_exercise.seconds)
	db.session.add(exercise)
	db.session.commit()

	flash("Added {type} at {datetime}".format(type=exercise.type.name, datetime=exercise.exercise_datetime))
	return redirect(url_for("index"))


@app.route("/new_exercise/<context>/<selected_day>", methods=["GET", "POST"])
@app.route("/new_exercise/<context>", methods=["GET", "POST"])
@login_required
def new_exercise(context, selected_day=None):
	if context == "logging":
		form = LogNewExerciseTypeForm()
	elif context == "scheduling":
		form = ScheduleNewExerciseTypeForm()

	category_choices = [(str(category.id), category.category_name) for category in current_user.exercise_categories.all()]
	form.exercise_category_id.choices = category_choices

	# for the post...
	if form.validate_on_submit():
		track_event(category="Exercises", action="New Exercise created for {context}".format(context=context), userId = str(current_user.id))
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
		if form.exercise_category_id.data != "None": 
			exercise_type.exercise_category_id = form.exercise_category_id.data		
		db.session.add(exercise_type)

		if context == "logging":
			exercise = Exercise(type=exercise_type,
								exercise_datetime=form.exercise_datetime.data,
								reps=form.reps.data,
								seconds=form.seconds.data)		
			db.session.add(exercise)
			db.session.commit()
			flash("Added {type} at {datetime}".format(type=exercise_type.name, datetime=exercise.exercise_datetime))
			return redirect(url_for("index"))
		elif context == "scheduling":
			scheduled_exercise = ScheduledExercise(type=exercise_type,
												   scheduled_day=selected_day,
												   sets=1,
												   reps=form.reps.data,
												   seconds=form.seconds.data)
			db.session.add(scheduled_exercise)
			db.session.commit()
			flash("Added {type} and scheduled for {scheduled_day}".format(type=exercise_type.name, scheduled_day=scheduled_exercise.scheduled_day))
			return redirect(url_for("schedule", schedule_freq="weekly", selected_day=selected_day))

	#for the get...
	form.user_categories_count.data = len(category_choices)
	track_event(category="Exercises", action="New Exercise form loaded for {context}".format(context=context), userId = str(current_user.id))
	return render_template("new_exercise.html", title="Log New Exercise Type", form=form, context=context)


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

		# Redirect to the page the user came from if it was passed in as next parameter, otherwise the index
		next_page = request.args.get("next")
		if not next_page or url_parse(next_page).netloc != "": # netloc check prevents redirection to another website
			return redirect(url_for("index"))
		return redirect(next_page)

	# If it's a get...
	form.exercise_datetime.data = exercise.exercise_datetime
	form.measured_by.data = exercise.type.measured_by
	form.reps.data = exercise.reps
	form.seconds.data = exercise.seconds
		
	track_event(category="Exercises", action="Edit Exercise form loaded", userId = str(current_user.id))
	return render_template("edit_exercise.html", title="Edit Exercise", form=form, exercise_name=exercise.type.name)


@app.route("/activity/<mode>")
@login_required
def activity(mode):
	track_event(category="Analysis", action="Activity {mode} page opened or refreshed".format(mode=mode), userId = str(current_user.id))

	if mode == "detail":
		exercises = current_user.exercises().all()
	elif mode == "summary":
		exercises = current_user.daily_exercise_summary().all()

	return render_template("activity.html", title="Activity", exercises=exercises, mode=mode)


@app.route("/schedule/<schedule_freq>/<selected_day>")
@app.route("/schedule/<schedule_freq>")
@login_required
def schedule(schedule_freq, selected_day=None):
	track_event(category="Schedule", action="Schedule ({frequency}) page opened or refreshed".format(frequency=schedule_freq), userId = str(current_user.id))

	if schedule_freq == "weekly":
		days = list(calendar.day_abbr)

	# Default to current day if not supplied in URL
	if selected_day is None:
		selected_day = calendar.day_abbr[date.today().weekday()]

	scheduled_exercises = current_user.scheduled_exercises(selected_day)

	exercise_types = current_user.exercise_types_ordered()

	return render_template("schedule.html", title="Schedule", schedule_days=days, schedule_freq=schedule_freq, selected_day=selected_day,
				scheduled_exercises=scheduled_exercises, exercise_types=exercise_types)


@app.route("/schedule_exercise/<id>/<selected_day>")
@login_required
def schedule_exercise(id, selected_day):
	exercise_type = ExerciseType.query.get(int(id))

	scheduled_exercise = ScheduledExercise.query.filter_by(type=exercise_type).filter_by(scheduled_day=selected_day).first()

	if scheduled_exercise:
		track_event(category="Schedule", action="Sets incremented for scheduled exercise", userId = str(current_user.id))
		scheduled_exercise.sets += 1
		flash("Added extra set for {type} on {day}".format(type=exercise_type.name, day=scheduled_exercise.scheduled_day))
	else:
		track_event(category="Schedule", action="Exercise scheduled", userId = str(current_user.id))

		# Schedule the exercise based on defaults
		scheduled_exercise = ScheduledExercise(type=exercise_type,
											   scheduled_day=selected_day,
											   sets=1,
											   reps=exercise_type.default_reps,
											   seconds=exercise_type.default_seconds)
		db.session.add(scheduled_exercise)
		flash("Added {type} to schedule for {day}".format(type=exercise_type.name, day=scheduled_exercise.scheduled_day))

	db.session.commit()
	return redirect(url_for("schedule", schedule_freq="weekly", selected_day=selected_day))


@app.route('/edit_scheduled_exercise/<id>', methods=['GET', 'POST'])
@login_required
def edit_scheduled_exercise(id):
	form = EditScheduledExerciseForm()
	scheduled_exercise = ScheduledExercise.query.get(int(id))

	if form.validate_on_submit():
		track_event(category="Schedule", action="Scheduled exercise updated", userId = str(current_user.id))
		scheduled_exercise.sets = form.sets.data
		scheduled_exercise.reps = form.reps.data
		scheduled_exercise.seconds = form.seconds.data
		db.session.commit()
		flash("Updated {type} scheduled for {day}".format(type=scheduled_exercise.type.name, day=scheduled_exercise.scheduled_day))

		if form.update_default.data:
			track_event(category="Exercises", action="Exercise default reps/secs updated", userId = str(current_user.id))
			scheduled_exercise.type.default_reps = form.reps.data
			scheduled_exercise.type.default_seconds = form.seconds.data
			db.session.commit()
			flash("Updated default {measured_by} for {type}".format(type=scheduled_exercise.type.name, measured_by=scheduled_exercise.type.measured_by))

		return redirect(url_for("schedule", schedule_freq="weekly", selected_day=scheduled_exercise.scheduled_day))

	# If it's a get...
	form.sets.data = scheduled_exercise.sets
	form.measured_by.data = scheduled_exercise.type.measured_by
	form.reps.data = scheduled_exercise.reps
	form.seconds.data = scheduled_exercise.seconds
		
	track_event(category="Schedule", action="Edit Scheduled Exercise form loaded", userId = str(current_user.id))
	return render_template("edit_exercise.html", title="Edit Scheduled Exercise", form=form, exercise_name=scheduled_exercise.type.name)


@app.route("/exercise_types")
@login_required
def exercise_types():
	track_event(category="Manage", action="Exercise Types page loaded", userId = str(current_user.id))

	exercise_types = current_user.exercise_types.order_by(ExerciseType.name).all()

	return render_template("exercise_types.html", title="Exercise Types", exercise_types=exercise_types)


@app.route('/edit_exercise_type/<id>', methods=['GET', 'POST'])
@login_required
def edit_exercise_type(id):
	form = EditExerciseTypeForm()
	category_choices = [(str(category.id), category.category_name) for category in current_user.exercise_categories.all()]
	form.exercise_category_id.choices = category_choices

	exercise_type = ExerciseType.query.get(int(id))

	if form.validate_on_submit():
		track_event(category="Manage", action="Exercise Type updated", userId = str(current_user.id))

		# Ensure that seconds and reps are none if the other is selected
		if form.measured_by.data == "reps":
			form.default_seconds.data = None
		elif form.measured_by.data == "seconds":
			form.default_reps.data = None

		exercise_type.measured_by = form.measured_by.data
		exercise_type.default_reps = form.default_reps.data
		exercise_type.default_seconds = form.default_seconds.data
		if form.exercise_category_id.data != "None": 
			exercise_type.exercise_category_id = form.exercise_category_id.data
		db.session.commit()
		flash("Updated {name}".format(name=exercise_type.name))

		return redirect(url_for("exercise_types"))

	# If it's a get...
	form.user_categories_count.data = len(category_choices)
	form.measured_by.data = exercise_type.measured_by
	form.default_reps.data = exercise_type.default_reps
	form.default_seconds.data = exercise_type.default_seconds
	form.exercise_category_id.data = exercise_type.exercise_category_id
		
	track_event(category="Manage", action="Edit Exercise Type form loaded", userId = str(current_user.id))
	return render_template("edit_exercise_type.html", title="Edit Exercise Type", form=form, exercise_name=exercise_type.name)


@app.route("/categories", methods=['GET', 'POST'])
def categories():
	categories_form = ExerciseCategoriesForm()
	current_categories = current_user.exercise_categories

	if categories_form.validate_on_submit():
		track_event(category="Manage", action="Category changes saved", userId = str(current_user.id))

		category_keys = [field_name for field_name in dir(categories_form) if field_name.startswith("cat_")]

		for category_key in category_keys:
			if categories_form[category_key].data != "":
				category = current_categories.filter_by(category_key=category_key).first()

				if category:
					category.category_name = categories_form[category_key].data
				else:
					category = ExerciseCategory(owner=current_user,
												category_key=category_key,
												category_name=categories_form[category_key].data)
			elif categories_form[category_key].data == "":
				category = current_categories.filter_by(category_key=category_key).first()

				if category:
					db.session.delete(category)

		db.session.commit()

		flash("Changes to Exercise Categories have been saved.")
		return redirect(url_for("exercise_types"))

	# If it's a get...
	for current_category in current_categories:
		categories_form[current_category.category_key].data = current_category.category_name

	track_event(category="Manage", action="Exercise Categories page loaded", userId = str(current_user.id))
	return render_template("categories.html", title="Manage Exercise Categories", categories_form=categories_form)