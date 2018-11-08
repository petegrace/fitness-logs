from flask import flash, redirect, url_for, request, session
from flask_login import current_user
from app import app, db, utils
from app.models import TrainingGoal, ActivityCadenceAggregate
from app.app_classes import TempCadenceAggregate
from sqlalchemy import or_
from stravalib.client import Client
import pandas as pd
from datetime import datetime, timedelta

def evaluate_cadence_goals(week):
	# 1. Get the in-progress goals, or goals for the current week that have already been hit but might have got better
	current_goals = current_user.training_goals.filter(or_(TrainingGoal.goal_start_date == week, TrainingGoal.goal_status == "In Progress")).filter_by(goal_metric="Time Spent Above Cadence").all()

	weeks_to_evaluate = []
	[weeks_to_evaluate.append(goal.goal_start_date) for goal in current_goals if goal.goal_start_date not in weeks_to_evaluate]
	
	for week in weeks_to_evaluate:
		run_activities = current_user.activities_filtered(activity_type="Run", week=week).all()

		# 2. Ensure that all Run activities for the week have cadence calculated, bearing in mind that if user hasn't sync'ed for a few weeks we might need to look back at a historic week
		for run in run_activities:
			if run.median_cadence is None:
				result = parse_cadence_stream(activity=run)
				if result == "Not authorized":
					redirect(url_for("connect_strava", action="authorize"))

		# 3. Get weekly cadence stats as for the graph
		weekly_cadence_aggregations = calculate_weekly_cadence_aggregations(week)
		weekly_cadence_goals = current_user.training_goals.filter_by(goal_start_date=week).filter_by(goal_metric="Time Spent Above Cadence").all()
	
		for goal in weekly_cadence_goals:
			goal_cadence = int(goal.goal_dimension_value)
			# 4. Compare the current stats vs. goal where they're for the same cadence
			for cadence_aggregate in weekly_cadence_aggregations["summary"]:
				if cadence_aggregate.cadence == goal_cadence:
					goal.current_metric_value = cadence_aggregate.total_seconds_above_cadence
					# 5. Set to success if the target has been hit and flash a congrats message
					if goal.current_metric_value >= goal.goal_target:
						goal.goal_status = "Successful"
			# 6. Set to missed if if the time period has expired
			if goal.goal_start_date + timedelta(days=7) < datetime.date(datetime.utcnow()) and goal.current_metric_value < goal.goal_target:
				goal.goal_status = "Missed"

	db.session.commit()


def parse_cadence_stream(activity):
	strava_client = Client()

	if not session.get("strava_access_token"):
		return "Not authorized"

	access_token = session["strava_access_token"]
	strava_client.access_token = access_token

	stream_types = ["time", "cadence"]

	try:
		activity_streams = strava_client.get_activity_streams(activity.external_id, types=stream_types)
	except:
		return "Not authorized"

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
		flash("Processed cadence data for {activity}".format(activity=activity.name))
		db.session.commit()
		return "Success"
	else:
		return "No cadence data available"


def calculate_weekly_cadence_aggregations(week):
	weekly_cadence_stats = current_user.weekly_cadence_stats(week=week).all()
	min_significant_cadence = 30
	max_significant_cadence = 300
	weekly_running_total = 0

	weekly_cadence_summary = []

	# For the lower range in graph look for aything more than 5 minutes
	for cadence_aggregate in weekly_cadence_stats:
		weekly_running_total += cadence_aggregate.total_seconds_at_cadence
		if cadence_aggregate.total_seconds_at_cadence >= 60 and max_significant_cadence==300: # only overwrite the max once (we're iterating in descing order)
			max_significant_cadence = cadence_aggregate.cadence 
		if cadence_aggregate.total_seconds_at_cadence >= 300: # keep overwriting until we get to the end and have the min
			min_significant_cadence = cadence_aggregate.cadence
		weekly_cadence_summary.append(TempCadenceAggregate(cadence=cadence_aggregate.cadence,
														   total_seconds_above_cadence=weekly_running_total))

	weekly_cadence_aggregations = dict(summary = weekly_cadence_summary,
									   min_significant_cadence = min_significant_cadence,
									   max_significant_cadence = max_significant_cadence)
	return weekly_cadence_aggregations

