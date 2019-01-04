class TempCadenceAggregate():
	cadence = None
	total_seconds_above_cadence = None

	def __init__(self, cadence, total_seconds_above_cadence):
		self.cadence = cadence
		self.total_seconds_above_cadence = total_seconds_above_cadence

	def __repr__(self):
		return "<TempCadenceAggregate for {cadence}>".format(cadence=self.cadence)

class TempGradientAggregate():
	gradient = None
	total_metres_above_gradient = None

	def __init__(self, gradient, total_metres_above_gradient):
		self.gradient = gradient
		self.total_metres_above_gradient = total_metres_above_gradient

	def __repr__(self):
		return "<TempCadenceAggregate for {gradient}>".format(gradient=self.gradient)

class PlotComponentContainer():
	name = None
	plot_div = None
	plot_script = None

	def __init__(self, name, plot_div, plot_script):
		self.name = name
		self.plot_div = plot_div
		self.plot_script = plot_script