from datetime import datetime, timedelta

def convert_m_to_km(m):
	km = round((m / 1000), 2)
	return km

def convert_mps_to_km_pace(mps):
	# Prevent divide by zero error
	if mps == 0:
		return None

	km_per_sec = mps / 1000
	secs_per_km = int(1 / km_per_sec)
	pace_timedelta = timedelta(seconds=secs_per_km)
	return pace_timedelta

def format_distance(m):
	if m >= 1000:
		distance_formatted = "{value} km".format(value=convert_m_to_km(m))
	else:
		distance_formatted = "{value} m".format(value=m)
	return distance_formatted

def format_timedelta_minutes(timedelta):
	minutes_split = convert_seconds_to_minutes_split(timedelta.seconds)
	timedelta_formatted = "%d:%02d" % (minutes_split["minutes"], minutes_split["seconds"])
	return timedelta_formatted

def convert_seconds_to_minutes_split(seconds):
	minutes, seconds = divmod(seconds, 60)
	minutes_split = { "minutes": minutes, "seconds": seconds }
	return minutes_split

def convert_timedelta_to_minutes_split(timedelta):
	return convert_seconds_to_minutes_split(timedelta.seconds)

def convert_seconds_to_minutes_formatted(seconds):
	minutes_split = convert_seconds_to_minutes_split(seconds)
	timedelta_formatted = "%d:%02d" % (minutes_split["minutes"], minutes_split["seconds"])
	return timedelta_formatted

def format_percentage(percent):
	return "{percent}%".format(percent=round(percent, 1))

def format_percentage_labels(percent):
	if percent >= 80 and percent <= 120:
		label = "" # Blank label so that it doesn't overlap on the chart
	else:
		label = format_percentage(percent)
	return label

# Wrapping the Python len function so its in utils that we pass into Jinja templates, otherwise we get undefined error
def length_of_list(list):
	return len(list)

def format_goal_units(goal_metric, value):
	if goal_metric == "Exercise Sets Completed":
		return "{sets} sets".format(sets=value)
	elif goal_metric == "Runs Completed Over Distance":
		return "{runs} run(s)".format(runs=value)
	elif goal_metric == "Weekly Distance":
		return format_distance(value)
	elif goal_metric == "Weekly Moving Time":
		return convert_seconds_to_minutes_formatted(value)
	elif goal_metric == "Weekly Elevation Gain":
		return "{metres} m".format(metres=value)
	elif goal_metric == "Time Spent Above Cadence":
		return convert_seconds_to_minutes_formatted(value)
	elif goal_metric == "Distance Climbing Above Gradient":
		return format_distance(value)

def current_year():
	return datetime.today().year

def seconds_to_datetime(seconds):
	base_datetime = datetime(2000, 1, 1, 0, 0)
	return base_datetime + timedelta(seconds=seconds)