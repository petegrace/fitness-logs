from flask import redirect, flash
import pandas as pd
from bokeh.core.properties import value
from bokeh.models import ColumnDataSource, HoverTool, TapTool, Plot, DatetimeTickFormatter, OpenURL, LabelSet, SingleIntervalTicker, LinearAxis, CustomJS
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
		category_index =  available_categories.index(category)
		colors.append(available_colors[category_index])
		line_colors.append(available_line_colors[category_index])
		names.append([mapping[1] for mapping in category_name_mappings if mapping[0]==category][0])

	source = ColumnDataSource(data=data)

	if dimension_type == "datetime":
		hover_tool = HoverTool(tooltips="@{dimension}{{%F}}: @$name {units}".format(dimension=dimension, units=measure_units),
							   formatters={dimension : "datetime"})
		plot = figure(x_axis_type="datetime", plot_height=plot_height, toolbar_location=None, tools=["tap"])

		if granularity == "day":
			bar_width = 50000000 # specified in ms
		elif granularity == "week":
			bar_width = 350000000
		plot.xaxis.formatter=DatetimeTickFormatter(days="%d %b")
	else:
		plot = figure(x_range=dimension_list, plot_height=plot_height, toolbar_location=None)
		bar_width = 0.7 # specified as a proportion

	if bar_direction == "vertical":
		plot.vbar_stack(categories, x=dimension, width=bar_width, color=colors, source=source, line_color=line_colors, line_width=1.5, fill_alpha=0.8,
							hover_alpha=1, hover_fill_color=colors, hover_line_color="#333333", legend=[value(name) for name in names])
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
	plot.axis.minor_tick_line_color = None
	plot.axis.axis_line_color = "#cccccc"
	plot.axis.major_label_text_color = "#666666"
	plot.axis.major_label_text_font_size = "7pt"
	plot.axis.major_tick_line_color = None
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


def generate_bar(dataset, plot_height, dimension_name, measure_name, measure_label_name=None, max_dimension_range=None):
	dimension_values = []
	measure_values = []
	measure_labels = []

	if measure_label_name is None:
		measure_label_name = measure_name

	# Reshape the data for the bars
	for row in dataset:
		dimension_values.append(getattr(row, dimension_name))
		measure_values.append(getattr(row, measure_name))
		measure_labels.append(getattr(row, measure_label_name))

	source=ColumnDataSource(dict(dimension=dimension_values,
								 measure=measure_values,
								 measure_label=measure_labels))

	if max_dimension_range is None:
		dimension_range_min = dimension_values[-1]
		dimension_range_max = dimension_values[0]
	else:
		dimension_range_min = dimension_values[-1] if dimension_values[-1] > max_dimension_range[0] else max_dimension_range[0]
		dimension_range_max = dimension_values[0] if dimension_values[0] < max_dimension_range[1] else max_dimension_range[1]

	dimension_range = (dimension_range_min-2, dimension_range_max+2)
	measure_range = (-1, max(measure_values)*1.1)

	labels = LabelSet(source=source, x="measure", y="dimension", text="measure_label", level="glyph",
        x_offset=5, y_offset=-5, render_mode="canvas", text_font = "sans-serif", text_font_size = "7pt", text_color="#0275d8")
	y_ticker = SingleIntervalTicker(interval=4, num_minor_ticks=2)
	y_axis = LinearAxis(ticker=y_ticker)

	plot = figure(plot_height=plot_height, y_range=dimension_range, x_range=measure_range, toolbar_location=None, tooltips="@dimension for @measure_label", y_axis_type=None)
	plot.hbar(source=source, y="dimension", right="measure", height=1.2, color="#0275d8", fill_alpha=0.8, hover_alpha=1)
	plot.add_layout(labels)
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