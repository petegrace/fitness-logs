from datetime import datetime, timedelta

def format_distance_for_uom_preference(m, user, decimal_places=2, show_uom_suffix=True):
	if user.distance_uom_preference == "miles":
		uom_suffix = " miles" if show_uom_suffix else ""
		distance_formatted = "{value}{uom_suffix}".format(value=convert_m_to_miles(m, decimal_places), uom_suffix=uom_suffix)
	else:
		uom_suffix = " km" if show_uom_suffix else ""
		distance_formatted = "{value}{uom_suffix}".format(value=convert_m_to_km(m, decimal_places), uom_suffix=uom_suffix)
	return distance_formatted

def convert_distance_to_m_for_uom_preference(user_distance, user):
	if user.distance_uom_preference == "miles":
		distance_m = user_distance * 1609.344
	else:
		distance_m = user_distance * 1000
	print(distance_m)
	return distance_m

def convert_m_to_km(m, decimal_places=2):
	km = round((m / 1000), decimal_places)
	if decimal_places == 0:
		km = int(km)
	return km

def convert_m_to_miles(m, decimal_places=2):
	miles = round((float(m) * 0.000621371), decimal_places)
	if decimal_places == 0:
		miles = int(miles)
	return miles

def format_pace_for_uom_preference(mps, user, show_uom_suffix=True):
	if user.distance_uom_preference == "miles":
		uom_suffix = " /mile" if show_uom_suffix else ""
	else:
		uom_suffix = " /km" if show_uom_suffix else ""
	pace_formatted = "{value}{uom_suffix}".format(value=format_timedelta_minutes(convert_mps_for_pace_uom_preference(mps, user)), uom_suffix=uom_suffix)
	return pace_formatted

def convert_mps_for_pace_uom_preference(mps, user):
	if user.distance_uom_preference == "miles":
		pace_timedelta = convert_mps_to_mile_pace(mps)
	else:
		pace_timedelta = convert_mps_to_km_pace(mps)
	return pace_timedelta

def convert_mps_to_km_pace(mps):
	# Prevent divide by zero error
	if mps == 0:
		return None

	km_per_sec = mps / 1000
	secs_per_km = int(1 / km_per_sec)
	pace_timedelta = timedelta(seconds=secs_per_km)
	return pace_timedelta

def convert_mps_to_mile_pace(mps):
	# Prevent divide by zero error
	if mps == 0:
		return None

	miles_per_sec = float(mps) / 1609.344
	secs_per_mile = int(1 / miles_per_sec)
	pace_timedelta = timedelta(seconds=secs_per_mile)
	return pace_timedelta

def format_elevation_for_uom_preference(m, user, show_uom_suffix=True):
	if user.elevation_uom_preference == "feet":
		uom_suffix = " feet" if show_uom_suffix else ""
		elevation_formatted ="{value}{uom_suffix}".format(value=int(float(m) * 3.28084), uom_suffix=uom_suffix) if m else None
	else:
		uom_suffix = " m" if show_uom_suffix else ""
		elevation_formatted ="{value}{uom_suffix}".format(value=int(m), uom_suffix=uom_suffix) if m else None
	return elevation_formatted

def format_distance(m):
	if m >= 1000:
		distance_formatted = "{value} km".format(value=convert_m_to_km(m))
	else:
		distance_formatted = "{value} m".format(value=m)
	return distance_formatted

def format_timedelta_minutes(timedelta):
	# don't try to format none
	if not timedelta:
		return None

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

def format_goal_units(goal_metric, value, user):
	if goal_metric == "Exercise Sets Completed":
		return "{sets} sets".format(sets=value)
	elif goal_metric == "Runs Completed Over Distance":
		return "{runs} run(s)".format(runs=value)
	elif goal_metric == "Weekly Distance":
		return format_distance_for_uom_preference(value, user)
	elif goal_metric == "Weekly Moving Time":
		return convert_seconds_to_minutes_formatted(value)
	elif goal_metric == "Weekly Elevation Gain":
		return format_elevation_for_uom_preference(value, user)
	elif goal_metric == "Time Spent Above Cadence":
		return convert_seconds_to_minutes_formatted(value)
	elif goal_metric == "Distance Climbing Above Gradient":
		return format_distance(value)

def current_year():
	return datetime.today().year

def today_formatted():
	return datetime.today().strftime("%d %B")

def seconds_to_datetime(seconds):
	base_datetime = datetime(2000, 1, 1, 0, 0)
	return base_datetime + timedelta(seconds=seconds)