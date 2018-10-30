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