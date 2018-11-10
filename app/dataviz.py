from flask import redirect, flash
import pandas as pd
from bokeh.core.properties import value
from bokeh.models import ColumnDataSource, HoverTool, TapTool, Plot, DatetimeTickFormatter, OpenURL, LabelSet, SingleIntervalTicker, LinearAxis, CustomJS, Arrow, NormalHead, CategoricalAxis
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


def generate_bar(dataset, plot_height, dimension_name, measure_name, measure_label_name=None, measure_label_function=None,
		dimension_type="continuous", max_dimension_range=None, goals_dataset=None, goal_measure_type="absolute", goal_dimension_type="value", tap_tool_callback=None):
	# IMPPRTANT: Assumes that data is ordered descending by dimension values when workinn out the axis range
	dimension_values = []
	measure_values = []
	measure_labels = []

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

	source=ColumnDataSource(dict(dimension=dimension_values,
								 measure=measure_values,
								 measure_label=measure_labels))

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
		goal_dimension_values = []
		goal_measure_values = []
		goal_measure_labels = []

		for row in goals_dataset:
			if goal_dimension_type == "value":
				goal_dimension_values.append(int(row.goal_dimension_value))
			else:
				goal_dimension_values.append(row.goal_description)

			if goal_measure_type == "absolute":
				goal_measure_values.append(row.goal_target)
				goal_measure_labels.append("Target: " + measure_label_function(row.goal_target))
			else:
				goal_measure_values.append(100)
				goal_measure_labels.append("Target: 100%")

		goals_source = ColumnDataSource(dict(dimension=goal_dimension_values,
											 measure=goal_measure_values,
											 measure_label=goal_measure_labels))

		# Update the max ranges
		if dimension_type == "continuous":
			if min(goal_dimension_values) < dimension_range_min:
				dimension_range_min = min(goal_dimension_values)-1

			if max(goal_dimension_values) > dimension_range_max:
				dimension_range_max = max(goal_dimension_values)+1
			
		if max(goal_measure_values) > measure_range_max:
			measure_range_max = max(goal_measure_values)

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
	plot.hbar(source=source, y="dimension", right="measure", height=bar_height, color="#0275d8", fill_alpha=0.8, hover_alpha=1)
	labels = LabelSet(source=source, x="measure", y="dimension", text="measure_label", level="glyph",
        x_offset=5, y_offset=-5, render_mode="canvas", text_font = "sans-serif", text_font_size = "7pt", text_color="#0275d8")
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


def generate_line_chart(dataset, plot_height, dimension_name, measure_name, measure_label_function=None):
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

	plot.line(source=source, x="dimension", y="measure", line_width=2)
	plot.circle(x=latest_dimension_value, y=latest_measure_value, size=6)

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