from flask import redirect, flash
import pandas as pd
from bokeh.core.properties import value
from bokeh.models import ColumnDataSource, HoverTool, TapTool, Plot, DatetimeTickFormatter, OpenURL
from bokeh.plotting import figure
import bokeh.layouts

def generate_stacked_bar_for_categories(dataset_query, user_categories, dimension, measure, dimension_type, plot_height, bar_direction):
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

	if dimension_type == "datetime":
		hover_tool = HoverTool(tooltips="@{dimension}{{%F}}: @$name completed sets".format(dimension=dimension),
							   formatters={dimension : "datetime"})
		plot = figure(x_axis_type="datetime", plot_height=plot_height, toolbar_location=None, tools=[hover_tool])
		bar_width = 50000000 # specified in ms
		plot.xaxis.formatter=DatetimeTickFormatter(days="%d %b")
	else:
		plot = figure(x_range=dimension_list, plot_height=plot_height, toolbar_location=None)
		bar_width = 0.7 # specified as a proportion

	if bar_direction == "vertical":
		plot.vbar_stack(categories, x=dimension, width=bar_width, color=colors, source=data, line_color=line_colors, line_width=1.5, fill_alpha=0.8,
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
	plot.axis.axis_line_color = "#999999"
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

	# TODO: means for using the chart as navigation, we'd probably need to use some custom JS to open in the same tab
	# REMEMBER TO ADD "tap" to the tools
	# url = "/index?date=@{dimension}".format(dimension=dimension)
	# tap_tool = plot.select(type=TapTool)
	# tap_tool.callback = OpenURL(url=url)

	return plot