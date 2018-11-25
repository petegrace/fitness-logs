from flask import redirect, flash
from datetime import timedelta
import pandas as pd
from bokeh.core.properties import value
from bokeh.models import ColumnDataSource, HoverTool, TapTool, Plot, DatetimeTickFormatter, OpenURL, LabelSet, SingleIntervalTicker, LinearAxis, CustomJS, Arrow, NormalHead, CategoricalAxis, FuncTickFormatter
from bokeh.plotting import figure
import bokeh.layouts

def generate_stacked_bar_for_categories(dataset_query, user_categories, dimension, measure, dimension_type, plot_height, bar_direction="vertical", measure_units="", granularity="day", show_grid=True, show_yaxis=True):
	# Colour mappings
	available_categories = ["cat_green", "cat_green_outline", "cat_blue", "cat_blue_outline", "cat_red", "cat_red_outline", "cat_yellow", "cat_yellow_outline", "Uncategorised"]
	available_colors = ["#5cb85c", "#ffffff", "#0275d8", "#ffffff", "#d9534f", "#ffffff", "#f0ad4e", "#ffffff", "#ffffff"]
	available_line_colors = ["#5cb85c", "#5cb85c","#0275d8", "#0275d8", "#d9534f", "#d9534f", "#f0ad4e", "#f0ad4e", "#292b2c"]
	category_name_mappings = [(c.category_key, c.category_name) for c in user_categories]
	category_name_mappings.append(("Uncategorised", "Uncategorised"))

	# Reshape the data
	df = pd.read_sql(dataset_query.statement, dataset_query.session.bind)
	pivot_df = df.pivot(index=dimension, columns="category_key", values=measure)
	pivot_df = pivot_df.fillna(value=0)
	categories = df["category_key"].unique()
	dimension_list = pivot_df.index.values

	data = {dimension : dimension_list}
	colors = []
	line_colors = []
	names = []

	for category in categories:
		data[category] = pivot_df[category].values
		category_index =  available_categories.index(category) if category in available_categories else 8
		colors.append(available_colors[category_index])
		line_colors.append(available_line_colors[category_index]) #TODO: Need to assign the undefinned category if it can't be matched
		names.append([mapping[1] for mapping in category_name_mappings if mapping[0]==category][0] if category in available_categories else category)

	source = ColumnDataSource(data=data)

	if dimension_type == "datetime":
		#hover_tool = HoverTool(tooltips="@{dimension}{{%F}}: @$name {units}".format(dimension=dimension, units=measure_units),
		#					   formatters={dimension : "datetime"})
		plot = figure(x_axis_type="datetime", plot_height=plot_height, toolbar_location=None, tools=["tap"])

		if granularity == "day":
			bar_width = 60000000 # specified in ms
		elif granularity == "week":
			bar_width = 420000000
		plot.xaxis.formatter=DatetimeTickFormatter(days="%d %b", months="1st %b")
	else:
		plot = figure(x_range=dimension_list, plot_height=plot_height, toolbar_location=None)
		bar_width = 0.7 # specified as a proportion

	if bar_direction == "vertical":
		plot.vbar_stack(categories, x=dimension, width=bar_width, color=colors, source=source, line_color=line_colors, line_width=1.5, fill_alpha=0.7, line_alpha=0.7,
						 selection_fill_color=colors, selection_line_color=line_colors, selection_fill_alpha=1, selection_line_alpha=1,
						 nonselection_fill_color=colors, nonselection_line_color=line_colors, nonselection_fill_alpha=0.7, nonselection_line_alpha=0.7,
						 legend=[value(name) for name in names])
		if dimension_type != "datetime":
			plot.x_range = dimension_list

	elif bar_direction == "horizontal":
		plot.hbar_stack(categories, y=dimension, height=bar_width, color=colors, source=data, line_color=line_colors, line_width=1.5,
	             			legend=[value(name) for name in names])
		if dimension_type != "datetime":
			plot.y_range = dimension_list

	# Formatting
	plot.y_range.start = 0
	plot.xgrid.grid_line_color = None
	plot.axis.axis_line_color = "#cccccc"
	plot.axis.major_label_text_color = "#666666"
	plot.axis.major_label_text_font_size = "8pt"
	plot.axis.major_tick_line_color = "#cccccc"
	plot.outline_line_color = None
	plot.legend.padding = 5
	plot.legend.label_text_font = "sans-serif"
	plot.legend.label_text_color = "#666666"
	plot.legend.label_text_font_size = "7pt"
	plot.legend.location = "top_left"
	plot.legend.orientation = "horizontal"
	plot.sizing_mode = "scale_width"
	plot.yaxis.visible = show_yaxis
	plot.legend.visible = False

	if not show_grid:
		plot.grid.grid_line_color = None

	return plot, source


def prepare_goals_source(goals_dataset, goal_dimension_type, goal_measure_type, measure_label_function=None, goal_label_function=None):
	goal_dimension_values = []
	goal_measure_values = []
	goal_measure_labels = []
	goal_fill_colors = []
	goal_line_colors = []

	for row in goals_dataset:
		if goal_dimension_type == "value" and row.goal_dimension_value != "None":
			goal_dimension_values.append(int(row.goal_dimension_value))
		else:
			goal_dimension_values.append(row.goal_description)


		goal_progress_percent = (row.current_metric_value / row.goal_target) * 100

		if goal_measure_type == "absolute":
			goal_measure_values.append(row.goal_target)
			if goal_progress_percent >= 80:
				goal_measure_labels.append("") # Avoid overlapping off labels by hiding the target
			elif measure_label_function is not None:
				goal_measure_labels.append("Target: " + measure_label_function(row.goal_target))
			else:
				goal_measure_labels.append("Target: " + str(row.goal_target))
		else:
			goal_measure_values.append(100)
			if goal_label_function is not None:
				goal_measure_labels.append("Target: " + goal_label_function(goal_metric=row.goal_metric, value=row.goal_target))
			else:
				goal_measure_labels.append("Target: " + str(row.goal_target))

		goal_fill_colors.append(row.goal_category.fill_color if row.goal_category is not None else "#292b2c")
		goal_line_colors.append(row.goal_category.line_color if row.goal_category is not None else "#292b2c")

	goals_source = ColumnDataSource(dict(dimension=goal_dimension_values,
										 measure=goal_measure_values,
										 measure_label=goal_measure_labels,
										 fill_color=goal_fill_colors,
										 line_color=goal_line_colors))

	return goals_source


def generate_bar(dataset, plot_height, dimension_name, measure_name, measure_label_name=None, measure_label_function=None, category_field=None, fill_color=None, line_color=None,
		dimension_type="continuous", max_dimension_range=None, goals_dataset=None, goal_measure_type="absolute", goal_dimension_type="value", goal_label_function=None, tap_tool_callback=None):
	# IMPPRTANT: Assumes that data is ordered descending by dimension values when workinn out the axis range
	dimension_values = []
	measure_values = []
	measure_labels = []
	fill_colors = []
	line_colors = []

	if measure_label_name is None:
		measure_label_name = measure_name

	# Reshape the data for the bars
	for row in dataset:
		dimension_values.append(getattr(row, dimension_name))
		measure_values.append(getattr(row, measure_name))

		if measure_label_function is None:
			measure_labels.append(getattr(row, measure_label_name))
		else:
			measure_labels.append(measure_label_function(getattr(row, measure_label_name)))

		if category_field is not None:
			fill_colors.append(getattr(row, category_field).fill_color if getattr(row, category_field) is not None else "#292b2c")
			line_colors.append(getattr(row, category_field).line_color if getattr(row, category_field) is not None else "#292b2c")
		elif fill_color is not None:
			fill_colors.append(fill_color),
			line_colors.append(line_color)
		else:
			fill_colors.append("#292b2c")
			line_colors.append("#292b2c")

	source=ColumnDataSource(dict(dimension=dimension_values,
								 measure=measure_values,
								 measure_label=measure_labels,
								 fill_color=fill_colors,
								 line_color=line_colors))

	# Set the dimension ranges without knowledge of goal targets for now
	if dimension_type == "continuous":
		if max_dimension_range is None:
			dimension_range_min = dimension_values[-1]
			dimension_range_max = dimension_values[0]
		else:
			dimension_range_min = dimension_values[-1] if dimension_values[-1] > max_dimension_range[0] else max_dimension_range[0]
			dimension_range_max = dimension_values[0] if dimension_values[0] < max_dimension_range[1] else max_dimension_range[1]

	measure_range_max = max(measure_values)

	# Prep the goals data if we have any
	if goals_dataset is not None:
		goals_source = prepare_goals_source(goals_dataset=goals_dataset, goal_dimension_type=goal_dimension_type, goal_measure_type=goal_measure_type,
							measure_label_function=measure_label_function, goal_label_function=goal_label_function)

		# Update the max ranges
		if dimension_type == "continuous":
			if min(goals_source.data["dimension"]) < dimension_range_min:
				dimension_range_min = min(goals_source.data["dimension"])-1

			if max(goals_source.data["dimension"]) > dimension_range_max:
				dimension_range_max = max(goals_source.data["dimension"])+1
			
		if max(goals_source.data["measure"]) > measure_range_max:
			measure_range_max = max(goals_source.data["measure"])

	if dimension_type == "continuous":
		dimension_range = (dimension_range_min-1, dimension_range_max+1)
		bar_height = 1.2
		goal_bar_height = 1.8
	elif dimension_type == "discrete":
		dimension_range = dimension_values
		bar_height = 0.6
		goal_bar_height = 0.8
	measure_range = (-1, float(measure_range_max)*1.1)

	plot = figure(plot_height=plot_height, y_range=dimension_range, x_range=measure_range, toolbar_location=None, tooltips="@dimension: @measure_label", y_axis_type=None, tools=["tap"])
	plot.hbar(source=source, y="dimension", right="measure", height=bar_height, color="fill_color", line_color="line_color", fill_alpha=0.8, hover_color="fill_color", hover_alpha=1)
	labels = LabelSet(source=source, x="measure", y="dimension", text="measure_label", level="glyph",
        x_offset=5, y_offset=-5, render_mode="canvas", text_font = "sans-serif", text_font_size = "7pt", text_color="fill_color")
	plot.add_layout(labels)

	# Add dashed lines for any goal targets that are set
	if goals_dataset is not None:
		plot.hbar(source=goals_source, y="dimension", right="measure", height=goal_bar_height, fill_alpha=0, line_color="#666666")
		goal_labels = LabelSet(source=goals_source, x="measure", y="dimension", text="measure_label", level="glyph",
       		x_offset=5, y_offset=-5, render_mode="canvas", text_font = "sans-serif", text_font_size = "7pt", text_color="#666666")
		plot.add_layout(goal_labels)
	else:
		goals_source = None

	if tap_tool_callback is not None:
		tap_tool = plot.select(type=TapTool)
		tap_tool.callback = CustomJS(args=dict(source=source, goals_source=goals_source), code=tap_tool_callback)

	# TODO: This will need to be more flexible for data other than cadence
	if dimension_type == "continuous":
		y_ticker = SingleIntervalTicker(interval=4, num_minor_ticks=2)
		y_axis = LinearAxis(ticker=y_ticker)
	else:
		y_axis = CategoricalAxis()
	plot.add_layout(y_axis, "left")

	plot.xaxis.visible = False
	plot.sizing_mode = "scale_width"
	plot.axis.minor_tick_line_color = None
	plot.axis.axis_line_color = "#999999"
	plot.axis.major_label_text_color = "#666666"
	plot.axis.major_label_text_font_size = "7pt"
	plot.axis.major_tick_line_color = "#999999"
	plot.grid.grid_line_color = None
	plot.outline_line_color = None

	return plot


def generate_line_chart(dataset, plot_height, dimension_name, measure_name, measure_label_function=None, line_color=None, y_tick_function_code=None):
	dimension_values = []
	measure_values = []

	for row in dataset:
		dimension_values.append(getattr(row, dimension_name))
		measure_values.append(getattr(row, measure_name))

	source=ColumnDataSource(dict(dimension=dimension_values,
								 measure=measure_values))

	latest_dimension_value = [dimension_values[-1]]
	latest_measure_value = [measure_values[-1]]

	plot = figure(x_axis_type="datetime", plot_height=plot_height, toolbar_location=None)
	plot.xaxis.formatter=DatetimeTickFormatter(days="%d %b", months="1st %b")

	if y_tick_function_code is not None:
		plot.yaxis.formatter=FuncTickFormatter(code=y_tick_function_code)

	if line_color is None:
		line_color = "#292b2c"

	plot.line(source=source, x="dimension", y="measure", line_width=2, line_color=line_color)
	plot.circle(x=latest_dimension_value, y=latest_measure_value, size=6, color=line_color, line_color=line_color)

	plot.sizing_mode = "scale_width"
	plot.axis.minor_tick_line_color = None
	plot.axis.axis_line_color = "#999999"
	plot.axis.major_label_text_color = "#666666"
	plot.axis.major_label_text_font_size = "8pt"
	plot.axis.major_tick_line_color = "#cccccc"
	plot.xgrid.grid_line_color = None
	plot.ygrid.grid_line_color = "#eeeeee"
	plot.outline_line_color = None

	return plot


def generate_line_chart_for_categories(dataset_query, dimension, measure, dimension_type, plot_height, line_type="normal", user_categories=None, measure_label_function=None,
								goals_dataset=None, goal_measure_type="absolute", goal_dimension_type="value", tap_tool_callback=None):	
	# Colour mappings
	available_categories = ["cat_green", "cat_green_outline", "cat_blue", "cat_blue_outline", "cat_red", "cat_red_outline", "cat_yellow", "cat_yellow_outline", "Uncategorised"]
	available_colors = ["#5cb85c", "#ffffff", "#0275d8", "#ffffff", "#d9534f", "#ffffff", "#f0ad4e", "#ffffff", "#ffffff"]
	available_line_colors = ["#5cb85c", "#5cb85c","#0275d8", "#0275d8", "#d9534f", "#d9534f", "#f0ad4e", "#f0ad4e", "#292b2c"]
	category_name_mappings = [(c.category_key, c.category_name) for c in user_categories]
	category_name_mappings.append(("Uncategorised", "Uncategorised"))

	# Reshape the data
	df = pd.read_sql(dataset_query.statement, dataset_query.session.bind)
	pivot_df = df.pivot(index=dimension, columns="category_key", values=measure)
	pivot_df = pivot_df.fillna(value=0)

	if line_type == "cumulative":
		pivot_df = pivot_df.cumsum()

	categories = df["category_key"].unique()
	dimension_list = pivot_df.index.values

	data = {dimension : dimension_list}
	colors = {}
	line_colors = {}
	line_dashes = {}
	names = {}

	for category in categories:
		data[category] = pivot_df[category].values
		category_index =  available_categories.index(category) if category in available_categories else 8
		colors[category] = available_colors[category_index]
		line_colors[category] = available_line_colors[category_index] #TODO: Need to assign the undefinned category if it can't be matched
		line_dashes[category] = "solid" if "outline" not in category else "dashed"
		names[category] = [mapping[1] for mapping in category_name_mappings if mapping[0]==category][0] if category in available_categories else category

	source = ColumnDataSource(data=data)

	plot = figure(x_axis_type="datetime", plot_height=plot_height, toolbar_location=None, tools=["tap"])
	plot.xaxis.formatter=DatetimeTickFormatter(days="%d %b", months="1st %b")

	latest_dimension_value = data[dimension][-1]

	for category in categories:
		latest_measure_value = data[category][-1]
		plot.line(source=source, x=dimension, y=category, line_width=2, line_color=line_colors[category], line_dash=line_dashes[category],
						 legend=names[category], name=category)
		plot.circle(source=source, x=dimension, y=category, size=6, line_color=line_colors[category], line_width=2, color=colors[category])

	# Prep the goals data if we have any
	if goals_dataset is not None:
		if len(goals_dataset) > 0:
			goals_source = prepare_goals_source(goals_dataset=goals_dataset, goal_dimension_type=goal_dimension_type, goal_measure_type=goal_measure_type, measure_label_function=measure_label_function)
			goal_end_date = goals_dataset[0].goal_start_date + timedelta(days=6)
			plot.circle(source=goals_source, x=goal_end_date, y="measure", line_color="line_color", color="#eeeeee", size=10)
			plot.circle(source=goals_source, x=goal_end_date, y="measure", line_color="line_color", color="fill_color", size=4)
			#TODO: should label the target


	if tap_tool_callback is not None:
		tap_tool = plot.select(type=TapTool)
		tap_tool.callback = CustomJS(args=dict(source=source), code=tap_tool_callback)

	plot.sizing_mode = "scale_width"
	plot.axis.minor_tick_line_color = None
	plot.axis.axis_line_color = "#999999"
	plot.axis.major_label_text_color = "#666666"
	plot.axis.major_label_text_font_size = "8pt"
	plot.axis.major_tick_line_color = "#cccccc"
	plot.xgrid.grid_line_color = None
	plot.ygrid.grid_line_color = "#eeeeee"
	plot.outline_line_color = None
	plot.legend.padding = 5
	plot.legend.label_text_font = "sans-serif"
	plot.legend.label_text_color = "#666666"
	plot.legend.label_text_font_size = "8pt"
	plot.legend.location = "top_left"

	return plot