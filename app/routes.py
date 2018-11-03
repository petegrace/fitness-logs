from datetime import datetime, date
import calendar
import requests
import statistics
from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from wtforms import HiddenField
import pandas as pd
from bokeh.embed import components
from bokeh.models import TapTool, CustomJS, Arrow, NormalHead, VeeHead
from app import app, db, utils
from app.forms import LogNewExerciseTypeForm, EditExerciseForm, ScheduleNewExerciseTypeForm, EditScheduledExerciseForm, EditExerciseTypeForm, ExerciseCategoriesForm
from app.models import User, ExerciseType, Exercise, ScheduledExercise, ExerciseCategory, Activity, ActivityCadenceAggregate, CalendarDay
from app.app_classes import TempCadenceAggregate
from app.dataviz import generate_stacked_bar_for_categories, generate_bar
from stravalib.client import Client
from requests_oauth2.services import OAuth2
from sqlalchemy import desc, and_, or_, null

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
	recent_activities = current_user.recent_activities().order_by(desc("created_datetime"), desc("activity_datetime")).paginate(page, app.config["EXERCISES_PER_PAGE"], False) # Pagination object
	next_url = url_for("index", page=recent_activities.next_num) if recent_activities.has_next else None
	prev_url = url_for("index", page=recent_activities.prev_num) if recent_activities.has_prev else None

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

	return render_template("index.html", title="Home", recent_activities=recent_activities.items, next_url=next_url, prev_url=prev_url,
							exercise_types=other_exercise_types, scheduled_exercises=scheduled_exercises_remaining, has_completed_schedule=has_completed_schedule, utils=utils)


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


@app.route("/weekly_activity/<year>")
@app.route("/weekly_activity/<year>/<week>")
@login_required
def weekly_activity(year, week=None): 
	track_event(category="Analysis", action="Weekly Activity page opened or refreshed", userId = str(current_user.id))

	week_options = db.session.query(CalendarDay.calendar_week_start_date
					).filter(CalendarDay.calendar_year==year
					).filter(CalendarDay.calendar_date<=datetime.today()
					).group_by(CalendarDay.calendar_week_start_date
					).order_by(CalendarDay.calendar_week_start_date.desc()).all()

	year_options = list(range(current_user.first_active_year(), datetime.today().year+1))

	if week is None:
		current_week = week_options[0].calendar_week_start_date
		current_week_datetime = datetime.strptime(str(current_week), "%Y-%m-%d")
		current_week_ms = current_week_datetime.timestamp() * 1000
	else:
		if "-" in week:
			current_week_datetime = datetime.strptime(week, "%Y-%m-%d")
			current_week = datetime.date(current_week_datetime)
			current_week_ms = current_week_datetime.timestamp() * 1000

		else: # assume milliseconds
			current_week_ms = int(week)
			current_week = datetime.date(datetime.fromtimestamp(current_week_ms/1000.0))
	days = CalendarDay.query.filter_by(calendar_week_start_date=current_week).order_by(CalendarDay.calendar_date.desc()).all()

	all_exercises = current_user.exercises().all()
	all_activities = current_user.activities.all()
	categories = current_user.exercise_categories.all()

	current_week_dataset = []
	current_week_activity_count = 0 # for plotting the current week indicator at the right height on the graph

	for day in days:
		exercises_by_category = []
		for category in categories:
			category_exercises = [exercise for exercise in all_exercises if exercise.exercise_date==day.calendar_date and exercise.type.exercise_category==category]
			if len(category_exercises) > 0:
				category_detail = dict(category=category,
						  			   exercise_count=len(category_exercises),
									   exercises=category_exercises)
				exercises_by_category.append(category_detail)
				current_week_activity_count += 1
		day_activities = [activity for activity in all_activities if activity.activity_date==day.calendar_date]
		current_week_activity_count += len(day_activities)
		day_detail = dict(day=day,
						  exercises_by_category=exercises_by_category,
						  activities=day_activities)
		current_week_dataset.append(day_detail)

	# Data and plotting for weekly cadence analysis graph
	weekly_cadence_stats = current_user.weekly_cadence_stats(week=current_week).all()
	weekly_cadence_goals = current_user.training_goals.filter_by(goal_start_date=current_week).filter_by(goal_metric="Time Spent Above Cadence").all()

	if len(weekly_cadence_goals) == 0:
		weekly_cadence_goals = None

	if len(weekly_cadence_stats) == 0:
		above_cadence_plot_script=None
		above_cadence_plot_div=None
	else:
		min_significant_cadence = 30
		max_significant_cadence = 300
		weekly_running_total = 0

		weekly_cadence_summary = []

		# For the lower range in graph look for aything more than 5 minutes
		for cadence_aggregate in weekly_cadence_stats:
			flash(cadence_aggregate)
			weekly_running_total += cadence_aggregate.total_seconds_at_cadence
			if cadence_aggregate.total_seconds_at_cadence >= 60 and max_significant_cadence==300: # only overwrite the max once (we're iterating in descing order)
				max_significant_cadence = cadence_aggregate.cadence 
			if cadence_aggregate.total_seconds_at_cadence >= 300: # keep overwriting until we get to the end and have the min
				min_significant_cadence = cadence_aggregate.cadence
			weekly_cadence_summary.append(TempCadenceAggregate(cadence=cadence_aggregate.cadence,
															   total_seconds_above_cadence=weekly_running_total))

		max_dimension_range = (min_significant_cadence, max_significant_cadence)
		above_cadence_plot = generate_bar(dataset=weekly_cadence_summary, plot_height=120, dimension_name="cadence", measure_name="total_seconds_above_cadence",
				measure_label_function=utils.convert_seconds_to_minutes_formatted, max_dimension_range=max_dimension_range, goals_dataset=weekly_cadence_goals)
		above_cadence_plot_script, above_cadence_plot_div = components(above_cadence_plot)

	# Data and plotting for the exercise sets by day graph
	exercises_by_category_and_day = current_user.exercises_by_category_and_day(week=current_week)
	user_categories = current_user.exercise_categories.all()

	exercise_sets_plot, source = generate_stacked_bar_for_categories(dataset_query=exercises_by_category_and_day, user_categories=user_categories,
		dimension="exercise_date", measure="exercise_sets_count", dimension_type = "datetime", plot_height=120, bar_direction="vertical")
	exercise_sets_plot_script, exercise_sets_plot_div = components(exercise_sets_plot)


	# Graph of activity by week for the year so we can provide navigation at the top
	weekly_summary = current_user.weekly_activity_summary(year=year)
	df = pd.read_sql(weekly_summary.statement, weekly_summary.session.bind)
	weekly_summary_plot, source = generate_stacked_bar_for_categories(dataset_query=weekly_summary, user_categories=categories,
		dimension="week_start_date", measure="total_activities", measure_units="activities", dimension_type = "datetime", plot_height=100, bar_direction="vertical",
		granularity="week", show_grid=False, show_yaxis=False)

	# TODO: extra stuff for the data viz should probably still go in the dataviz file, just a more specific function to call the generic one
	callback_code = """
selection = require('core/util/selection')
indices = selection.get_indices(source)
for (i = 0; i < indices.length; i++) {{
    ind = indices[i]
    url = "/weekly_activity/{year}/" + source.data['week_start_date'][ind]
    window.open(url, "_self")
}}
""".format(year=year)

	tap_tool = weekly_summary_plot.select(type=TapTool)
	tap_tool.callback = CustomJS(args=dict(source=source), code=callback_code)

	weekly_summary_plot.add_layout(Arrow(end=VeeHead(fill_color="#999999"),
                   x_start=current_week_ms, y_start=current_week_activity_count+0.1, x_end=current_week_ms, y_end=current_week_activity_count))

	weekly_summary_plot_script, weekly_summary_plot_div = components(weekly_summary_plot)

	return render_template("weekly_activity.html", title="Weekly Activity",utils=utils,
		weekly_summary=weekly_summary, weekly_summary_plot_script=weekly_summary_plot_script, weekly_summary_plot_div=weekly_summary_plot_div,
		year_options=year_options, week_options=week_options, current_year=int(year), current_week=current_week, current_week_dataset=current_week_dataset,
		above_cadence_plot_script=above_cadence_plot_script, above_cadence_plot_div=above_cadence_plot_div,
		exercise_sets_plot_script=exercise_sets_plot_script, exercise_sets_plot_div=exercise_sets_plot_div)


@app.route("/activity/<mode>")
@login_required
def activity(mode):
	track_event(category="Analysis", action="Activity {mode} page opened or refreshed".format(mode=mode), userId = str(current_user.id))

	# Data viz for exercises completed by day
	exercises_by_category_and_day = current_user.exercises_by_category_and_day()
	user_categories = current_user.exercise_categories.all()

	plot_by_day = generate_stacked_bar_for_categories(dataset_query=exercises_by_category_and_day, user_categories=user_categories,
		dimension="exercise_date", measure="exercise_sets_count", dimension_type = "datetime", plot_height=150, bar_direction="vertical")
	plot_by_day_script, plot_by_day_div = components(plot_by_day)

	if mode == "detail":
		activities = current_user.recent_activities().order_by(desc("activity_datetime")).all()
	elif mode == "summary":
		activities = current_user.daily_activity_summary().all()

	return render_template("activity.html", title="Activity", activities=activities, mode=mode, plot_by_day_script=plot_by_day_script, plot_by_day_div=plot_by_day_div, utils=utils)


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
		scheduled_exercise.is_removed = False
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


@app.route('/remove_scheduled_exercise/<id>')
@login_required
def remove_scheduled_exercise(id):
	scheduled_exercise = ScheduledExercise.query.get(int(id))
	track_event(category="Schedule", action="Scheduled exercise removed", userId = str(current_user.id))

	scheduled_exercise.is_removed = True
	db.session.commit()
	flash("Removed exercise {exercise} from schedule for {day}".format(exercise=scheduled_exercise.type.name, day=scheduled_exercise.scheduled_day))

	return redirect(url_for("schedule", schedule_freq="weekly", selected_day=scheduled_exercise.scheduled_day))


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
@login_required
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


@app.route("/import_strava_activity")
@login_required
def import_strava_activity():
	track_event(category="Strava", action="Starting import of Strava activity", userId = str(current_user.id))
	strava_client = Client()

	if not session.get("strava_access_token"):
		return redirect(url_for("connect_strava", action="prompt"))

	access_token = session["strava_access_token"]
	strava_client.access_token = access_token

	try:
		athlete = strava_client.get_athlete()
	except:
		return redirect(url_for("connect_strava", action="prompt"))

	most_recent_strava_activity_datetime = current_user.most_recent_strava_activity_datetime()
	activities = strava_client.get_activities(after = most_recent_strava_activity_datetime)

	new_activity_count = 0
	for strava_activity in activities:
		activity = Activity(external_source = "Strava",
							external_id = strava_activity.id,
							owner = current_user,
							name = strava_activity.name,
							start_datetime = strava_activity.start_date,
							activity_type = strava_activity.type,
							is_race = True if strava_activity.workout_type == "1" else False,
							distance = strava_activity.distance.num,
							elapsed_time =strava_activity.elapsed_time,
							moving_time = strava_activity.moving_time,
							average_speed = strava_activity.average_speed.num,
							average_cadence = (strava_activity.average_cadence * 2) if strava_activity.type == "Run" else strava_activity.average_cadence,
							average_heartrate = strava_activity.average_heartrate)

		db.session.add(activity)
		new_activity_count += 1

	flash("Added {count} new activities from Strava!".format(count=new_activity_count))
	track_event(category="Strava", action="Completed import of Strava activity", userId = str(current_user.id))
	db.session.commit()

	# Redirect to the page the user came from if it was passed in as next parameter, otherwise the index
	next_page = request.args.get("next")
	if not next_page or url_parse(next_page).netloc != "": # netloc check prevents redirection to another website
		return redirect(url_for("index"))
	return redirect(next_page)


@app.route("/activity_analysis/<id>")
@login_required
def activity_analysis(id):
	track_event(category="Strava", action="Activity Analysis page loaded", userId = str(current_user.id))
	activity = Activity.query.get(int(id))

	# Grab the cadence data from Strava if we don't already have it
	if activity.median_cadence is None:
		track_event(category="Strava", action="Cadence stream parsed for new activity", userId = str(current_user.id))
		strava_client = Client()

		if not session.get("strava_access_token"):
			return redirect(url_for("connect_strava", action="authorize", next="/activity_analysis/{id}".format(id=id)))

		access_token = session["strava_access_token"]
		strava_client.access_token = access_token

		stream_types = ["time", "cadence"]

		try:
			activity_streams = strava_client.get_activity_streams(activity.external_id, types=stream_types)
		except:
			return redirect(url_for("connect_strava", action="authorize", next="/activity_analysis/{id}".format(id=id)))


		if "cadence" in activity_streams:
			cadence_records = []
			cadence_df = pd.DataFrame(columns=["cadence", "start_time", "duration"])
			dp_ind = 0
			df_ind = 0

			# construct a data frame
			for cadence_data_point in activity_streams["cadence"].data:
				if cadence_data_point > 0 and dp_ind > 1:
					duration = (activity_streams["time"].data[dp_ind] - activity_streams["time"].data[dp_ind-1])

					if duration <= 10: # Discard anything more than 10 seconds that probably relates to stopping
						#cadence_records.append({"cadence": cadence_data_point,
						#						"start_time": activity_streams["time"].data[dp_ind-1],
						#						"duration": duration})
						cadence_df.loc[df_ind] = [cadence_data_point, activity_streams["time"].data[dp_ind-1], duration]
						df_ind += 1
				dp_ind += 1

			cadence_aggregation = cadence_df.groupby(["cadence"])["duration"].sum()
			cadence_data = list(zip(cadence_aggregation.index, cadence_aggregation))
			cadence_data_desc = cadence_data
			cadence_data_desc.reverse()

			running_total = 0
			this_aggregate_total = 0
			#above_cadence_data = []

			for cadence_group in cadence_data_desc:
				running_total += cadence_group[1]
				this_aggregate_total += cadence_group[1]
				
				# Group up any outliers with seconds < 10 seconds into the next aggregate
				if this_aggregate_total > 10:
					activity_cadence_aggregate = ActivityCadenceAggregate(activity=activity,
																		  cadence=cadence_group[0]*2,
																		  total_seconds_at_cadence=this_aggregate_total,
																		  total_seconds_above_cadence=running_total)
					db.session.add(activity_cadence_aggregate)
					this_aggregate_total = 0

			activity.median_cadence = cadence_df["cadence"].median()*2
			db.session.commit()

	
	if activity.median_cadence is not None:
		# Keep the graph tidy if there's any bit of walking or other outliers by excluding them
		max_dimension_range = (int(activity.median_cadence-30), int(activity.median_cadence+30))

		at_cadence_plot = generate_bar(dataset=activity.activity_cadence_aggregates, plot_height=300,
			dimension_name="cadence", measure_name="total_seconds_at_cadence", measure_label_name="total_seconds_at_cadence_formatted", max_dimension_range=max_dimension_range)
		at_cadence_plot_script, at_cadence_plot_div = components(at_cadence_plot)

		above_cadence_plot = generate_bar(dataset=activity.activity_cadence_aggregates, plot_height=300,
			dimension_name="cadence", measure_name="total_seconds_above_cadence", measure_label_name="total_seconds_above_cadence_formatted", max_dimension_range=max_dimension_range)
		#above_cadence_plot
		above_cadence_plot_script, above_cadence_plot_div = components(above_cadence_plot)
	else:
		max_dimension_range = None
		at_cadence_plot_script, at_cadence_plot_div = ("", "")
		above_cadence_plot_script, above_cadence_plot_div = ("", "")

	return render_template("activity_analysis.html", title="Activity Analysis: {name}".format(name=activity.name), activity=activity,
		at_cadence_plot_script=at_cadence_plot_script, at_cadence_plot_div=at_cadence_plot_div,
		above_cadence_plot_script=above_cadence_plot_script, above_cadence_plot_div=above_cadence_plot_div)


@app.route("/connect_strava/<action>")
@login_required
def connect_strava(action="prompt"):
	code = request.args.get("code")
	error = request.args.get("error")
	next_page = request.args.get("next")

	if next_page is None:
		next_page = "/index"

	if error:
		track_event(category="Strava", action="Error during Strava authorizaion", userId = str(current_user.id))
		return redirect(url_for("index"))

	if action == "authorize":
		# Do the Strava bit
		strava_auth = OAuth2(
			client_id = app.config["STRAVA_OAUTH2_CLIENT_ID"],
			client_secret = app.config["STRAVA_OAUTH2_CLIENT_SECRET"],
			site = "https://www.strava.com",
			redirect_uri = app.config["STRAVA_OAUTH2_REDIRECT_URI"] + "?next={next}".format(next=next_page),
			authorization_url = '/oauth/authorize',
			token_url = '/oauth/token',
			revoke_url = '/oauth2/deauthorize',
			scope_sep = ","
		)

		if not code:
			return redirect(strava_auth.authorize_url(scope=["activity:read"], response_type="code"))

		data = strava_auth.get_token(code=code, grant_type="authorization_code")
		session["strava_access_token"] = data.get("access_token")
		track_event(category="Strava", action="Strava authorization successful", userId = str(current_user.id))

		# Pass the next query string parameter through o the import
		return redirect(url_for("import_strava_activity", next=next_page))

	# Shouldn' reach here any more as we're passing people to this route directly
	track_event(category="Strava", action="Login page for Strava", userId = str(current_user.id))
	return render_template("connect_strava.html", title="Connect to Strava")



@app.route("/charts")
@login_required
def chart():
	plot_by_day = select_test()
	plot_by_day_script, plot_by_day_div = components(plot_by_day)

	return render_template("chart.html", title="Exercises Data Viz", bars_count=0,
 		plot_by_day_div=plot_by_day_div, plot_by_day_script=plot_by_day_script)
# 	exercises_by_category_and_day = current_user.exercises_by_category_and_day()
# 	exercises_by_type = current_user.exercises_by_type()
# 	user_categories = current_user.exercise_categories.all()

# 	# Colour mappings
# 	available_categories = ["cat_green", "cat_green_outline", "cat_blue", "cat_blue_outline", "cat_red", "cat_red_outline", "cat_yellow", "cat_yellow_outline", "Uncategorised"]
# 	available_colors = ["#5cb85c", "#ffffff", "#0275d8", "#ffffff", "#d9534f", "#ffffff", "#f0ad4e", "#ffffff", "#ffffff"]
# 	available_line_colors = ["#5cb85c", "#5cb85c","#0275d8", "#0275d8", "#d9534f", "#d9534f", "#f0ad4e", "#f0ad4e", "#292b2c"]
# 	category_name_mappings = [(c.category_key, c.category_name) for c in user_categories]
# 	category_name_mappings.append(("Uncategorised", "Uncategorised"))

# 	# Prepare the by type plot
# 	by_type_df = pd.read_sql(exercises_by_type.statement, exercises_by_type.session.bind)
# 	by_type_pivot_df = by_type_df.pivot(index="exercise_type", columns="category_key", values="exercise_sets_count")
# 	by_type_pivot_df = by_type_pivot_df.fillna(value=0)
# 	by_type_categories = by_type_df["category_key"].unique()
# 	types = by_type_pivot_df.index.values

# 	by_type_data = {'exercise_type' : types}
# 	by_type_colors = []
# 	by_type_line_colors = []
# 	by_type_names = []

# 	for category in by_type_categories:
# 		by_type_data[category] = by_type_pivot_df[category].values
# 		category_index =  available_categories.index(category)
# 		by_type_colors.append(available_colors[category_index])
# 		by_type_line_colors.append(available_line_colors[category_index])
# 		by_type_names.append([mapping[1] for mapping in category_name_mappings if mapping[0]==category][0])

# 	plot_by_type = figure(y_range=types, plot_height=300, toolbar_location=None, tools="")
# 	plot_by_type.hbar_stack(by_type_categories, y='exercise_type', height=0.7, color=by_type_colors, source=by_type_data, line_color=by_type_line_colors, line_width=1.5)


# 	plot_by_type.x_range.start = 0
# 	#plot_by_type.y_range.range_padding = 0.1
# 	plot_by_type.ygrid.grid_line_color = None
# 	plot_by_type.axis.minor_tick_line_color = None
# 	plot_by_type.axis.axis_line_color = "#999999"
# 	plot_by_type.axis.major_label_text_color = "#666666"
# 	plot_by_type.axis.major_label_text_font_size = "7pt"
# 	plot_by_type.axis.major_tick_line_color = None
# 	plot_by_type.outline_line_color = None
# 	plot_by_type.sizing_mode = "scale_width"
# 	plot_by_type.title.text_font = "sans-serif"
# 	plot_by_type.title.text_font_style = "normal"

# 	plot_by_day = generate_stacked_bar_for_categories(dataset_query=exercises_by_category_and_day, user_categories=user_categories,
# 		dimension="exercise_date", measure="exercise_sets_count", dimension_type = "datetime", plot_height=200, bar_direction="vertical")

# 	# SPlit the plot components to pass into the template
# 	plot_by_day_script, plot_by_day_div = components(plot_by_day)
# 	plot_by_type_script, plot_by_type_div = components(plot_by_type)

# 	return render_template("chart.html", title="Exercises Data Viz", bars_count=0,
# 		plot_by_day_div=plot_by_day_div, plot_by_day_script=plot_by_day_script, plot_by_type_div=plot_by_type_div, plot_by_type_script=plot_by_type_script)