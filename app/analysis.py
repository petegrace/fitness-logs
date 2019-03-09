from flask import flash, redirect, url_for, request, session
from flask_login import current_user
from bokeh.embed import components
from app import app, db, utils
from app.models import TrainingGoal, ActivityCadenceAggregate, ActivityPaceAggregate, ActivityGradientAggregate, CalendarDay, Activity, Exercise, ExerciseType, ExerciseCategory
from app.app_classes import TempCadenceAggregate, TempGradientAggregate, PlotComponentContainer
from app.dataviz import generate_line_chart
from sqlalchemy import func, or_
from stravalib.client import Client
import pandas as pd
import math
from datetime import datetime, timedelta

def evaluate_running_goals(week, goal_metric, calculate_weekly_aggregations_function=None):
	# 1. Get the in-progress goals, or goals for the current week that have already been hit but might have got better
	current_goals = current_user.training_goals.filter(or_(TrainingGoal.goal_start_date == week, TrainingGoal.goal_status == "In Progress")).filter_by(goal_metric=goal_metric).all()

	weeks_to_evaluate = []
	[weeks_to_evaluate.append(goal.goal_start_date) for goal in current_goals if goal.goal_start_date not in weeks_to_evaluate]

	for week in weeks_to_evaluate:
		run_activities = current_user.activities_filtered(activity_type="Run", week=week).all()
		weekly_goals = current_user.training_goals.filter_by(goal_start_date=week).filter_by(goal_metric=goal_metric).all()

		# 2. Ensure that all Run activities for the week have cadence calculated, bearing in mind that if user hasn't sync'ed for a few weeks we might need to look back at a historic week
		for run in run_activities:
			if not run.is_fully_parsed:
				result = parse_streams(activity=run)
				if result == "Not authorized":
					flash("Some activities relevant to your goal may not be fully parsed.  Please Connect with Strava when you get chance.")
					break

		if goal_metric == "Runs Completed Over Distance":
			for goal in weekly_goals:
				# 3. Get the stats we need
				activities_over_distance = [activity for activity in run_activities if activity.distance >= int(goal.goal_dimension_value)*1000]
				# 4. Compare the current stats vs. goal where they're for the same cadence
				goal.current_metric_value = len(activities_over_distance)
				# 5. Set to success if the target has been hit and flash a congrats message
				if goal.current_metric_value >= goal.goal_target:
					goal.goal_status = "Successful"
				# 6. Set to missed if if the time period has expired
				if goal.goal_start_date + timedelta(days=7) < datetime.date(datetime.utcnow()) and goal.current_metric_value < goal.goal_target:
					goal.goal_status = "Missed"

		if goal_metric in (["Weekly Distance", "Weekly Moving Time", "Weekly Elevation Gain"]):
			for goal in weekly_goals:
				# 3. Get the stats we need
				weekly_summary_stats = current_user.weekly_activity_type_stats(week=week).filter(Activity.activity_type=="Run").all()
				# 4. Compare the current stats vs. goal where they're for the same cadence
				for row in weekly_summary_stats: # Use a for loop to deal with it potentially being zero rows
					if goal_metric == "Weekly Distance":
						goal.current_metric_value = row.total_distance
					elif goal_metric == "Weekly Moving Time":
						goal.current_metric_value = row.total_moving_time.seconds
					elif goal_metric == "Weekly Elevation Gain":
						goal.current_metric_value = row.total_elevation_gain
				# 5. Set to success if the target has been hit and flash a congrats message
				if goal.current_metric_value >= goal.goal_target:
					goal.goal_status = "Successful"
				# 6. Set to missed if if the time period has expired
				if goal.goal_start_date + timedelta(days=7) < datetime.date(datetime.utcnow()) and goal.current_metric_value < goal.goal_target:
					goal.goal_status = "Missed"

		elif goal_metric in (["Time Spent Above Cadence", "Distance Climbing Above Gradient"]):
			# 3. Get weekly stats as for the graph
			weekly_aggregations = calculate_weekly_aggregations_function(week)
			
			for goal in weekly_goals:
				goal_dimension_value = int(goal.goal_dimension_value)
				# 4. Compare the current stats vs. goal where they're for the same cadence
				for aggregate in weekly_aggregations["summary"]:
					if aggregate.get_dimension_value() == goal_dimension_value:
						goal.current_metric_value = aggregate.get_metric_value()
						# 5. Set to success if the target has been hit and flash a congrats message
						if goal.current_metric_value >= goal.goal_target:
							goal.goal_status = "Successful"
				# 6. Set to missed if if the time period has expired
				if goal.goal_start_date + timedelta(days=7) < datetime.date(datetime.utcnow()) and goal.current_metric_value < goal.goal_target:
					goal.goal_status = "Missed"

	db.session.commit()


def aggregate_stream_data(data_points_df, groupby_field, sort_order="DESC"):
	duration_aggregation = data_points_df.groupby([groupby_field])["duration"].sum()
	distance_aggregation = data_points_df.groupby([groupby_field])["distance_travelled"].sum().round(decimals=1)
	grouped_data = list(zip(duration_aggregation.index, duration_aggregation, distance_aggregation))

	if sort_order == "DESC":
		grouped_data.reverse()
	
	return grouped_data


def parse_streams(activity):
	if activity.activity_type != "Run":
		return "Invalid activity type"

	strava_client = Client()

	if not session.get("strava_access_token"):
		return "Not authorized"

	access_token = session["strava_access_token"]
	strava_client.access_token = access_token

	stream_types = ["time", "cadence", "velocity_smooth", "distance", "altitude", "grade_smooth"]

	try:
		activity_streams = strava_client.get_activity_streams(activity.external_id, types=stream_types)
	except:
		return "Not authorized"

	if activity_streams is not None:
		#cadence_records = []
		data_points_df = pd.DataFrame(columns=["start_time", "duration", "distance_travelled", "elevation_gained", "pace_seconds", "cadence", "gradient"])
		dp_ind = 0
		df_ind = 0

		# construct a data frame.  We can probably do this more efficiently by constructing a list first then only putting into the data frame once
		for time_data_point in activity_streams["time"].data:
			if dp_ind > 1:
				duration = (time_data_point - activity_streams["time"].data[dp_ind-1])
				distance_travelled = (activity_streams["distance"].data[dp_ind] - activity_streams["distance"].data[dp_ind-1])
				elevation_gained = (activity_streams["altitude"].data[dp_ind] - activity_streams["altitude"].data[dp_ind-1]) if "altitude" in activity_streams else None
				pace_seconds = math.ceil(utils.convert_mps_to_km_pace(activity_streams["velocity_smooth"].data[dp_ind]).total_seconds() / 5) * 5 if "velocity_smooth" in activity_streams and activity_streams["velocity_smooth"].data[dp_ind] > 0 else None
				gradient = math.floor(activity_streams["grade_smooth"].data[dp_ind]) if "grade_smooth" in activity_streams else None

				# Extra cleansing of gradient to deal with dodgy value during barometer calibration
				gradient = None if time_data_point < 60 and gradient > 10 else gradient
				elevation_gained = None if elevation_gained and ((time_data_point < 60 and elevation_gained > 1) or elevation_gained < 0) else elevation_gained

				if duration <= 10: # Discard anything more than 10 seconds that probably relates to stopping
					data_points_df.loc[df_ind] = [activity_streams["time"].data[dp_ind-1],
												  duration,
												  distance_travelled,
												  elevation_gained,
												  pace_seconds,
												  activity_streams["cadence"].data[dp_ind] if "cadence" in activity_streams else None,
												  gradient]
					df_ind += 1
			dp_ind += 1

		# Test if we corrected for calibration such that it's worth overwriting the Strava elevation gain. Note that
		# Strava tends to come up with a lower number normally (probably due to smoothing) so we only use this if it's a lower number
		total_elevation_gain = data_points_df["elevation_gained"].sum()
		if total_elevation_gain < activity.total_elevation_gain:
			activity.total_elevation_gain = total_elevation_gain
			activity.is_overwritten_elevation_gain = True
			flash("Bad elevation gain detected on activity. Overwritten in Training Ticks based on calibration errors detected.")

		# Perform aggregations for cadence if needed
		if not activity.activity_cadence_aggregates.first() and "cadence" in activity_streams:
			cadence_data = aggregate_stream_data(data_points_df, groupby_field="cadence")

			running_total = 0
			this_aggregate_total = 0

			for cadence_group in cadence_data:
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

			activity.median_cadence = data_points_df["cadence"].median()*2

		# Perform aggregations for pace if needed
		if not activity.activity_pace_aggregates.first() and "velocity_smooth" in activity_streams:
			pace_data = aggregate_stream_data(data_points_df, groupby_field="pace_seconds", sort_order="ASC")
			
			running_total = 0
			this_aggregate_total = 0

			for pace_group in pace_data:
				running_total += pace_group[1]
				this_aggregate_total += pace_group[1]
				
				# Group up any outliers with seconds < 10 seconds into the next aggregate
				if this_aggregate_total > 10:
					activity_pace_aggregate = ActivityPaceAggregate(activity=activity,
																	pace_seconds=pace_group[0],
																	total_seconds_at_pace=this_aggregate_total,
																	total_seconds_above_pace=running_total)
					db.session.add(activity_pace_aggregate)
					this_aggregate_total = 0

		# Perform aggregations for gradient if needed
		if not activity.activity_gradient_aggregates.first() and "grade_smooth" in activity_streams:
			gradient_data = aggregate_stream_data(data_points_df, groupby_field="gradient")

			running_total_duration = 0
			running_total_distance = 0
			this_aggregate_total_duration = 0
			this_aggregate_total_distance = 0

			for gradient_group in gradient_data:
				running_total_duration += gradient_group[1]
				running_total_distance += gradient_group[2]
				this_aggregate_total_duration += gradient_group[1]
				this_aggregate_total_distance += gradient_group[2]
				
				# We don't care about anything < 2% as it's not going to be significant enough
				if gradient_group[0] < 2:
					break

				# Group up any outliers with seconds < 5 seconds into the next aggregate
				if this_aggregate_total_duration > 5:
					activity_gradient_aggregate = ActivityGradientAggregate(activity=activity,
																			gradient=gradient_group[0],
																			total_seconds_at_gradient=this_aggregate_total_duration,
																			total_seconds_above_gradient=running_total_duration,
																			total_metres_at_gradient=this_aggregate_total_distance,
																			total_metres_above_gradient=running_total_distance)
					db.session.add(activity_gradient_aggregate)
					this_aggregate_total_duration = 0
					this_aggregate_total_distance = 0

		
		flash("Processed detailed activity data for {activity}".format(activity=activity.name))

		activity.is_fully_parsed = True
		db.session.commit()
		return "Success"
	else:
		return "No activity streams available"


def calculate_weekly_cadence_aggregations(week):
	weekly_cadence_stats = current_user.weekly_cadence_stats(week=week).all()
	min_significant_cadence = 30
	max_significant_cadence = 300
	previous_cadence = 0
	weekly_running_total = 0

	weekly_cadence_summary = []

	# For the lower range in graph look for aything more than 5 minutes
	for cadence_aggregate in weekly_cadence_stats:
		# Fill in any gaps
		if cadence_aggregate.cadence < previous_cadence - 2:
			gap_cadence = previous_cadence - 2
			while gap_cadence > cadence_aggregate.cadence:
				weekly_cadence_summary.append(TempCadenceAggregate(cadence=gap_cadence,
														   		   total_seconds_above_cadence=weekly_running_total))
				gap_cadence -= 2

		# Now get on with adding the current cadence
		weekly_running_total += cadence_aggregate.total_seconds_at_cadence
		if cadence_aggregate.total_seconds_at_cadence >= 60 and max_significant_cadence==300: # only overwrite the max once (we're iterating in descing order)
			max_significant_cadence = cadence_aggregate.cadence 
		if cadence_aggregate.total_seconds_at_cadence >= 300: # keep overwriting until we get to the end and have the min
			min_significant_cadence = cadence_aggregate.cadence
		weekly_cadence_summary.append(TempCadenceAggregate(cadence=cadence_aggregate.cadence,
														   total_seconds_above_cadence=weekly_running_total))
		# Set the previous_cadence so we can detect gaps
		previous_cadence = cadence_aggregate.cadence

	weekly_cadence_aggregations = dict(summary = weekly_cadence_summary,
									   min_significant_cadence = min_significant_cadence,
									   max_significant_cadence = max_significant_cadence)
	return weekly_cadence_aggregations


def calculate_weekly_gradient_aggregations(week):
	weekly_gradient_stats = current_user.weekly_gradient_stats(week=week).all()
	min_significant_gradient = 1
	max_significant_gradient = 100
	previous_gradient = 0
	weekly_running_total = 0

	weekly_gradient_summary = []

	# For the lower range in graph look for aything more than 5 minutes
	for gradient_aggregate in weekly_gradient_stats:
		# Fill in any gaps
		if gradient_aggregate.gradient < previous_gradient - 1:
			gap_gradient = previous_gradient - 1
			while gap_gradient > gradient_aggregate.gradient:
				weekly_gradient_summary.append(TempGradientAggregate(gradient=gap_gradient,
														   		     total_metres_above_gradient=weekly_running_total))
				gap_gradient -= 1

		# Now get on with adding the current gradient
		weekly_running_total += gradient_aggregate.total_metres_at_gradient
		if gradient_aggregate.total_metres_at_gradient >= 100 and max_significant_gradient==100: # only overwrite the max once (we're iterating in descing order)
			max_significant_gradient = gradient_aggregate.gradient 
		if gradient_aggregate.total_metres_at_gradient >= 100: # keep overwriting until we get to the end and have the min
			min_significant_gradient = gradient_aggregate.gradient
		weekly_gradient_summary.append(TempGradientAggregate(gradient=gradient_aggregate.gradient,
														   	 total_metres_above_gradient=weekly_running_total))
		# Set the previous_gradient so we can detect gaps
		previous_gradient = gradient_aggregate.gradient

	weekly_gradient_aggregations = dict(summary = weekly_gradient_summary,
									    min_significant_gradient = min_significant_gradient,
									    max_significant_gradient = max_significant_gradient)
	return weekly_gradient_aggregations


def get_cadence_goal_history_charts(week):
	weekly_cadence_goals = current_user.training_goals.filter_by(goal_start_date=week).filter_by(goal_metric="Time Spent Above Cadence").all()

	cadence_goal_plot_containers = []

	run_category = current_user.exercise_categories.filter_by(category_name="Run").first()
	if run_category is not None:
		line_color = run_category.line_color
	else:
		line_color = None

	for goal in weekly_cadence_goals:
		goal_history = db.session.query(
				CalendarDay.calendar_week_start_date,
				func.sum(ActivityCadenceAggregate.total_seconds_at_cadence).label("total_seconds_above_cadence")
			).join(ActivityCadenceAggregate.activity
			).join(CalendarDay, func.date(Activity.start_datetime)==CalendarDay.calendar_date
			).filter(Activity.owner == current_user
			).filter(ActivityCadenceAggregate.cadence >= int(goal.goal_dimension_value)
			).filter(Activity.start_datetime >= (week - timedelta(days=365))
			).filter(Activity.start_datetime < (week + timedelta(days=7))
			).group_by(CalendarDay.calendar_week_start_date
			).order_by(CalendarDay.calendar_week_start_date).all()

		plot_name = "Historic {metric} of {dimension_value}".format(metric=goal.goal_metric , dimension_value=goal.goal_dimension_value)
		cadence_goal_history_plot = generate_line_chart(dataset=goal_history, plot_height=100, dimension_name="calendar_week_start_date", measure_name="total_seconds_above_cadence", line_color=line_color,
											y_tick_function_code="return parseInt(tick / 60);")
		cadence_goal_history_plot_script, cadence_goal_history_plot_div = components(cadence_goal_history_plot)
		cadence_goal_plot_container = PlotComponentContainer(name=plot_name, plot_div=cadence_goal_history_plot_div, plot_script=cadence_goal_history_plot_script)
		cadence_goal_plot_containers.append(cadence_goal_plot_container)

	return cadence_goal_plot_containers


def evaluate_exercise_set_goals(week):
	# 1. Get the in-progress goals, or goals for the current week that have already been hit but might have got better
	current_goals = current_user.training_goals.filter(or_(TrainingGoal.goal_start_date == week, TrainingGoal.goal_status == "In Progress")).filter_by(goal_metric="Exercise Sets Completed").all()
	for goal in current_goals:
		if goal.goal_dimension_value == "None":
			exercise_sets = current_user.exercises_filtered(week=goal.goal_start_date).all()
		else:
			exercise_sets = current_user.exercises_filtered(exercise_category_id=int(goal.goal_dimension_value), week=goal.goal_start_date).all()
		# 4. Compare the current stats vs. goal where they're for the same cadence
		goal.current_metric_value = len(exercise_sets)
		# 5. Set to success if the target has been hit and flash a congrats message
		if goal.current_metric_value >= goal.goal_target:
			goal.goal_status = "Successful"
		# 6. Set to missed if if the time period has expired
		if goal.goal_start_date + timedelta(days=7) < datetime.date(datetime.utcnow()) and goal.current_metric_value < goal.goal_target:
			goal.goal_status = "Missed"

	db.session.commit()


def get_goal_history_charts(week, goal_metric):
	weekly_goals = current_user.training_goals.filter_by(goal_start_date=week).filter_by(goal_metric=goal_metric).all()

	goal_plot_containers = []

	# Set line colors for runs, which we'll override for Exercise Sets goals
	run_category = current_user.exercise_categories.filter_by(category_name="Run").first()
	if run_category is not None:
		line_color = run_category.line_color
	else:
		line_color = None

	for goal in weekly_goals:
		if goal_metric == "Time Spent Above Cadence":
			goal_history = db.session.query(
					CalendarDay.calendar_week_start_date,
					func.sum(ActivityCadenceAggregate.total_seconds_at_cadence).label("total_seconds_above_cadence")
				).join(ActivityCadenceAggregate.activity
				).join(CalendarDay, func.date(Activity.start_datetime)==CalendarDay.calendar_date
				).filter(Activity.owner == current_user
				).filter(ActivityCadenceAggregate.cadence >= int(goal.goal_dimension_value)
				).filter(Activity.start_datetime >= (week - timedelta(days=365))
				).filter(Activity.start_datetime < (week + timedelta(days=7))
				).group_by(CalendarDay.calendar_week_start_date
				).order_by(CalendarDay.calendar_week_start_date).all()

			plot_name = "Historic {metric} of {dimension_value}".format(metric=goal.goal_metric , dimension_value=goal.goal_dimension_value)
			goal_history_plot = generate_line_chart(dataset=goal_history, plot_height=100, dimension_name="calendar_week_start_date", measure_name="total_seconds_above_cadence", line_color=line_color,
											y_tick_function_code="return parseInt(tick / 60);")

		elif goal_metric == "Distance Climbing Above Gradient":
			goal_history = db.session.query(
					CalendarDay.calendar_week_start_date,
					func.sum(ActivityGradientAggregate.total_metres_at_gradient).label("total_metres_above_gradient")
				).join(ActivityGradientAggregate.activity
				).join(CalendarDay, func.date(Activity.start_datetime)==CalendarDay.calendar_date
				).filter(Activity.owner == current_user
				).filter(ActivityGradientAggregate.gradient >= int(goal.goal_dimension_value)
				).filter(Activity.start_datetime >= (week - timedelta(days=365))
				).filter(Activity.start_datetime < (week + timedelta(days=7))
				).group_by(CalendarDay.calendar_week_start_date
				).order_by(CalendarDay.calendar_week_start_date).all()

			plot_name = "Historic {metric} of {dimension_value}%".format(metric=goal.goal_metric , dimension_value=goal.goal_dimension_value)
			goal_history_plot = generate_line_chart(dataset=goal_history, plot_height=100, dimension_name="calendar_week_start_date", measure_name="total_metres_above_gradient", line_color=line_color,
											y_tick_function_code="return parseInt(tick / 1000);")

		elif goal_metric == "Exercise Sets Completed":
			if goal.goal_dimension_value == "None":
				line_color = "#292b2c"
				goal_category_name = "Uncategorised"
			else:
				goal_category = ExerciseCategory.query.get(int(goal.goal_dimension_value))
				line_color = goal_category.line_color
				goal_category_name = goal_category.category_name

			goal_history = db.session.query(
					CalendarDay.calendar_week_start_date,
					func.count(Exercise.id).label("exercise_sets_completed")
				).join(Exercise.type
				).join(CalendarDay, func.date(Exercise.exercise_datetime)==CalendarDay.calendar_date
				).filter(ExerciseType.owner == current_user
				).filter(or_(ExerciseType.exercise_category_id == int(goal.goal_dimension_value), goal.goal_dimension_value == "None")
				).filter(Exercise.exercise_datetime >= (week - timedelta(days=365))
				).filter(Exercise.exercise_datetime < (week + timedelta(days=7))
				).group_by(CalendarDay.calendar_week_start_date
				).order_by(CalendarDay.calendar_week_start_date).all()
		
			measure_name = "exercise_sets_completed"
			plot_name = "Historic {metric} of {dimension_value}".format(metric=goal.goal_metric , dimension_value=goal_category_name)
			goal_history_plot = generate_line_chart(dataset=goal_history, plot_height=100, dimension_name="calendar_week_start_date", measure_name=measure_name, line_color=line_color)
		
		goal_history_plot_script, goal_history_plot_div = components(goal_history_plot)
		goal_plot_container = PlotComponentContainer(name=plot_name, plot_div=goal_history_plot_div, plot_script=goal_history_plot_script)
		goal_plot_containers.append(goal_plot_container)

	return goal_plot_containers