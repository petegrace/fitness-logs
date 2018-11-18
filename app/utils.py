import datetime

def convert_m_to_km(m):
	km = round((m / 1000), 2)
	return km

def convert_mps_to_km_pace(mps):
	# Prevent divide by zero error
	if mps == 0:
		return None

	km_per_sec = mps / 1000
	secs_per_km = int(1 / km_per_sec)
	pace_timedelta = datetime.timedelta(seconds=secs_per_km)
	return pace_timedelta

def format_timedelta_minutes(timedelta):
	minutes, seconds = divmod(timedelta.seconds, 60)
	timedelta_formatted = "%d:%02d" % (minutes, seconds)
	return timedelta_formatted

def convert_seconds_to_minutes_formatted(seconds):
	minutes, seconds = divmod(seconds, 60)
	timedelta_formatted = "%d:%02d" % (minutes, seconds)
	return timedelta_formatted

def format_percentage(percent):
	return "{percent}%".format(percent=round(percent, 1))

# Wrapping the Python len function so its in utils that we pass into Jinja templates, otherwise we get undefined error
def length_of_list(list):
	return len(list)

def format_goal_units(goal_metric, value):
	if goal_metric == "Exercise Sets Completed":
		return "{sets} sets".format(sets=value)
	elif goal_metric == "Time Spent Above Cadence":
		return convert_seconds_to_minutes_formatted(value)