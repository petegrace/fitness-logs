from datetime import datetime, date, timedelta
import os
import calendar
import requests
import statistics
import time
import threading
from flask import render_template, flash, redirect, url_for, request, session, Response, jsonify, Markup
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from wtforms import HiddenField, SubmitField
import pandas as pd
from bokeh.embed import components
from bokeh.models import TapTool, CustomJS, Arrow, NormalHead, VeeHead
from app import app, db, utils, analysis, training_plan_utils
from app.auth.forms import RegisterForm
from app.auth.common import configured_google_client
from app.forms import LogNewExerciseTypeForm, EditExerciseForm, AddNewExerciseTypeForm, EditScheduledExerciseForm, ScheduledActivityForm, EditExerciseTypeForm, ExerciseCategoriesForm
from app.forms import ActivitiesCompletedGoalForm, TotalDistanceGoalForm, TotalMovingTimeGoalForm, TotalElevationGainGoalForm, CadenceGoalForm, GradientGoalForm, ExerciseSetsGoalForm
from app.models import User, ExerciseType, Exercise, ScheduledExercise, ExerciseCategory, Activity, ScheduledActivity, ActivityCadenceAggregate, ActivityPaceAggregate, CalendarDay, TrainingGoal, ExerciseForToday, ActivityForToday, TrainingPlanTemplate
from app.app_classes import TempCadenceAggregate, PlotComponentContainer
from app.dataviz import generate_stacked_bar_for_categories, generate_bar, generate_line_chart, generate_line_chart_for_categories
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
        'https://www.google-analytics.com/collect', data=data)


def goal_callback_function_js(modal_id, dimension_input_id, target_input_id):
	goal_callback = """
			$('{modal_id}').modal('show')
			selection = require('core/util/selection')
			indices = selection.get_indices(source)
			for (i = 0; i < indices.length; i++) {{
			    ind = indices[i]
			    selected_dimension_value = source.data['dimension'][ind]
			}}
			try {{
				goal_indices = selection.get_indices(goals_source)
				for (i = 0; i < goal_indices.length; i++) {{
				    ind = goal_indices[i]
				    selected_dimension_value = goals_source.data['dimension'][ind]
				    current_target = goals_source.data['measure'][ind] / 60
				}}
			}}
			catch(err) {{
				goal_indices = []
			}}
			$('{dimension_input_id}').val(selected_dimension_value)
			if (goal_indices.length > 0) {{
				$('{target_input_id}').val(current_target)
			}}
			else {{
				$('{target_input_id}').val('')
			}}
			""".format(modal_id=modal_id, dimension_input_id=dimension_input_id, target_input_id=target_input_id)

	return goal_callback


def handle_goal_form_post(form, current_week, goal_type, goal_metric, goal_metric_units, metric_multiplier, calculate_weekly_aggregations_function=None):
	if form.goal_relative_week.data == "this":
		goal_start_date = current_week.calendar_week_start_date
	elif form.goal_relative_week.data == "next":
		goal_start_date = current_week.calendar_week_start_date + timedelta(days=7)

	if form.get_dimension_value_input() is None:
		weekly_goal = current_user.training_goals.filter_by(goal_start_date=goal_start_date
			).filter_by(goal_metric=goal_metric).first()
	else:
		weekly_goal = current_user.training_goals.filter_by(goal_start_date=goal_start_date
			).filter_by(goal_metric=goal_metric
			).filter_by(goal_dimension_value=str(form.get_dimension_value_input().data)).first()

	if weekly_goal is not None:
		weekly_goal.goal_target = form.get_target_input().data * metric_multiplier
		track_event(category="Analysis", action="Existing weekly goal for {goal_type} updated".format(goal_type=goal_type), userId = str(current_user.id))
		flash("Updated {goal_type} goal for {dimension_value}".format(goal_type=goal_type, dimension_value=weekly_goal.goal_dimension_value))
	else:
		weekly_goal = TrainingGoal(owner=current_user,
									goal_period='week',
									goal_start_date=goal_start_date,
									goal_metric=goal_metric,
									goal_metric_units=goal_metric_units,
									goal_dimension_value=str(form.get_dimension_value_input().data) if form.get_dimension_value_input() is not None else None,
									goal_target=form.get_target_input().data * metric_multiplier,
									goal_status="In Progress",
									current_metric_value=0)
		db.session.add(weekly_goal)
		track_event(category="Analysis", action="New weekly goal for {goal_type} created".format(goal_type=goal_type), userId = str(current_user.id))
		flash("Created new {goal_type} goal for {dimension_value}".format(goal_type=goal_type, dimension_value=weekly_goal.goal_dimension_value))

	if not current_user.is_training_goals_user:
		current_user.is_training_goals_user = True

	db.session.commit()

	# Evaluate the goals in case there's already progress made
	analysis.evaluate_running_goals(week=goal_start_date, goal_metric=goal_metric, calculate_weekly_aggregations_function=calculate_weekly_aggregations_function)


# Routes
@app.route("/")
@app.route("/index")
def home():
	return render_template("auth/react_login.html")
	

# TODO: Change references from index/home to be something like "Activity Hub"
@app.route("/hub")
@login_required
def index():
	track_event(category="Main", action="Home page opened or refreshed", userId = str(current_user.id))
	page = request.args.get("page", 1, type=int)
	recent_activities = current_user.recent_activities().order_by(desc("created_datetime"), desc("activity_datetime")).paginate(page, app.config["EXERCISES_PER_PAGE"], False) # Pagination object
	next_url = url_for("index", page=recent_activities.next_num) if recent_activities.has_next else None
	prev_url = url_for("index", page=recent_activities.prev_num) if recent_activities.has_prev else None

	today = date.today()

	# Handle scenario of user not having had to log in since yesterday
	if current_user.last_login_date != today:
		training_plan_utils.refresh_plan_for_today(current_user)
		current_user.last_login_datetime = datetime.utcnow() # Treat it as a fresh login for logic and tracking purposes
		db.session.commit()

	current_day = calendar.day_abbr[today.weekday()]
	activities_for_today_remaining = current_user.activities_for_today_remaining().all()
	exercises_for_today_remaining = current_user.exercises_for_today_remaining().all()
	original_activities_for_today = current_user.activities_for_today().all()
	original_exercises_for_today = current_user.exercises_for_today().all()

	has_completed_schedule = False

	if not (exercises_for_today_remaining or activities_for_today_remaining):
		if (original_exercises_for_today or original_activities_for_today):
		   has_completed_schedule = True

	# Get the exercise types that aren't available from Training Plan box
	exercise_types = current_user.exercise_types_ordered().all()
	scheduled_exercises_remaining_type_ids = [scheduled_exercise.exercise_type_id for scheduled_exercise in exercises_for_today_remaining]
	other_exercise_types = [exercise_type for exercise_type in exercise_types if exercise_type.id not in scheduled_exercises_remaining_type_ids]

	
	# Check for the flags we're using to present modals for encouraging engagement
	is_new_user = request.args.get("is_new_user")
	if is_new_user and is_new_user == "True" and (current_user.id % 2) == 0: #It's coming from query param so is a string still
		show_new_user_modal = True # Only showing this to 50% of users for now to see how it performs
	else:
		show_new_user_modal = False

	show_post_import_modal = request.args.get("show_post_import_modal")
	if show_post_import_modal and show_post_import_modal == "True": #It's coming from query param so is a string still
		show_post_import_modal = True 
	else:
		show_post_import_modal = False

	is_not_using_categories = request.args.get("is_not_using_categories")
	if is_not_using_categories and is_not_using_categories == "True": #It's coming from query param so is a string still
		show_exercise_categories_modal = True
	else:
		show_exercise_categories_modal = False

	return render_template("index.html", title="Home", recent_activities=recent_activities.items, next_url=next_url, prev_url=prev_url, current_user=current_user,
							exercise_types=other_exercise_types, has_completed_schedule=has_completed_schedule,
							activities_for_today_remaining=activities_for_today_remaining, original_activities_for_today = original_activities_for_today,
							exercises_for_today_remaining=exercises_for_today_remaining, original_exercises_for_today = original_exercises_for_today,
							utils=utils, show_new_user_modal=show_new_user_modal, show_exercise_categories_modal=show_exercise_categories_modal, show_post_import_modal=show_post_import_modal)


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

	flash(Markup("Added {type}. (<a href='{url}'>Edit</a>)".format(type=exercise.type.name, url=url_for("edit_exercise", id=exercise.id))))
	return redirect(url_for("index"))


@app.route("/new_exercise/<context>/<selected_day>", methods=["GET", "POST"])
@app.route("/new_exercise/<context>", methods=["GET", "POST"])
@login_required
def new_exercise(context, selected_day=None):
	if context == "logging":
		form = LogNewExerciseTypeForm()
	else:
		form = AddNewExerciseTypeForm()

	# Bit of a hack to reduce avoid duplicate errors when unioning exercises and activities
	category_choices = [(str(category.id), category.category_name) for category in current_user.exercise_categories.filter(ExerciseCategory.category_name.notin_(["Run", "Ride", "Swim"])).all()]
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

			if current_user.is_exercises_user == False:
				current_user.is_exercises_user = True

			db.session.commit()
			flash(Markup("Added {type}. (<a href='{url}'>Edit</a>)".format(type=exercise.type.name, url=url_for("edit_exercise", id=exercise.id))))
	
			# Show a modal to encourage use of categories after a certain number of exercise types have been used
			if current_user.is_categories_user == False:
				exercise_types_count = len(current_user.exercise_types.all())
				if exercise_types_count == 3 or exercise_types_count == 10 or exercise_types_count == 20:
					return redirect(url_for("index", is_not_using_categories=True))

			return redirect(url_for("index"))
		elif context == "scheduling":
			scheduled_exercise = ScheduledExercise(type=exercise_type,
												   scheduled_day=selected_day,
												   sets=1,
												   reps=form.reps.data,
												   seconds=form.seconds.data)
			db.session.add(scheduled_exercise)

			if selected_day == calendar.day_abbr[date.today().weekday()]:
				training_plan_utils.add_to_plan_for_today(current_user, selected_day)

			if current_user.is_training_plan_user == False:
				current_user.is_training_plan_user = True

			db.session.commit()
			flash("Added {type} and scheduled for {scheduled_day}".format(type=exercise_type.name, scheduled_day=scheduled_exercise.scheduled_day))
			
			# Show a modal to encourage use of categories after a certain number of exercise types have been used
			if current_user.is_categories_user == False:
				exercise_types_count = len(current_user.exercise_types.all())
				if exercise_types_count == 3 or exercise_types_count == 10 or exercise_types_count == 20:
					return redirect(url_for("schedule", schedule_freq="weekly", selected_day=selected_day, is_not_using_categories=True))
			
			return redirect(url_for("schedule", schedule_freq="weekly", selected_day=selected_day))
		else: # Only the exercise type to create
			db.session.commit()
			flash("Added {type}".format(type=exercise_type.name))
			return redirect(url_for("exercise_types"))

	#for the get...
	form.user_categories_count.data = len(category_choices)
	track_event(category="Exercises", action="New Exercise form loaded for {context}".format(context=context), userId = str(current_user.id))
	return render_template("new_exercise.html", title="Add New Exercise Type", form=form, context=context)


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
		flash("Updated {type}".format(type=exercise.type.name, datetime=exercise.exercise_datetime))

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


@app.route("/weekly_activity/<year>", methods=['GET', 'POST'])
@app.route("/weekly_activity/<year>/<week>", methods=['GET', 'POST'])
@login_required
def weekly_activity(year, week=None): 
	track_event(category="Analysis", action="Weekly Activity page opened or refreshed", userId = str(current_user.id))
	activities_completed_goal_form = ActivitiesCompletedGoalForm()
	total_distance_goal_form = TotalDistanceGoalForm()
	total_moving_time_goal_form = TotalMovingTimeGoalForm()
	total_elevation_gain_goal_form = TotalElevationGainGoalForm()
	cadence_goal_form = CadenceGoalForm()
	gradient_goal_form = GradientGoalForm()
	exercise_sets_goal_form = ExerciseSetsGoalForm()

	total_distance_goal_form.target_distance.label.text = total_distance_goal_form.target_distance.label.text + " ({uom})".format(uom=current_user.distance_uom_preference)
	activities_completed_goal_form.minimum_distance.label.text = activities_completed_goal_form.minimum_distance.label.text + " ({uom})".format(uom=current_user.distance_uom_preference)
	total_elevation_gain_goal_form.target_elevation_gain.label.text = total_elevation_gain_goal_form.target_elevation_gain.label.text + " ({uom})".format(uom=current_user.elevation_uom_preference)

	if year == "current":
		year = utils.current_year()

	# Bit of a hack to reduce avoid duplicate errors when unioning exercises and activities
	category_choices = [(str(category.id), category.category_name) for category in current_user.exercise_categories.filter(ExerciseCategory.category_name.notin_(["Run", "Ride", "Swim"])).all()]
	exercise_sets_goal_form.exercise_category_id.choices = category_choices

	# Sort out our week and year-related stuff
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

	# Create a new runs/activities completed goal
	if activities_completed_goal_form.validate_on_submit():
		handle_goal_form_post(form=activities_completed_goal_form, current_week=week_options[0], goal_type="runs completed", goal_metric="Runs Completed Over Distance", goal_metric_units="runs", metric_multiplier = 1,
							calculate_weekly_aggregations_function=None)

	# Create a new distance goal
	if total_distance_goal_form.validate_on_submit():
		metric_multiplier = 1609.344 if current_user.distance_uom_preference == "miles" else 1000
		handle_goal_form_post(form=total_distance_goal_form, current_week=week_options[0], goal_type="weekly distance", goal_metric="Weekly Distance", goal_metric_units="metres", metric_multiplier = metric_multiplier)

	# Create a new moving time goal
	if total_moving_time_goal_form.validate_on_submit():
		handle_goal_form_post(form=total_moving_time_goal_form, current_week=week_options[0], goal_type="weekly moving time", goal_metric="Weekly Moving Time", goal_metric_units="seconds", metric_multiplier = 60)

	# Create a new elevation gain goal
	if total_elevation_gain_goal_form.validate_on_submit():
		metric_multiplier = (1 / 3.28084) if current_user.elevation_uom_preference == "feet" else 1
		handle_goal_form_post(form=total_elevation_gain_goal_form, current_week=week_options[0], goal_type="weekly elevation gain", goal_metric="Weekly Elevation Gain", goal_metric_units="metres", metric_multiplier = metric_multiplier)

	# Create a new cadence goal or update an existing one if it's a post
	if cadence_goal_form.validate_on_submit():
		handle_goal_form_post(form=cadence_goal_form, current_week=week_options[0], goal_type="cadence", goal_metric="Time Spent Above Cadence", goal_metric_units="seconds", metric_multiplier = 60,
							calculate_weekly_aggregations_function=analysis.calculate_weekly_cadence_aggregations)

	# Create a new cadence goal or update an existing one if it's a post
	if gradient_goal_form.validate_on_submit():
		handle_goal_form_post(form=gradient_goal_form, current_week=week_options[0], goal_type="gradient", goal_metric="Distance Climbing Above Gradient", goal_metric_units="metres", metric_multiplier = 1000,
							calculate_weekly_aggregations_function=analysis.calculate_weekly_gradient_aggregations)

	# Create a new exercise sets goal for or update an existing one if it's a post
	if exercise_sets_goal_form.validate_on_submit():
		if exercise_sets_goal_form.goal_relative_week.data == "this":
			goal_start_date = week_options[0].calendar_week_start_date
		elif exercise_sets_goal_form.goal_relative_week.data == "next":
			goal_start_date = week_options[0].calendar_week_start_date + timedelta(days=7)

		weekly_goal = current_user.training_goals.filter_by(goal_start_date=goal_start_date
			).filter_by(goal_metric="Exercise Sets Completed"
			).filter_by(goal_dimension_value=str(exercise_sets_goal_form.exercise_category_id.data)).first()
		if weekly_goal is not None:
			weekly_goal.goal_target = exercise_sets_goal_form.target_sets_to_complete.data
			track_event(category="Analysis", action="Existing weekly goal for exerise sets updated", userId = str(current_user.id))
			flash("Updated goal for exercise sets completed")
		else:
			weekly_goal = TrainingGoal(owner=current_user,
									   goal_period='week',
									   goal_start_date=goal_start_date,
									   goal_metric="Exercise Sets Completed",
									   goal_metric_units="sets",
									   goal_dimension_value=str(exercise_sets_goal_form.exercise_category_id.data),
									   goal_target=exercise_sets_goal_form.target_sets_to_complete.data,
									   goal_status="In Progress",
									   current_metric_value=0)
			db.session.add(weekly_goal)
			track_event(category="Analysis", action="New weekly goal for exercise sets created", userId = str(current_user.id))
			flash("Created new goal for exercise sets completed")

		if not current_user.is_training_goals_user:
			current_user.is_training_goals_user = True
			
		db.session.commit()

	# Now start getting the data that we need for a get (as well as after a post)
	days = CalendarDay.query.filter_by(calendar_week_start_date=current_week).order_by(CalendarDay.calendar_date.desc()).all()

	all_exercises = current_user.exercises().all()
	all_activities = current_user.activities.all()
	categories = current_user.exercise_categories.all()

	current_week_dataset = []
	current_week_activity_count = 0 # for plotting the current week indicator at the right height on the graph

	for day in days:
		exercises_by_category = []
		# Create dictionaries of exercises for each category
		for category in categories:
			category_exercises = [exercise for exercise in all_exercises if exercise.exercise_date==day.calendar_date and exercise.type.exercise_category==category]
			if len(category_exercises) > 0:
				category_detail = dict(category=category,
						  			   exercise_count=len(category_exercises),
									   exercises=category_exercises)
				exercises_by_category.append(category_detail)
				current_week_activity_count += 1
		# Create similar dictionary for uncategorised
		uncategorised_exercises = [exercise for exercise in all_exercises if exercise.exercise_date==day.calendar_date and exercise.type.exercise_category is None]
		if len(uncategorised_exercises) > 0:
			category_detail = dict(category=None,
					  			   exercise_count=len(uncategorised_exercises),
								   exercises=uncategorised_exercises)
			exercises_by_category.append(category_detail)
			current_week_activity_count += 1
		# Grab the activities without worrying about categories
		day_activities = [activity for activity in all_activities if activity.activity_date==day.calendar_date]
		current_week_activity_count += len(day_activities)

		if day.calendar_date > date.today():
			scheduled_activities = current_user.scheduled_activities_filtered(day.day_of_week).all()
			scheduled_exercise_categories = current_user.scheduled_exercise_categories(day.day_of_week).all()
		else:
			scheduled_activities = []
			scheduled_exercise_categories = []

		# Construct a dictionary for the day as a whole
		day_detail = dict(day=day,
						  exercises_by_category=exercises_by_category,
						  activities=day_activities,
						  scheduled_activities=scheduled_activities,
						  scheduled_exercise_categories=scheduled_exercise_categories)
		current_week_dataset.append(day_detail)

	# Evaluate the exercise sets goals at this point
	analysis.evaluate_exercise_set_goals(current_week)

	# Get the category in use for runs so we can use across run-related charts
	run_category = ExerciseCategory.query.filter(ExerciseCategory.owner == current_user).filter(ExerciseCategory.category_name == "Run").first()

	if run_category is not None:
		run_fill_color = run_category.fill_color
		run_line_color = run_category.line_color
	else:
		run_fill_color = None
		run_line_color = None

	# Data for the summary stats
	summary_stats = current_user.weekly_activity_type_stats(week=current_week).all()
	
	# Data and plotting for weekly cadence analysis graph
	weekly_cadence_goals = current_user.training_goals.filter_by(goal_start_date=current_week).filter_by(goal_metric="Time Spent Above Cadence").all()

	if len(weekly_cadence_goals) == 0:
		weekly_cadence_goals = None

	weekly_cadence_aggregations = analysis.calculate_weekly_cadence_aggregations(current_week)

	if len(weekly_cadence_aggregations["summary"]) == 0:
		above_cadence_plot_script=None
		above_cadence_plot_div=None
	else:
		weekly_cadence_summary = weekly_cadence_aggregations["summary"]
		min_significant_cadence = weekly_cadence_aggregations["min_significant_cadence"]
		max_significant_cadence = weekly_cadence_aggregations["max_significant_cadence"]

		set_cadence_goal_callback = """
			$('#setCadenceGoal-modal').modal('show')
			selection = require('core/util/selection')
			indices = selection.get_indices(source)
			for (i = 0; i < indices.length; i++) {{
			    ind = indices[i]
			    selected_cadence = source.data['dimension'][ind]
			}}
			try {{
				goal_indices = selection.get_indices(goals_source)
				for (i = 0; i < goal_indices.length; i++) {{
				    ind = goal_indices[i]
				    selected_cadence = goals_source.data['dimension'][ind]
				    current_target = goals_source.data['measure'][ind] / 60
				}}
			}}
			catch(err) {{
				goal_indices = []
			}}
			$('#cadence').val(selected_cadence)
			if (goal_indices.length > 0) {{
				$('#target_minutes_above_cadence').val(current_target)
			}}
			else {{
				$('#target_minutes_above_cadence').val('')
			}}
			"""

		max_dimension_range = (min_significant_cadence, max_significant_cadence)
		above_cadence_plot = generate_bar(dataset=weekly_cadence_summary, plot_height=120, dimension_name="cadence", measure_name="total_seconds_above_cadence",
				measure_label_function=utils.convert_seconds_to_minutes_formatted, fill_color=run_fill_color, line_color=run_line_color, max_dimension_range=max_dimension_range,
				goals_dataset=weekly_cadence_goals, tap_tool_callback=set_cadence_goal_callback)
		above_cadence_plot_script, above_cadence_plot_div = components(above_cadence_plot)

	# Data and plotting for historic performance against current cadence goals
	cadence_goal_history_charts = analysis.get_cadence_goal_history_charts(week=current_week)

	# Data and plotting for weekly gradient analysis graph
	weekly_gradient_goals = current_user.training_goals.filter_by(goal_start_date=current_week).filter_by(goal_metric="Distance Climbing Above Gradient").all()

	if len(weekly_gradient_goals) == 0:
		weekly_gradient_goals = None

	weekly_gradient_aggregations = analysis.calculate_weekly_gradient_aggregations(current_week)

	if len(weekly_gradient_aggregations["summary"]) == 0:
		above_gradient_plot_script=None
		above_gradient_plot_div=None
	else:
		weekly_gradient_summary = weekly_gradient_aggregations["summary"]
		min_significant_gradient = weekly_gradient_aggregations["min_significant_gradient"]
		max_significant_gradient = weekly_gradient_aggregations["max_significant_gradient"]

		set_gradient_goal_callback = goal_callback_function_js(modal_id="#setGradientGoal-modal", dimension_input_id="#gradient", target_input_id="#target_km_above_gradient")

		max_dimension_range = (min_significant_gradient, max_significant_gradient+0.4)
		above_gradient_plot = generate_bar(dataset=weekly_gradient_summary, plot_height=120, dimension_name="gradient", measure_name="total_metres_above_gradient",
				measure_label_function=utils.format_distance, fill_color=run_fill_color, line_color=run_line_color,
				dimension_interval=1, max_dimension_range=max_dimension_range,
				goals_dataset=weekly_gradient_goals, tap_tool_callback=set_gradient_goal_callback)
		above_gradient_plot_script, above_gradient_plot_div = components(above_gradient_plot)
	
	above_gradient_plot_container = PlotComponentContainer(name="Distance Climbing above Gradient %", plot_div=above_gradient_plot_div, plot_script=above_gradient_plot_script)

	# Data and plotting for historic performance against current gradient goals
	gradient_goal_history_charts = analysis.get_goal_history_charts(week=current_week, goal_metric="Distance Climbing Above Gradient")

	# Data and plotting for the exercise sets by day graph
	exercises_by_category_and_day = current_user.exercises_by_category_and_day(week=current_week)
	weekly_exercise_set_goals = current_user.training_goals.filter_by(goal_start_date=current_week).filter_by(goal_metric="Exercise Sets Completed").all()

	# Data and plotting for historic performance against current exercise set goals
	exercise_set_goal_history_charts = analysis.get_goal_history_charts(week=current_week, goal_metric="Exercise Sets Completed")

	if len(exercises_by_category_and_day.all()) == 0:
		exercise_sets_plot_script = None
		exercise_sets_plot_div = None
	else:
		user_categories = current_user.exercise_categories.all()
		set_exercise_sets_goal_callback = """
				$('#setExerciseSetsGoal-modal').modal('show')
				"""

		exercise_sets_plot = generate_line_chart_for_categories(dataset_query=exercises_by_category_and_day, user_categories=user_categories,
			dimension="exercise_date", measure="exercise_sets_count", dimension_type = "datetime", plot_height=120, line_type="cumulative", goals_dataset=weekly_exercise_set_goals,
			tap_tool_callback=set_exercise_sets_goal_callback)
		exercise_sets_plot_script, exercise_sets_plot_div = components(exercise_sets_plot)

	# Data and plotting for the goals graph
	goals_for_week = current_user.training_goals.filter(TrainingGoal.goal_start_date == current_week).all()
	if len(goals_for_week) == 0:
		current_goals_plot_script = None
		current_goals_plot_div = None
	else:
		current_goals_plot = generate_bar(dataset=goals_for_week, plot_height=120, dimension_name="goal_description", measure_name="percent_progress",
					measure_label_function=utils.format_percentage_labels, dimension_type="discrete", category_field="goal_category",
					goals_dataset=goals_for_week, goal_measure_type="percent", goal_dimension_type="description", goal_label_function=utils.format_goal_units)
		current_goals_plot_script, current_goals_plot_div = components(current_goals_plot)


	# Graph of activity by week for the year so we can provide navigation at the top
	weekly_summary = current_user.weekly_activity_summary(year=year)
	weekly_summary_plot, source = generate_stacked_bar_for_categories(dataset_query=weekly_summary, user_categories=categories,
		dimension="week_start_date", measure="total_activities", measure_units="activities", dimension_type = "datetime", plot_height=100, bar_direction="vertical",
		granularity="week", show_grid=False, show_yaxis=False)

	# TODO: extra stuff for the data viz should should be refactored into dataviz now we've shown we can pass the callback in as a parameter
	weekly_summary_callback_code = """
		selection = require('core/util/selection')
		indices = selection.get_indices(source)
		for (i = 0; i < indices.length; i++) {{
		    ind = indices[i]
		    url = "/weekly_activity/{year}/" + source.data['week_start_date'][ind]
		    window.open(url, "_self")
		}}
		""".format(year=year)

	tap_tool = weekly_summary_plot.select(type=TapTool)
	tap_tool.callback = CustomJS(args=dict(source=source), code=weekly_summary_callback_code)

	weekly_summary_plot.add_layout(Arrow(end=VeeHead(fill_color="#999999"),
                   x_start=current_week_ms, y_start=current_week_activity_count+0.1, x_end=current_week_ms, y_end=current_week_activity_count))

	weekly_summary_plot_script, weekly_summary_plot_div = components(weekly_summary_plot)

	return render_template("weekly_activity.html", title="Weekly Activity", utils=utils, current_user=current_user,
		weekly_summary=weekly_summary, weekly_summary_plot_script=weekly_summary_plot_script, weekly_summary_plot_div=weekly_summary_plot_div,
		year_options=year_options, week_options=week_options, current_year=int(year), current_week=current_week, current_week_dataset=current_week_dataset,
		summary_stats=summary_stats, activities_completed_goal_form=activities_completed_goal_form, total_distance_goal_form=total_distance_goal_form,
		total_moving_time_goal_form=total_moving_time_goal_form, total_elevation_gain_goal_form=total_elevation_gain_goal_form,
		above_cadence_plot_script=above_cadence_plot_script, above_cadence_plot_div=above_cadence_plot_div, cadence_goal_form=cadence_goal_form,
		above_gradient_plot_container = above_gradient_plot_container, gradient_goal_form=gradient_goal_form, gradient_goal_history_charts=gradient_goal_history_charts,
		exercise_sets_plot_script=exercise_sets_plot_script, exercise_sets_plot_div=exercise_sets_plot_div, exercise_sets_goal_form=exercise_sets_goal_form,
		current_goals_plot_script=current_goals_plot_script, current_goals_plot_div=current_goals_plot_div,
		cadence_goal_history_charts=cadence_goal_history_charts, exercise_set_goal_history_charts=exercise_set_goal_history_charts)


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


@app.route("/training_plan")
@login_required
def training_plan():
	track_event(category="Schedule", action="Training plan opened", userId = str(current_user.id))
	return render_template("training_plan.html", title="Training Plan"
	)

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

	scheduled_exercises = current_user.scheduled_exercises(selected_day).all()
	scheduled_activities = current_user.scheduled_activities_filtered(selected_day).all()

	activity_types = current_user.exercise_categories.filter(ExerciseCategory.category_name.in_(["Run", "Ride", "Swim"])).all()
	exercise_types = current_user.exercise_types_ordered()

	templates = TrainingPlanTemplate.query.all()

	# Determine whether to show modal to encourage use of categories
	is_not_using_categories = request.args.get("is_not_using_categories")
	if is_not_using_categories and is_not_using_categories == "True": #It's coming from query param so is a string still
		show_exercise_categories_modal = True
	else:
		show_exercise_categories_modal = False

	return render_template("schedule.html", title="Schedule", schedule_days=days, schedule_freq=schedule_freq, selected_day=selected_day,
				scheduled_exercises=scheduled_exercises, scheduled_activities=scheduled_activities, templates=templates,
				exercise_types=exercise_types, activity_types=activity_types, show_exercise_categories_modal=show_exercise_categories_modal)


@app.route('/schedule_activity/<activity_type>/<selected_day>', methods=['GET', 'POST'])
@login_required
def schedule_activity(activity_type, selected_day):
	form = ScheduledActivityForm()
	scheduled_activity = ScheduledActivity.query.filter_by(owner=current_user).filter_by(activity_type=activity_type).filter_by(scheduled_day=selected_day).first()

	if form.validate_on_submit():
		if scheduled_activity:
			# edit
			track_event(category="Schedule", action="Scheduled activity updated", userId = str(current_user.id))
			scheduled_activity.activity_type = activity_type
			scheduled_activity.scheduled_day = selected_day
			scheduled_activity.description = form.description.data
			scheduled_activity.planned_distance = (form.planned_distance.data*1000) if form.planned_distance.data else None
			scheduled_activity.is_removed = False
			db.session.commit()
			flash("Updated {activity_type} scheduled for {day}".format(activity_type=scheduled_activity.activity_type, day=scheduled_activity.scheduled_day))
		else:
			# create
			track_event(category="Schedule", action="Scheduled activity created", userId = str(current_user.id))
			scheduled_activity = ScheduledActivity(activity_type=activity_type,
												owner=current_user,
												scheduled_day=selected_day,
												description=form.description.data,
												planned_distance=(form.planned_distance.data*1000) if form.planned_distance.data else None)
			db.session.add(scheduled_activity)
			db.session.commit()
			flash("Created {activity_type} scheduled for {day}".format(activity_type=scheduled_activity.activity_type, day=scheduled_activity.scheduled_day))

		if selected_day == calendar.day_abbr[date.today().weekday()]:
			training_plan_utils.add_to_plan_for_today(current_user, selected_day)

		if current_user.is_training_plan_user == False:
			current_user.is_training_plan_user = True
			db.session.commit()

		return redirect(url_for("schedule", schedule_freq="weekly", selected_day=scheduled_activity.scheduled_day))

	# If it's a get...
	if scheduled_activity:
		form.description.data = scheduled_activity.description
		form.planned_distance.data = int(scheduled_activity.planned_distance / 1000) if scheduled_activity.planned_distance else None
		
	track_event(category="Schedule", action="Scheduled Activity form loaded", userId = str(current_user.id))
	return render_template("schedule_activity.html", title="Schedule Activity", form=form, activity_type=activity_type, selected_day=selected_day)


@app.route('/remove_scheduled_activity/<id>')
@login_required
def remove_scheduled_activity(id):
	scheduled_activity = ScheduledActivity.query.get(int(id))
	track_event(category="Schedule", action="Scheduled activity removed", userId = str(current_user.id))

	scheduled_activity.is_removed = True
	db.session.commit()
	flash("Removed activity {activity_type} from schedule for {day}".format(activity_type=scheduled_activity.activity_type, day=scheduled_activity.scheduled_day))

	return redirect(url_for("schedule", schedule_freq="weekly", selected_day=scheduled_activity.scheduled_day))


@app.route('/remove_activity_for_today/<id>')
@login_required
def remove_activity_for_today(id):
	activity_for_today = ActivityForToday.query.get(int(id))
	track_event(category="Schedule", action="Activity for today removed", userId = str(current_user.id))
	flash("Removed activity {activity_type} from today's planned exercises".format(activity_type=activity_for_today.scheduled_activity.activity_type))

	db.session.delete(activity_for_today)
	db.session.commit()

	return redirect(url_for("index"))


@app.route("/schedule_exercise/<id>/<selected_day>")
@login_required
def schedule_exercise(id, selected_day):
	exercise_type = ExerciseType.query.get(int(id))

	scheduled_exercise = ScheduledExercise.query.filter(ExerciseType.owner==current_user).filter_by(type=exercise_type).filter_by(scheduled_day=selected_day).first()

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

		if current_user.is_training_plan_user == False:
			current_user.is_training_plan_user = True

	db.session.commit()

	if selected_day == calendar.day_abbr[date.today().weekday()]:
		training_plan_utils.add_to_plan_for_today(current_user, selected_day)

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


@app.route('/remove_exercise_for_today/<id>')
@login_required
def remove_exercise_for_today(id):
	exercise_for_today = ExerciseForToday.query.get(int(id))
	track_event(category="Schedule", action="Exercise for today removed", userId = str(current_user.id))
	flash("Removed exercise {exercise} from today's planned exercises".format(exercise=exercise_for_today.scheduled_exercise.type.name))

	db.session.delete(exercise_for_today)
	db.session.commit()

	return redirect(url_for("index"))


@app.route('/add_to_today/<selected_day>')
@login_required
def add_to_today(selected_day):
	track_event(category="Schedule", action="Added another day's exercises to today's plan", userId = str(current_user.id))	
	training_plan_utils.add_to_plan_for_today(current_user, selected_day)
	flash("Added activities and exercises from {selected_day} to today's plan".format(selected_day=selected_day))

	return redirect(url_for("index"))


@app.route("/exercise_types")
@login_required
def exercise_types():
	track_event(category="Manage", action="Exercise Types page loaded", userId = str(current_user.id))
	exercise_types = current_user.exercise_types_active().order_by(ExerciseType.name).all()
	archived_exercise_types = current_user.exercise_types_archived().order_by(ExerciseType.name).all()

	return render_template("exercise_types.html", title="Exercise Types", exercise_types=exercise_types, archived_exercise_types=archived_exercise_types)


@app.route('/edit_exercise_type/<id>', methods=['GET', 'POST'])
@login_required
def edit_exercise_type(id):
	exercise_type = ExerciseType.query.get(int(id))

	# Create the form with a default category selection, other defaults get set further down
	form = EditExerciseTypeForm(exercise_category_id = exercise_type.exercise_category_id)
	category_choices = [(str(category.id), category.category_name) for category in current_user.exercise_categories.filter(ExerciseCategory.category_name.notin_(["Run", "Ride", "Swim"])).all()]
	form.exercise_category_id.choices = category_choices

	
	if form.validate_on_submit():
		track_event(category="Manage", action="Exercise Type updated", userId = str(current_user.id))

		# Ensure that seconds and reps are none if the other is selected
		if form.measured_by.data == "reps":
			form.default_seconds.data = None
		elif form.measured_by.data == "seconds":
			form.default_reps.data = None

		exercise_type.name = form.name.data
		exercise_type.measured_by = form.measured_by.data
		exercise_type.default_reps = form.default_reps.data
		exercise_type.default_seconds = form.default_seconds.data
		if form.exercise_category_id.data != "None": 
			exercise_type.exercise_category_id = form.exercise_category_id.data
		db.session.commit()
		flash("Updated {name}".format(name=exercise_type.name))

		return redirect(url_for("exercise_types"))

	# If it's a get...
	form.exercise_type_id.data = exercise_type.id
	form.user_categories_count.data = len(category_choices)
	form.name.data = exercise_type.name
	form.measured_by.data = exercise_type.measured_by
	form.default_reps.data = exercise_type.default_reps
	form.default_seconds.data = exercise_type.default_seconds

	track_event(category="Manage", action="Edit Exercise Type form loaded", userId = str(current_user.id))
	return render_template("edit_exercise_type.html", title="Edit Exercise Type", form=form, exercise_name=exercise_type.name)


@app.route("/archive_exercise_type/<id>")
@login_required
def archive_exercise_type(id):
	track_event(category="Manage", action="Archived exercise type", userId = str(current_user.id))
	exercise_type = ExerciseType.query.get(int(id))
	exercise_type.is_archived = True
	db.session.commit()

	flash("{exercise_type} has been archived and will be hidden from your available exercises.You can reinstate it from the Archived Exercises section".format(exercise_type=exercise_type.name))
	return redirect(url_for("exercise_types"))


@app.route("/reinstate_exercise_type/<id>")
@login_required
def reinstate_exercise_type(id):
	track_event(category="Manage", action="Reinstated exercise type", userId = str(current_user.id))
	exercise_type = ExerciseType.query.get(int(id))
	exercise_type.is_archived = False
	db.session.commit()

	flash("{exercise_type} has been reinstated and is available again for logging and scheduling".format(exercise_type=exercise_type.name))
	return redirect(url_for("exercise_types"))
	

@app.route("/categories", methods=['GET', 'POST'])
@login_required
def categories():
	categories_form = ExerciseCategoriesForm()
	current_categories = current_user.exercise_categories

	if categories_form.validate_on_submit():
		track_event(category="Manage", action="Category changes saved", userId = str(current_user.id))

		category_keys = [field_name for field_name in dir(categories_form) if field_name.startswith("cat_")]

		# Lists to use for looking up colour attributes for each category
		available_categories = ["cat_green", "cat_green_outline", "cat_blue", "cat_blue_outline", "cat_red", "cat_red_outline", "cat_yellow", "cat_yellow_outline", "Uncategorised"]
		available_fill_colors = ["#588157", "#ffffff", "#3f7eba", "#ffffff", "#ef6461", "#ffffff", "#e4b363", "#ffffff", "#ffffff"]
		available_line_colors = ["#588157", "#588157","#3f7eba", "#3f7eba", "#ef6461", "#ef6461", "#e4b363", "#e4b363", "#292b2c"]

		for category_key in category_keys:
			if categories_form[category_key].data != "":
				category = current_categories.filter_by(category_key=category_key).first()
				category_index =  available_categories.index(category_key)

				if category:
					category.category_name = categories_form[category_key].data
					category.fill_color = available_fill_colors[category_index]
					category.line_color = available_line_colors[category_index]
				else:
					category = ExerciseCategory(owner=current_user,
												category_key=category_key,
												category_name=categories_form[category_key].data,
												fill_color=available_fill_colors[category_index],
												line_color=available_line_colors[category_index])
			elif categories_form[category_key].data == "":
				category = current_categories.filter_by(category_key=category_key).first()

				if category:
					db.session.delete(category)

		if not current_user.is_categories_user:
			current_user.is_categories_user = True

		db.session.commit()

		flash("Changes to Exercise Categories have been saved.")
		return redirect(url_for("exercise_types"))

	# If it's a get...
	for current_category in current_categories:
		categories_form[current_category.category_key].data = current_category.category_name

	# Check for the show modal params and generate modal if True
	show_strava_categories_modal = request.args.get("show_strava_categories_modal")
	if show_strava_categories_modal and show_strava_categories_modal == "True": #It's coming from query param so is a string still
		show_strava_categories_modal = True
	else:
		show_strava_categories_modal = False
	
	show_exercise_categories_modal = request.args.get("show_exercise_categories_modal")
	if show_exercise_categories_modal and show_exercise_categories_modal == "True": #It's coming from query param so is a string still
		show_exercise_categories_modal = True
	else:
		show_exercise_categories_modal = False

	track_event(category="Manage", action="Exercise Categories page loaded", userId = str(current_user.id))
	return render_template("categories.html", title="Manage Exercise Categories", categories_form=categories_form,
			show_strava_categories_modal=show_strava_categories_modal, show_exercise_categories_modal=show_exercise_categories_modal)


@app.route("/copy_template_to_schedule/<template_id>")
@login_required
def copy_template_to_schedule(template_id):
	track_event(category="Schedule", action="Attempting to copy training plan from template", userId = str(current_user.id))
	template = TrainingPlanTemplate.query.get(int(template_id))

	# Create the categories used by the template
	if current_user.unused_category_keys().count() < template.template_exercise_categories.count():
		flash("Not enough spare exercise categories to copy template.")
		track_event(category="Schedule", action="Not enough spare exercise categories to copy template.", userId = str(current_user.id))
		return redirect(url_for("schedule", schedule_freq="weekly"))	
	else:
		new_exercise_types_count = 0

		for template_category in template.template_exercise_categories.all():
			if template_category.category_name not in [category.category_name for category in current_user.exercise_categories.all()]:
				unused_category_key = current_user.unused_category_keys().first()
				new_category = ExerciseCategory(owner=current_user,
												category_key=unused_category_key.category_key,
												category_name=template_category.category_name,
												fill_color=unused_category_key.fill_color,
												line_color=unused_category_key.line_color)
				db.session.add(new_category)
				flash("Added new category of {category_name} from {template} template".format(category_name=template_category.category_name, template=template.name))
			else:
				new_category = ExerciseCategory.query.filter_by(owner=current_user).filter_by(category_name=template_category.category_name).first()
			
			# Create the exercise types associated with that category
			for template_exercise_type in template_category.template_exercise_types.all():
				if template_exercise_type.name not in [exercise_type.name for exercise_type in current_user.exercise_types.all()]:
					new_exercise_type = ExerciseType(name=template_exercise_type.name,
													 owner=current_user,
													 exercise_category_id=new_category.id,
													 measured_by=template_exercise_type.measured_by,
													 default_reps=template_exercise_type.default_reps,
													 default_seconds=template_exercise_type.default_seconds)

					db.session.add(new_exercise_type)
					new_exercise_types_count += 1
				else:
					new_exercise_type = ExerciseType.query.filter_by(owner=current_user).filter_by(name=template_exercise_type.name).first()
				
				# Add the exercise to the schedule on the required days
				for template_scheduled_exercise in template_exercise_type.template_scheduled_exercises:
					scheduled_exercise = ScheduledExercise.query.filter(ExerciseType.owner==current_user
							).filter_by(is_removed=False
							).filter_by(type=new_exercise_type
							).filter_by(scheduled_day=template_scheduled_exercise.scheduled_day
							).first()

					if not scheduled_exercise:
						scheduled_exercise = ScheduledExercise(type=new_exercise_type,
															   scheduled_day=template_scheduled_exercise.scheduled_day,
															   sets=template_exercise_type.default_sets,
															   reps=new_exercise_type.default_reps,
															   seconds=new_exercise_type.default_seconds)
						db.session.add(scheduled_exercise)	

		if not current_user.is_training_plan_user:
			current_user.is_training_plan_user = True

		flash("Added {count} new exercise type(s) from {template} template and scheduled in training plan".format(count=new_exercise_types_count, template=template.name))
		db.session.commit()

	track_event(category="Schedule", action="Completed copying training plan from template", userId = str(current_user.id))

	# Send the user back to the schedule page
	return redirect(url_for("schedule", schedule_freq="weekly"))	


@app.route("/import_strava_activity")
@login_required
def import_strava_activity():
	track_event(category="Strava", action="Starting import of Strava activity", userId = str(current_user.id))
	strava_client = Client()

	if not session.get("strava_access_token"):
		return redirect(url_for("connect_strava", action="authorize"))

	access_token = session["strava_access_token"]
	strava_client.access_token = access_token

	try:
		athlete = strava_client.get_athlete()
	except:
		return redirect(url_for("connect_strava", action="authorize"))

	most_recent_strava_activity_datetime = current_user.most_recent_strava_activity_datetime()

	# Start from 2000 if no imported activities
	most_recent_strava_activity_datetime = datetime(2000,1,1) if most_recent_strava_activity_datetime is None else most_recent_strava_activity_datetime

	activities = strava_client.get_activities(after = most_recent_strava_activity_datetime)
	activities_list = list(activities)

	new_activity_count = 0

	for strava_activity in activities_list:
		# if the start_datetime is today then check if there's a scheduled activity in today's plan
		if strava_activity.start_date.date() == date.today():
			scheduled_activity = current_user.activities_for_today_remaining(activity_type=strava_activity.type).first()
		else:
			scheduled_activity = None
		

		activity = Activity(external_source = "Strava",
							external_id = strava_activity.id,
							owner = current_user,
							scheduled_activity_id = scheduled_activity.id if scheduled_activity else None,
							name = strava_activity.name,
							start_datetime = strava_activity.start_date,
							activity_type = strava_activity.type,
							is_race = True if strava_activity.workout_type == "1" else False,
							distance = strava_activity.distance.num,
							total_elevation_gain = strava_activity.total_elevation_gain.num,
							elapsed_time =strava_activity.elapsed_time,
							moving_time = strava_activity.moving_time,
							average_speed = strava_activity.average_speed.num,
							average_cadence = (strava_activity.average_cadence * 2) if (strava_activity.type == "Run" and strava_activity.average_cadence is not None) else strava_activity.average_cadence,
							average_heartrate = strava_activity.average_heartrate,
							description = (strava_activity.description[:1000] if strava_activity.description else None)) #limit to first 1000 characters just in case

		db.session.add(activity)
		new_activity_count += 1

		if strava_activity.start_date.replace(tzinfo=None) > datetime.now() - timedelta(days=7):
			result = analysis.parse_streams(activity=activity)

	flash("Added {count} new activities from Strava!".format(count=new_activity_count))
	track_event(category="Strava", action="Completed import of Strava activity", userId = str(current_user.id))
	db.session.commit()

	# Evaluate any goals that the user has, including processing any additional data e.g. cadence
	current_day = CalendarDay.query.filter(CalendarDay.calendar_date==datetime.date(datetime.today())).first()
	current_week = current_day.calendar_week_start_date
	analysis.evaluate_running_goals(week=current_week, goal_metric="Runs Completed Over Distance")
	analysis.evaluate_running_goals(week=current_week, goal_metric="Weekly Distance")
	analysis.evaluate_running_goals(week=current_week, goal_metric="Weekly Moving Time")
	analysis.evaluate_running_goals(week=current_week, goal_metric="Weekly Elevation Gain")
	analysis.evaluate_running_goals(week=current_week, goal_metric="Time Spent Above Cadence", calculate_weekly_aggregations_function=analysis.calculate_weekly_cadence_aggregations)
	analysis.evaluate_running_goals(week=current_week, goal_metric="Distance Climbing Above Gradient", calculate_weekly_aggregations_function=analysis.calculate_weekly_gradient_aggregations)
	
	# If the user hasn't used categories yet then apply some defaults
	if len(current_user.exercise_categories.all()) == 0:
		run_category = ExerciseCategory(owner=current_user,
										category_key="cat_green",
										category_name="Run",
										fill_color="#588157",
										line_color="#588157")
		ride_category = ExerciseCategory(owner=current_user,
										 category_key="cat_blue",
										 category_name="Ride",
										 fill_color="#3f7eba",
										 line_color="#3f7eba")
		swim_category = ExerciseCategory(owner=current_user,
										 category_key="cat_red",
										 category_name="Swim",
										 fill_color="#ef6461",
										 line_color="#ef6461")
		db.session.add(run_category)
		db.session.add(ride_category)
		db.session.add(swim_category)
		db.session.commit()
		flash("Default categories have been added to colour-code your Strava activities. Configure them from the Manage Exercises section.")

	# Add a URL param that we can use to offer to redirect to Categories page	
	if (not current_user.is_training_goals_user) and new_activity_count > 1 and (current_user.id % 4) in [0, 1]: # Show to 50% of users
		show_post_import_modal = True
	else:
		show_post_import_modal = False

	# Redirect to the page the user came from if it was passed in as next parameter, otherwise the index
	next_page = request.args.get("next")
	if not next_page or url_parse(next_page).netloc != "": # netloc check prevents redirection to another website
		return redirect(url_for("index", show_post_import_modal=show_post_import_modal))
	return redirect("{next_page}?show_post_import_modal={show_post_import_modal}".format(next_page=next_page, show_post_import_modal=show_post_import_modal))


@app.route("/activity_analysis/<id>")
@login_required
def activity_analysis(id):
	track_event(category="Strava", action="Activity Analysis page loaded", userId = str(current_user.id))
	activity = Activity.query.get(int(id))

	if activity is None or activity.owner != current_user:
		flash("Invalid activity")
		return redirect(url_for("index"))

	if not activity.is_fully_parsed:
		track_event(category="Strava", action="Activity parsed from Strava", userId = str(current_user.id))

		# 1. Get the activity from Strava again and update what we have in DB
		strava_client = Client()

		if not session.get("strava_access_token"):
			return redirect(url_for("connect_strava", action="authorize"))

		access_token = session["strava_access_token"]
		strava_client.access_token = access_token

		try:
			strava_activity = strava_client.get_activity(activity_id=activity.external_id)
		except:
			return redirect(url_for("connect_strava", action="authorize"))

		activity.name = strava_activity.name
		activity.start_datetime = strava_activity.start_date
		activity.activity_type = strava_activity.type
		activity.is_race = True if strava_activity.workout_type == "1" else False
		activity.distance = strava_activity.distance.num
		activity.total_elevation_gain = strava_activity.total_elevation_gain.num
		activity.elapsed_time =strava_activity.elapsed_time
		activity.moving_time = strava_activity.moving_time
		activity.average_speed = strava_activity.average_speed.num
		activity.average_cadence = (strava_activity.average_cadence * 2) if (strava_activity.type == "Run" and strava_activity.average_cadence is not None) else strava_activity.average_cadence
		activity.average_heartrate = strava_activity.average_heartrate
		activity.description = (strava_activity.description[:1000] if strava_activity.description else None) #limit to first 1000 characters just in case

		db.session.commit()

		# 2. Run analysis.parse_streams(), which we want to...
		analysis.parse_streams(activity)

		# 3. Set the activity to is_fully_parsed and confirm user to be Strava user
		activity.is_fully_parsed = True

		if not current_user.is_strava_user:
			current_user.is_strava_user = True

		db.session.commit()

	# Find out colour-coding req's for the charts that follow
	run_category = ExerciseCategory.query.filter(ExerciseCategory.owner == current_user).filter(ExerciseCategory.category_name == "Run").first()
	if run_category is not None:
		fill_color = run_category.fill_color
		line_color = run_category.line_color
	else:
		fill_color = None
		line_color = None
	
	# Cadence charts
	if activity.median_cadence:
		# Keep the graph tidy if there's any bit of walking or other outliers by excluding them
		max_dimension_range = (int(activity.median_cadence-30), int(activity.median_cadence+30))

		at_cadence_plot = generate_bar(dataset=activity.activity_cadence_aggregates, plot_height=300,
			dimension_name="cadence", measure_name="total_seconds_at_cadence", measure_label_name="total_seconds_at_cadence_formatted", max_dimension_range=max_dimension_range,
			fill_color=fill_color, line_color=line_color)
		at_cadence_plot_script, at_cadence_plot_div = components(at_cadence_plot)

		above_cadence_plot = generate_bar(dataset=activity.activity_cadence_aggregates, plot_height=300,
			dimension_name="cadence", measure_name="total_seconds_above_cadence", measure_label_name="total_seconds_above_cadence_formatted", max_dimension_range=max_dimension_range,
			fill_color=fill_color, line_color=line_color)
		above_cadence_plot_script, above_cadence_plot_div = components(above_cadence_plot)
	else:
		at_cadence_plot_script, at_cadence_plot_div = ("", "")
		above_cadence_plot_script, above_cadence_plot_div = ("", "")
	
	# Pace charts
	if activity.activity_pace_aggregates.first():
		# Keep the graph tidy if there's any bit of walking or other outliers by excluding them
		max_dimension_range = (utils.seconds_to_datetime(0), utils.seconds_to_datetime(utils.convert_mps_to_km_pace(activity.average_speed).total_seconds() + 60))

		at_pace_plot = generate_bar(dataset=activity.activity_pace_aggregates.order_by(ActivityPaceAggregate.pace_seconds.desc()), plot_height=300,
			dimension_type="timedelta", dimension_name="pace_seconds", measure_name="total_seconds_at_pace", dimension_interval=5000, measure_label_name="total_seconds_at_pace_formatted", max_dimension_range=max_dimension_range,
			fill_color=fill_color, line_color=line_color)
		at_pace_plot_script, at_pace_plot_div = components(at_pace_plot)
		at_pace_plot_container = PlotComponentContainer(name="Time Spent at Pace (secs/km)", plot_div=at_pace_plot_div, plot_script=at_pace_plot_script)

		above_pace_plot = generate_bar(dataset=activity.activity_pace_aggregates.order_by(ActivityPaceAggregate.pace_seconds.desc()), plot_height=300,
			dimension_type="timedelta", dimension_name="pace_seconds", measure_name="total_seconds_above_pace", dimension_interval=5000, measure_label_name="total_seconds_above_pace_formatted", max_dimension_range=max_dimension_range,
			fill_color=fill_color, line_color=line_color)
		above_pace_plot_script, above_pace_plot_div = components(above_pace_plot)
		above_pace_plot_container = PlotComponentContainer(name="Time Spent faster than Pace (secs/km)", plot_div=above_pace_plot_div, plot_script=above_pace_plot_script)
	else:
		at_pace_plot_container = None
		above_pace_plot_container = None

	# Gradient charts
	if activity.activity_gradient_aggregates.first():
		at_gradient_plot = generate_bar(dataset=activity.activity_gradient_aggregates, plot_height=300,
			dimension_name="gradient", measure_name="total_metres_at_gradient", dimension_interval=1, measure_label_name="total_metres_at_gradient_formatted",
			fill_color=fill_color, line_color=line_color)
		at_gradient_plot_script, at_gradient_plot_div = components(at_gradient_plot)
		at_gradient_plot_container = PlotComponentContainer(name="Distance Climbing at Gradient %", plot_div=at_gradient_plot_div, plot_script=at_gradient_plot_script)

		above_gradient_plot = generate_bar(dataset=activity.activity_gradient_aggregates, plot_height=300,
			dimension_name="gradient", measure_name="total_metres_above_gradient", dimension_interval=1, measure_label_name="total_metres_above_gradient_formatted",
			fill_color=fill_color, line_color=line_color)
		above_gradient_plot_script, above_gradient_plot_div = components(above_gradient_plot)
		above_gradient_plot_container = PlotComponentContainer(name="Distance Climbing above Gradient %", plot_div=above_gradient_plot_div, plot_script=above_gradient_plot_script)
	else:
		at_gradient_plot_container = None
		above_gradient_plot_container = None


	return render_template("activity_analysis.html", title="Activity Analysis: {name}".format(name=activity.name), activity=activity,
		at_cadence_plot_script=at_cadence_plot_script, at_cadence_plot_div=at_cadence_plot_div,
		above_cadence_plot_script=above_cadence_plot_script, above_cadence_plot_div=above_cadence_plot_div,
		at_pace_plot_container=at_pace_plot_container, above_pace_plot_container=above_pace_plot_container,
		at_gradient_plot_container=at_gradient_plot_container, above_gradient_plot_container=above_gradient_plot_container)


@app.route("/connect_strava/<action>")
@login_required
def connect_strava(action="prompt"):
	code = request.args.get("code")
	error = request.args.get("error")
	next_page = request.args.get("next")

	if next_page is None:
		next_page = "/hub"

	if error:
		track_event(category="Strava", action="Error during Strava authorization", userId = str(current_user.id))
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


@app.route("/backfill_stream_data")
@login_required
def backfill_stream_data():
	track_event(category="Strava", action="Streams backfill triggered", userId = str(current_user.id))
	activities = current_user.activities.filter(Activity.is_fully_parsed == False).order_by(Activity.start_datetime.desc()).all()
	flash("Getting detailed run data for {count} activities".format(count=len(activities)))

	for activity in activities:
		result = analysis.parse_streams(activity)
		if result == "Not authorized":
			return redirect(url_for("connect_strava", action="authorize"))

	track_event(category="Strava", action="Streams backfill completed", userId = str(current_user.id))
	return redirect(url_for("weekly_activity", year="current"))

@app.route("/flag_bad_elevation_data/<activity_id>")
@login_required
def flag_bad_elevation_data(activity_id):
	track_event(category="Analysis", action="Elevation data flagged as bad", userId = str(current_user.id))

	activity = Activity.query.get(int(activity_id))
	activity.is_bad_elevation_data = True
	activity.total_elevation_gain = None

	for gradient_aggregate in activity.activity_gradient_aggregates:
		db.session.delete(gradient_aggregate)

	db.session.commit()
	flash("Elevation and gradient for {activity_name} flagged as bad and will be ignored from now on.".format(activity_name=activity.name))

	return redirect(url_for('activity_analysis', id=activity.id))

@app.route("/privacy")
def privacy_policy():
	return render_template("privacy.html", title="Privacy Policy")

@app.route("/test")
def test():
	return render_template("_hub.html")