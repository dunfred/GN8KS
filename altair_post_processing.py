'''
def custom_altair_chart_to_json(*args, **kwargs):
  """Calls post-processing before returning json string."""
  try:
    vegalite_post_processor.post_process_chart(args[0])
  except Exception:  # pylint: disable=broad-exception-caught
    pass
  return alt.SchemaBase.to_json(*args, **kwargs)
'''


"""Vega-Lite post processor to run after LLM-generated altair is executed."""

import re
from typing import Any
from typing import Union

import altair as alt
import pandas as pd
import pandas.api.types

is_datetime = pandas.api.types.is_datetime64_any_dtype
is_numeric = pandas.api.types.is_numeric_dtype
guess_datetime_format = pd._libs.tslibs.parsing.guess_datetime_format  # pylint: disable=protected-access
Undefined = alt.utils.schemapi.Undefined


COLUMN_NAME_CHARACTER_REPLACEMENTS = {
    '[': '(',
    ']': ')',
    '.': ' ',
    ':': '_',
    "'": '',
}
MAX_LEGEND_SIZE = 48
DEFAULT_MAX_BINS = 30
DEFAULT_PIE_RADIUS = 120
DISTANCE_OF_LABEL_FROM_WEDGE = 20
MAX_PIE_WEDGES = 24
MAX_VERTICAL_BARS = 25
MIN_POINTS_NEEDED_FOR_TYPE_CONVERSION = 10
MAX_HEATMAP_LABELED_X_VALUES = 20
DEFAULT_COLORS = [
    '#1A73E8',
    '#12B5CB',
    '#F538A0',
    '#FA903E',
    '#C58AF9',
    '#81C995',
    '#FCC934',
    '#9AA0A6',
    '#185ABC',
    '#129EAF',
    '#E52592',
    '#D56E0C',
    '#A142F4',
    '#1E8E3E',
    '#F9AB00',
    '#5F6368',
    '#669DF6',
    '#4ECDE6',
    '#FF8BCB',
    '#FCAD70',
    '#E9D2FD',
    '#A8DAB5',
    '#FDD663',
    '#BDC1C6',
]


def has_defined_attr(chart: Any, attr: str) -> bool:
  """Returns True if chart.attr exists and is defined."""
  return hasattr(chart, attr) and chart[attr] is not Undefined


def get_mark_type(chart: alt.TopLevelMixin) -> Union[str, None]:
  if not has_defined_attr(chart, 'mark'):
    return None
  if isinstance(chart.mark, str):
    return chart.mark
  if has_defined_attr(chart.mark, 'type') and isinstance(chart.mark.type, str):
    return chart.mark.type
  return None


def flatten_nesting_and_copy_dataframes_recursive(
    chart: alt.TopLevelMixin,
    data: pd.DataFrame,
    nesting_attrs: list[str],
    flattened_list: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
) -> None:
  """Recursively populates `flattened_list` with charts nested within `chart`.

  This also replaces all the DataFrames in `chart` with copies (these copies are
  also added to the flattened list). These copies are made so that, when we
  modify DataFrames in the post-processors following this, we don't modify
  DataFrames defined in the coding environment (in case future code references
  it again.)

  Args:
    chart: A chart somewhere in a nested chart structure.
    data: The DataFrame referenced by `chart`. This must be kept track of
      separately because it is not always in `chart.data` for nested charts.
    nesting_attrs: List of nesting attribute names we are flattening over.
      Contents could be any of "vconcat", "hconcat", or "layer".
    flattened_list: Running flattened list of (non-nested chart, data) tuples.
  """
  bottom_level = True  # True if `chart` has no nesting below it.
  for attr in nesting_attrs:
    if has_defined_attr(chart, attr):
      bottom_level = False
      for nested_chart in getattr(chart, attr):
        if has_defined_attr(nested_chart, 'data'):
          # If we have found a new DataFrame, replace it with a copy.
          nested_chart.data = nested_chart.data.copy()
          nested_chart_data = nested_chart.data
        else:
          nested_chart_data = data
        flatten_nesting_and_copy_dataframes_recursive(
            nested_chart, nested_chart_data, nesting_attrs, flattened_list
        )
  if bottom_level:  # Store only non-nested charts.
    flattened_list.append((chart, data))


def flatten_layers(
    chart: alt.TopLevelMixin, data: Union[pd.DataFrame, Any] = None
) -> list[tuple[alt.TopLevelMixin, pd.DataFrame]]:
  """Flattens `chart` into list of non-concatenated charts.

  Args:
    chart: Top-level, potentially layered Altair chart to flatten layers of.
    data: DataFrame referenced by `chart` (in chase `chart` is in a concatenated
      chart and `chart.data` may be Undefined). If None, will assume DataFrame
      is in `chart.data`.

  Returns:
    List of (non-layered chart, DataFrame for non-layered chart) tuples.
  """
  if data is None:
    data = chart.data
  all_layers = []
  flatten_nesting_and_copy_dataframes_recursive(
      chart, data, ['layer'], all_layers
  )
  return all_layers


def flatten_concats(
    chart: alt.TopLevelMixin,
) -> list[tuple[alt.TopLevelMixin, pd.DataFrame]]:
  """Flattens `chart` into list of non-concatenated charts.

  Args:
    chart: Top-level, potentially concatenated Altair chart to flatten
      concatenation of.

  Returns:
    List of (non-concatenated chart, DataFrame for non-concatenated chart)
      tuples.
  """
  all_concats = []
  # If `chart` has a top-level DataFrame, make a copy
  # (flatten_nesting_and_copy_dataframes_recursive will copy all the DataFrames
  # from inner nested charts).
  if chart.data is not Undefined:
    chart.data = chart.data.copy()
  flatten_nesting_and_copy_dataframes_recursive(
      chart, chart.data, ['vconcat', 'hconcat'], all_concats
  )
  return all_concats


def get_defined_encodings_with_field(chart: alt.TopLevelMixin) -> list[Any]:
  """Gets flat list of defined encodings with defined 'field' in `chart`."""
  encodings = []
  if has_defined_attr(chart, 'encoding') and hasattr(chart.encoding, '_kwds'):
    # The following is adapted from how altair source code finds all values in
    # the chart encoding:
    # http://google3/third_party/py/altair/utils/schemapi.py;l=273;rcl=621686387
    for encoding in chart.encoding._kwds.values():  # pylint: disable=protected-access
      if encoding is Undefined:
        continue
      if isinstance(encoding, list):  # Common with e.g. tooltips.
        for list_encoding_entry in encoding:
          if has_defined_attr(list_encoding_entry, 'field'):
            encodings.append(list_encoding_entry)
      else:
        if has_defined_attr(encoding, 'field'):
          encodings.append(encoding)
  return encodings


def is_continuous(field_type: str) -> bool:
  """True if `field_type` is continuous rather than discrete."""
  return field_type in {'quantitative', 'temporal'}


def sanitize_column_names(chart: alt.TopLevelMixin, data: pd.DataFrame) -> None:
  """Replaces characters in column names that Vega-Lite can't render with.

  Args:
    chart: Single, non-concatenated/non-layered Altair chart.
    data: DataFrame referenced by `chart`.
  """
  # Replace prohibited characters in column names in DataFrame.
  for prohibited, replacement in COLUMN_NAME_CHARACTER_REPLACEMENTS.items():
    for column in data.columns:
      if prohibited not in column:
        continue
      data.rename(
          columns={column: column.replace(prohibited, replacement)},
          inplace=True,
      )

  # Replace prohibited characters in `field` parameter for any defined chart
  # encodings.
  encodings = get_defined_encodings_with_field(chart)
  for encoding in encodings:
    for prohibited, replacement in COLUMN_NAME_CHARACTER_REPLACEMENTS.items():
      if prohibited not in encoding.field:
        continue
      encoding.field = encoding.field.replace(prohibited, replacement)


def remove_duplicate_selectors(
    layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
) -> bool:
  """Remove duplicate selectors (based on name) from the layers.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.

  Returns:
    True if chart was modified.
  """
  modified_chart = False
  selector_names = set()
  for layer, _ in layers:
    if not has_defined_attr(layer, 'selection'):
      continue
    duplicate_selectors = []
    # Check each selector in the selection. If we have seen it already,
    # mark it for deletion. Otherwise, add it to `selector_names` so that
    # prevent it from having duplicates.
    for selector in layer.selection.keys():
      if selector in selector_names:
        duplicate_selectors.append(selector)
      else:
        selector_names.add(selector)
    # Remove all duplicate selectors.
    for selector in duplicate_selectors:
      del layer.selection[selector]
      modified_chart = True
    # If we have emptied out the selection, remove it from the layer.
    if not layer.selection:
      layer.selection = Undefined

  return modified_chart


def scale_axes(layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]]) -> None:
  """Adds axes scales based on min and max of x and y.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.
  """
  deny_list_mark_types = {'arc', 'area', 'bar', 'rect', 'geoshape', 'rule'}
  for layer, _ in layers:
    if get_mark_type(layer) in deny_list_mark_types:
      return

  for layer, data in layers:
    if not has_defined_attr(layer, 'encoding'):
      continue

    for variable in [layer.encoding.x, layer.encoding.y]:
      if variable is Undefined or variable.field is Undefined:
        continue
      if variable.type != 'quantitative':
        continue
      if variable.scale is not Undefined:
        # We should respect any scale deliberately added by the LLM code.
        continue
      if variable.bin is not Undefined or variable.aggregate is not Undefined:
        # min and max of variables may not be good scales for binned or
        # aggregated data.
        continue

      variable_min = data.min(numeric_only=True)[variable.field]
      variable_max = data.max(numeric_only=True)[variable.field]
      variable_mean = data.mean(numeric_only=True)[variable.field]
      # Set bounds to be slightly beyond the min and max, so we don't cut off
      # any points on the boundaries.
      lower_bound = variable_min - 0.15 * (variable_mean - variable_min)
      upper_bound = variable_max + 0.15 * (variable_max - variable_mean)
      # If lower_bound is negative and all values of this variable are
      # non-negative, set lower_bound to 0. This prevents a weird-looking
      # situation where the axis for entirely non-negative data shows negative
      # values.
      if lower_bound < 0 and (data[variable.field] >= 0).all():
        lower_bound = 0
      variable.scale = alt.Scale(domain=[lower_bound, upper_bound])


def remove_legend_none(chart: alt.Chart) -> None:
  """Removes legend=None from pie charts' and heatmaps' color property.

  legend=None gets added by the model sometimes and makes pie charts and
  heatmaps strictly worse.

  Args:
    chart: Single, non-concatenated/non-layered Altair chart.
  """
  if get_mark_type(chart) not in {'arc', 'rect'}:
    return
  if (
      not has_defined_attr(chart, 'encoding')
      or not has_defined_attr(chart.encoding, 'color')
      or not has_defined_attr(chart.encoding.color, 'legend')
  ):
    return

  if chart.encoding.color.legend is None:
    chart.encoding.color.legend = Undefined


def maybe_remove_legend_variables(
    layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
) -> None:
  """Conditionally removes colors, shapes & legend based on number of series.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.
  """
  all_mark_types = {get_mark_type(layer[0]) for layer in layers}
  # Leave pie charts as is (shapes don't apply and removing colors makes them
  # meaningless).
  if 'arc' in all_mark_types or 'rect' in all_mark_types:
    return

  legend_variables = ['color', 'shape']
  for layer, data in layers:
    # Either color or shape can appear on the legend (if both are Undefined,
    # no legend will appear).
    for variable in legend_variables:
      if not has_defined_attr(layer.encoding, variable) or not has_defined_attr(
          layer.encoding[variable], 'field'
      ):
        continue

      # Find number of series (i.e. different entries for `variable` in legend).
      num_series = data[layer.encoding[variable].field].nunique()
      # If there is only one series on the legend remove
      # the variable on it (color or shape).
      if num_series == 1:
        layer.encoding[variable] = Undefined


def assign_default_colors(chart: alt.Chart, data: pd.DataFrame):
  """Assigns default color scheme to single (i.e. non-layered) chart.

  Args:
    chart: Single, non-concatenated/non-layered Altair chart.
    data: DataFrame referenced by `chart`.
  """

  def assign_colors(domains):
    """Assigns hex codes cyclically to each domain element."""
    num_hex_codes = len(DEFAULT_COLORS)
    return [
        DEFAULT_COLORS[idx % num_hex_codes] for idx, _ in enumerate(domains)
    ]

  def is_color_scale_defined(chart):
    """Check if color scale is explicitly defined in the chart."""
    return (
        has_defined_attr(chart.config, 'mark')
        and has_defined_attr(chart.config.mark, 'color')
    ) or (
        has_defined_attr(chart.encoding.color, 'scale')
        and has_defined_attr(chart.encoding.color.scale, 'range')
    )

  # Early return if chart has explicitly defined color scale
  if is_color_scale_defined(chart):
    return

  # Assign default color if no color encoding is present in the chart.
  # Note that, since this is just setting color to a single value, it will not
  # introduce a legend.
  if chart.encoding.color is Undefined:
    chart.encoding.color = alt.Color(value=DEFAULT_COLORS[0])
    return

  # If the color is defined with a continuous type, return (we would assign too
  # many colors to a continuous color scale).
  if is_continuous(chart.encoding.color.type):
    return

  # Assign multiple colors cyclically from DEFAULT_COLORS
  # Handle color scale definition
  if has_defined_attr(chart.encoding.color, 'scale') and has_defined_attr(
      chart.encoding.color.scale, 'domain'
  ):
    # Scale and domain explicitly declared in chart creation
    domains = chart.encoding.color.scale.domain
  else:
    # Scale and domain not declared in chart creation
    # Use legend to find color mapping
    legend_field = chart.encoding.color.field
    domains = sorted(data[legend_field].unique().tolist())

  colors = assign_colors(domains)
  chart.encoding.color.scale = alt.Scale(domain=domains, range=colors)


def format_labeled_pie_chart(
    layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
) -> None:
  """For pie charts, format pie and text (if available).

  If the pie has no labels, we will add stack and order. If the pie has labels,
  we will do that, plus make sure the text layer is in the right position. This
  includes updating the radius of the arcs and the text.

  We don't support more than one pie layer or more than one text layer.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.
  """
  # Chart must have a pie layer and no more than one text layer.
  pie_layers = [layer for layer in layers if get_mark_type(layer[0]) == 'arc']
  text_layers = [layer for layer in layers if get_mark_type(layer[0]) == 'text']

  # If we have more than one pie or no pies, return.
  if len(pie_layers) != 1:
    return
  # Second [0] is to get just the Altair chart (we don't need the DataFrames).
  pie_layer = pie_layers[0][0]

  # More than one text layer is not supported.
  if len(text_layers) > 1:
    return

  # Set pie order to descending by value.
  pie_layer.encoding.order = alt.Order(
      field=pie_layer.encoding.theta.field,
      type=pie_layer.encoding.theta.type,
      sort='descending',
  )

  # Make sure theta has the stack property set to True or "normalize", otherwise
  # the labels will be in the wrong positions. Note that the FE will add labels
  # to the pie, even if the spec doesn't include them.
  uses_normalize = False
  if has_defined_attr(pie_layer.encoding, 'theta'):
    if (
        has_defined_attr(pie_layer.encoding.theta, 'stack')
        and pie_layer.encoding.theta.stack == 'normalize'
    ):
      uses_normalize = True
    else:
      pie_layer.encoding.theta.stack = True

  # If the pie doesn't have labels, then we are done. Otherwise, we need to
  # make sure the text layer is in the right position.
  if not text_layers:
    return
  text_layer = text_layers[0][0]

  # If no explicit outerRadius was set for pie layer, set default outerRadius.
  if isinstance(pie_layer.mark, str):
    pie_layer.mark = alt.MarkDef(type='arc', outerRadius=DEFAULT_PIE_RADIUS)
  elif not has_defined_attr(pie_layer.mark, 'outerRadius'):
    pie_layer.mark.outerRadius = DEFAULT_PIE_RADIUS

  # Set text radius to be slightly outside pie radius.
  text_radius = pie_layer.mark.outerRadius + DISTANCE_OF_LABEL_FROM_WEDGE
  if isinstance(text_layer.mark, str):
    text_layer.mark = alt.MarkDef(type='text')
  text_layer.mark.radius = text_radius

  # Set pie and text order to be the same, specifically descending by value.
  text_layer.encoding.order = pie_layer.encoding.order

  if has_defined_attr(text_layer.encoding, 'theta'):
    text_layer.encoding.theta.stack = 'normalize' if uses_normalize else True


def remove_extra_wedges(
    layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
) -> None:
  """Function to remove extra wedges of a pie chart.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.
  """
  pie_layers = [layer for layer in layers if get_mark_type(layer[0]) == 'arc']
  # We should only aggregate wedges if there is exactly one pie layer.
  if len(pie_layers) != 1:
    return
  pie_layer, pie_data = pie_layers[0]

  # Retrieve theta and color fields from "encoding" container
  theta_column, color_column = None, None
  if has_defined_attr(pie_layer, 'encoding') and has_defined_attr(
      pie_layer.encoding, 'theta'
  ):
    theta_column = pie_layer.encoding.theta.field
  if has_defined_attr(pie_layer, 'encoding') and has_defined_attr(
      pie_layer.encoding, 'color'
  ):
    color_column = pie_layer.encoding.color.field
  # Return if either theta or color field is missing
  if (
      not theta_column
      or theta_column is Undefined
      or not color_column
      or color_column is Undefined
  ):
    return

  # Get the number of unique wedges in the pie chart based on the "color" field
  num_wedges = pie_data[color_column].nunique()

  # Return if the number of wedges is less than `MAX_PIE_WEDGES` + 1
  if num_wedges < MAX_PIE_WEDGES + 1:
    return

  # Sort the `data` in descending order of `theta_column` and keep the first
  # `MAX_PIE_WEDGES` - 1 rows.
  sorted_df = pie_data.sort_values(
      by=theta_column, ascending=False
  ).reset_index(drop=True)
  subset_df = sorted_df.head(MAX_PIE_WEDGES - 1)
  # Aggregate remaining rows into a single row.
  aggregated_row = sorted_df.iloc[MAX_PIE_WEDGES - 1 :].sum()
  # Replace object/str type fields with "Other".
  aggregated_row = aggregated_row.apply(
      lambda x: 'Other' if isinstance(x, str) else x
  )
  aggregated_row.name = 'Aggregated'
  new_data = pd.concat(
      [subset_df, aggregated_row.to_frame().T], ignore_index=True
  ).reset_index(drop=True)

  # Replace pie_data with new_data in place.
  pie_data.update(new_data)
  # Update will only replace as many rows as are in new_data, so drop the rest.
  pie_data.drop(range(len(new_data), len(pie_data)), inplace=True)


def maybe_make_bar_or_box_chart_horizontal(
    layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
) -> None:
  """Conditionally swaps x and y axes of `chart`.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.
  """

  def should_rotate(chart, data):
    # We should only consider rotating bar or box charts.
    if get_mark_type(chart) not in {'bar', 'boxplot'}:
      return False
    if not has_defined_attr(chart.encoding, 'x') or not has_defined_attr(
        chart.encoding, 'y'
    ):
      return False
    # We only need to consider rotating if the x variable is discrete.
    if is_continuous(chart.encoding.x.type):
      return False

    num_x_categories = data[chart.encoding.x.field].nunique()
    # If the y variable is also discrete, we should only rotate if it has fewer
    # unique values than the x variable.
    if not is_continuous(chart.encoding.y.type):
      num_y_categories = data[chart.encoding.y.field].nunique()
    else:
      num_y_categories = 0

    if (
        num_x_categories > MAX_VERTICAL_BARS
        and num_x_categories > num_y_categories
    ):
      return True
    return False

  def rotate_chart(chart):
    if not hasattr(chart.encoding, 'x') or not hasattr(chart.encoding, 'y'):
      return
    tmp = chart.encoding.x
    chart.encoding.x = chart.encoding.y
    chart.encoding.y = tmp

    # We should not carry over the labelAngle when swapping the axes.
    for encoding_var in [chart.encoding.x, chart.encoding.y]:
      if has_defined_attr(encoding_var, 'axis') and has_defined_attr(
          encoding_var.axis, 'labelAngle'
      ):
        encoding_var.axis.labelAngle = Undefined
        if encoding_var.axis == alt.Axis():
          encoding_var.axis = Undefined

  # If we find we need to rotate any layer, we should rotate all of them,
  # since they likely share axes.
  if any([should_rotate(layer, data) for layer, data in layers]):
    for layer, _ in layers:
      rotate_chart(layer)


def match_bar_grouping_with_orientation(chart: alt.TopLevelMixin) -> None:
  """Make sure `column` or `row` matches bar orientation in grouped bar charts.

  We should not have vertical bar charts with `row` set or horizontal bar charts
  with `column` set. Currently, this function is only handling the latter case.

  Args:
    chart: Single, non-concatenated/non-layered Altair chart.
  """
  # Only consider bar or boxplot charts.
  if get_mark_type(chart) not in {'bar', 'boxplot'}:
    return
  # Only consider charts with exactly one of `column` or `row` defined.
  if has_defined_attr(chart.encoding, 'row') == has_defined_attr(
      chart.encoding, 'column'
  ):
    return
  if not has_defined_attr(chart.encoding, 'x') or not has_defined_attr(
      chart.encoding, 'y'
  ):
    return
  # If both x and y are discrete, the bars will appear as squares rather than
  # extend from an axis, so bar orientation doesn't apply.
  if not is_continuous(chart.encoding.x.type) and not is_continuous(
      chart.encoding.y.type
  ):
    return

  # Determine bar orientation. Bar charts will only be horizontal if the x axis
  # is continuous and the y axis is discrete.
  is_horizontal_bar = is_continuous(
      chart.encoding.x.type
  ) and not is_continuous(chart.encoding.y.type)

  # For the moment, it is very unlikely that the model will add a `row`
  # encoding incorrectly. Rather, we see the model being overly aggressive in
  # adding a `column` (or the `column` is left over from our rotating a bar
  # chart to be horizontal). In the spririt of having fewer post processors,
  # we will only handle that case. If the model starts using `row` more often,
  # we can revisit this.
  if is_horizontal_bar and has_defined_attr(chart.encoding, 'column'):
    # Copy all defined attributes from column to row (alt.Column and alt.Row
    # have identical constructors and attributes).
    column_encoding_attrs = {
        k: v
        for k, v in chart.encoding.column._kwds.items()  # pylint: disable=protected-access
        if hasattr(alt.Row(), k) and v is not Undefined
    }
    chart.encoding.row = alt.Row(**column_encoding_attrs)
    chart.encoding.column = Undefined

    # Change header properties to apply to row rather than columns.
    if has_defined_attr(chart.encoding.row, 'header'):
      if (
          has_defined_attr(chart.encoding.row.header, 'titleOrient')
          and chart.encoding.row.header.titleOrient == 'bottom'
      ):
        chart.encoding.row.header.titleOrient = 'left'
      if (
          has_defined_attr(chart.encoding.row.header, 'labelOrient')
          and chart.encoding.row.header.labelOrient == 'bottom'
      ):
        chart.encoding.row.header.labelOrient = 'left'


def maybe_update_types_and_formats(
    layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
) -> None:
  """Corrects type and updates format of mis-types fields in `chart`.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.
  """
  # Do not try to change the data type of any field in heat maps. Heatmaps do
  # not support continuous axes values, and converting strings into continuous
  # values is basically all we are doing here.
  deny_list_mark_types = {'rect'}
  for layer, _ in layers:
    if get_mark_type(layer) in deny_list_mark_types:
      return

  def is_not_string_column(column):
    return column.dtype != 'object' and column.dtypes != pd.StringDtype()

  def convert_date(column):
    """Attempt to convert column to datetime."""
    if is_datetime(column):
      # If column is date time, do nothing
      return None, None, None
    try:
      if is_numeric(column):
        # Make sure the first value looks like a year before trying to convert
        # them all to years.
        pd.to_datetime(column[0], errors='raise', format='%Y')
        return (
            pd.to_datetime(column, errors='raise', format='%Y'),
            'temporal',
            '%Y',
        )
      else:
        datetime_format = guess_datetime_format(column[0])
        if datetime_format:
          return (
              pd.to_datetime(column, errors='raise', format=datetime_format),
              'temporal',
              datetime_format,
          )
    except ValueError:
      return None, None, None
    return None, None, None

  def convert_number(column):
    """Attempt to convert column to float."""
    if is_not_string_column(column):
      # If column is numerical, do nothing
      return None, None, None
    try:
      float_column = column.astype(float)
      return float_column, 'quantitative', None
    except ValueError:
      return None, None, None

  def convert_currency(column):
    """Attempt to convert column with leading currency symbol to float."""
    if is_not_string_column(column):
      # If columns is not a string, do nothing
      return None, None, None
    # If any non-empty values of column don't contain currency, do nothing.
    currency_regex = r'(?:^\s*(\$|€|£|¥))|(?:(\$|€|£|¥)\s*$)'
    regex_searches = []
    for value in column.dropna().astype(str):
      search = re.search(currency_regex, value)
      if not search:
        return None, None, None
      regex_searches.append(search)
    # If more than one currency symbol is featured, do nothing. (We can't format
    # them consistently otherwise.)
    currencies = set()
    for search in regex_searches:
      if search is None:
        continue
      if search.group(1) is not None:  # Currency symbol before number
        currencies.add(search.group(1))
      elif search.group(2) is not None:  # Currency symbol after number
        currencies.add(search.group(2))
    if len(currencies) != 1:
      return None, None, None
    currency = list(currencies)[0]
    try:
      column = (
          column.astype(str)
          .str.replace(currency_regex, '', regex=True)
          .astype(float)
      )
      return column, 'quantitative', '{}.2f'.format(currency)
    except ValueError:
      return None, None, None

  def convert_percentage(column):
    if is_not_string_column(column):
      # If columns is not a string, do nothing
      return None, None, None
    # If any non-empty values of column don't contain percentages, do nothing.
    percent_regex = r'\s*%$'
    for value in column.dropna().astype(str):
      if not re.search(percent_regex, value):
        return None, None, None
    try:
      column = (
          column.astype(str)
          .str.replace(percent_regex, '', regex=True)
          .astype(float)
          / 100
      )
      return column, 'quantitative', '%'
    except ValueError:
      return None, None, None

  def try_convert_data(field, data):
    """Run the various conversion functions in the order specified."""

    # Each conversion function should return the modified data, the new data
    # type, and the new format. If no change is made, returns None for each.
    conversion_functions = [
        convert_date,
        convert_number,
        convert_currency,
        convert_percentage,
    ]
    for func in conversion_functions:
      fixed_data, data_type, new_format = func(data[field])
      if data_type:
        return fixed_data, data_type, new_format
    return None, None, None

  # Keep track of all fields (in a specific DataFrame) that need converting, and
  # the new dataframe column, new type name and new format for each of them.
  # Ideally, we would use a dict keyed on (field name, DataFrame) to do this,
  # but DataFrames unfortunately can't be used as dict keys.
  # Instead, we do this. Each item in fields_to_convert is a (field name,
  # original DataFrame, new DataFrame column, new type, new format).
  fields_to_convert = []

  def already_found_field(field, data, fields_to_convert):
    for found_tuple in fields_to_convert:
      found_field, found_data = found_tuple[:2]
      if found_field == field and found_data is data:
        return True
    return False

  # First, collect all fields in specific DataFrames that we need to convert.
  for layer, data in layers:
    if not has_defined_attr(layer, 'encoding'):
      continue
    # To be more conservative, we are only trying to convert fields being
    # being shown as a variable in any chart layer.
    for variable_name in ['x', 'y', 'theta', 'color']:
      if not has_defined_attr(layer.encoding, variable_name):
        continue
      variable = getattr(layer.encoding, variable_name)
      if not has_defined_attr(variable, 'field'):
        continue
      field = variable.field

      if data[field].nunique() < MIN_POINTS_NEEDED_FOR_TYPE_CONVERSION:
        continue
      # Check if we already marked `field` in `data` to be converted.
      if already_found_field(field, data, fields_to_convert):
        continue

      new_column, new_type, new_format = try_convert_data(field, data)
      if new_type:
        fields_to_convert.append(
            (field, data, new_column, new_type, new_format)
        )

  # For every field in a DataFrame we need to update, update in the DataFrame
  # and then update every encoding in every layer that references the field.
  for (
      field_to_convert,
      data_to_update,
      new_column,
      new_type,
      new_format,
  ) in fields_to_convert:
    # Update DataFrame in place.
    data_to_update[field_to_convert] = new_column

    # Update all encodings in all layers where encoding.field has a new type.
    for layer, data in layers:
      if data is not data_to_update:
        continue
      encodings = get_defined_encodings_with_field(layer)
      for encoding in encodings:
        if encoding.field != field_to_convert:
          continue

        encoding.type = new_type
        if new_format:
          if hasattr(encoding, 'format'):
            encoding.format = new_format
          # Add axis to `encoding` if applicable, and make sure it has new
          # format.
          if hasattr(encoding, 'axis'):
            if encoding.axis is Undefined:
              encoding.axis = alt.Axis()
            encoding.axis.format = new_format


def set_default_bins(chart: alt.TopLevelMixin) -> None:
  """Set default maxbins for single-layer chart.

  Should not be called on heatmaps (i.e. `rect` mark type). This is mostly
  because we aggressively put labels on heatmaps, and then remove them when
  heatmaps are too big - but we cannot tell how big heatmaps will be when they
  are binned. So, this ensures that binned heatmaps don't get too big.

  Args:
    chart: Single, non-concatenated/non-layered Altair chart.
  """
  variables = []
  if has_defined_attr(chart, 'encoding'):
    if has_defined_attr(chart.encoding, 'x'):
      variables.append(chart.encoding.x)
    if has_defined_attr(chart.encoding, 'y'):
      variables.append(chart.encoding.y)
  for var in variables:
    if not has_defined_attr(var, 'bin'):
      continue

    # Explicitly check var.bin is True, since it could also equal alt.Bin().
    if var.bin == True:  # pylint: disable=singleton-comparison
      var.bin = alt.Bin(maxbins=DEFAULT_MAX_BINS)


def fix_binning(chart: alt.TopLevelMixin) -> None:
  """Removes scale from binned vars and ensure binning is reflected in tooltips.

  Args:
    chart: Single, non-concatenated/non-layered Altair chart.
  """
  variables = []
  if has_defined_attr(chart, 'encoding'):
    if has_defined_attr(chart.encoding, 'x'):
      variables.append(chart.encoding.x)
    if has_defined_attr(chart.encoding, 'y'):
      variables.append(chart.encoding.y)
  for var in variables:
    if not has_defined_attr(var, 'bin'):
      continue

    # Don't allow a scale type when the data is binned. See b/338151286.
    if has_defined_attr(var, 'scale'):
      if has_defined_attr(var.scale, 'type'):
        var.scale.type = Undefined

    # If var.bin is set, make sure tooltips with the same field match.
    if (
        var.bin
        and has_defined_attr(var, 'field')
        and has_defined_attr(chart.encoding, 'tooltip')
    ):
      tooltips = (
          chart.encoding.tooltip
          if isinstance(chart.encoding.tooltip, list)
          else [chart.encoding.tooltip]
      )
      for tooltip in tooltips:
        if has_defined_attr(tooltip, 'field') and tooltip.field == var.field:
          tooltip.bin = var.bin
          break


def maybe_remove_heatmap_labels(
    layers: list[tuple[alt.TopLevelMixin, pd.DataFrame]],
    layered_chart: alt.TopLevelMixin,
) -> None:
  """For a labeled heatmap with too many x-values, remove label layer.

  Args:
    layers: Flattened list of all layers in a chart as (chart object, DataFrame)
      tuples.
    layered_chart: Altair chart object that has all the layers in `layers`.
  """
  # Chart must have exactly one heatmap layer and one text layer.
  heatmap_layers = [
      layer for layer in layers if get_mark_type(layer[0]) == 'rect'
  ]
  text_layers = [layer for layer in layers if get_mark_type(layer[0]) == 'text']
  if len(heatmap_layers) != 1 or len(text_layers) != 1:
    return
  heatmap_layer, heatmap_data = heatmap_layers[0]
  text_layer, text_data = text_layers[0]

  # Heatmap and text layers must read from the same DataFrame.
  if heatmap_data is not text_data:
    return

  # heatmap_layer and text_layer must have matching, defined x & y variables.
  for layer in [heatmap_layer, text_layer]:
    for variable in ['x', 'y']:
      if not has_defined_attr(layer.encoding, variable):
        return
      if not has_defined_attr(getattr(layer.encoding, variable), 'field'):
        return
  heatmap_x = heatmap_layer.encoding.x.field
  heatmap_y = heatmap_layer.encoding.y.field
  text_x = text_layer.encoding.x.field
  text_y = text_layer.encoding.y.field
  if heatmap_x != text_x or heatmap_y != text_y:
    return

  # Remove text layer if there are too many x-values.
  if heatmap_data[heatmap_x].nunique() > MAX_HEATMAP_LABELED_X_VALUES:
    layers.remove(text_layers[0])
    layered_chart.layer.remove(text_layer)


def post_process_chart(chart: alt.TopLevelMixin) -> None:
  """Calls all custom Vega-Lite post-processing, altering `chart`."""
  # Disable max rows, since we may have added a lot of rows in the post
  # processing. Whenever we update to altair v5, we should use VegaFusion.
  alt.data_transformers.disable_max_rows()
  # Calling chart.to_dict() will parse variable shorthand into aggregate,
  # field, and type encodings, so we don't have to do that ourselves.
  chart.to_dict()

  # We don't want to block on any of the post-processing. So, if anything goes
  # wrong in one post processor, just move on to the next one.
  def try_or_continue(fn, *args):
    try:
      fn(*args)
    except Exception:  # pylint: disable=broad-exception-caught
      return

  def try_or_continue_for_each(fn, chart_data_pairs, pass_data=True):
    try:
      if pass_data:
        for chart, data in chart_data_pairs:
          fn(chart, data)
      else:
        for chart, _ in chart_data_pairs:
          fn(chart)
    except Exception:  # pylint: disable=broad-exception-caught
      return

  # Flatten `chart` into list of non-concatenated (but potentially layered)
  # charts.
  concats = flatten_concats(chart)
  for concat, data in concats:
    # Flatten `concat` into list of non-layered charts.
    layers = flatten_layers(concat, data)

    try_or_continue_for_each(sanitize_column_names, layers)
    try_or_continue(remove_duplicate_selectors, layers)
    try_or_continue(maybe_update_types_and_formats, layers)
    try_or_continue(maybe_remove_heatmap_labels, layers, chart)
    try_or_continue(scale_axes, layers)
    try_or_continue_for_each(remove_legend_none, layers, pass_data=False)
    try_or_continue(maybe_remove_legend_variables, layers)
    try_or_continue(remove_extra_wedges, layers)
    try_or_continue(format_labeled_pie_chart, layers)
    if not any(
        [layer for layer, _ in layers if get_mark_type(layer) == 'rect']
    ):
      try_or_continue_for_each(set_default_bins, layers, pass_data=False)
    try_or_continue_for_each(fix_binning, layers, pass_data=False)
    if len(concats) == 1:
      # For now, we don't want to do this for multiple concatenated charts.
      try_or_continue(maybe_make_bar_or_box_chart_horizontal, layers)
    try_or_continue_for_each(
        match_bar_grouping_with_orientation, layers, pass_data=False
    )
  # TODO(b/337907871): Hold off on overriding default colors until we decide
  # who should own this. Also, don't re-enable without fixing b/337898806.
  # try_or_continue_for_each(assign_default_colors, layers)