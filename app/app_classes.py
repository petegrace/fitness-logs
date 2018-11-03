class TempCadenceAggregate():
	cadence = None
	total_seconds_above_cadence = None

	def __init__(self, cadence, total_seconds_above_cadence):
		self.cadence = cadence
		self.total_seconds_above_cadence = total_seconds_above_cadence

	def __repr__(self):
		return "<TempCadenceAggregate for {cadence}>".format(cadence=self.cadence)