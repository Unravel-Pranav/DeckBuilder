"""
Chart formatting utilities (python-pptx + OOXML).

This module centralizes chart number formatting rules so we can apply consistent
tick label + data label formatting across all charts in a config-driven way.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence, Tuple

from lxml import etree


_NUMERIC_TYPES = (int, float, Decimal)


@dataclass(frozen=True)
class ChartNumberFormatConfig:
    """Minimal config surface for chart numeric formatting."""

    enable_numeric_formatting: bool
    enable_bar_specific_formatting: bool

    numeric_tick_label_format: str
    numeric_data_label_format: str
    bar_data_label_format: str

    bar_reverse_category_axis: bool


_CHART_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
_NS = {"c": _CHART_NS}


def _clean_format_code(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def apply_axis_format_codes_to_chart_space(
    chart_space: Any,
    *,
    primary_y_axis_format_code: str | None = None,
    secondary_y_axis_format_code: str | None = None,
    apply_to_data_labels: bool = True,
) -> None:
    """
    Apply Excel-style number formats from frontend axisConfig to the chart OOXML.

    Rules:
    - If a format code is not provided for an axis, do NOT set/override formatting for it.
    - Tick label formats are set via c:valAx/c:numFmt for left (primary) and right (secondary) axes.
    - Data label formats are set per chart-type block based on which value axis that block references.
    """
    if chart_space is None:
        return

    primary_code = _clean_format_code(primary_y_axis_format_code)
    secondary_code = _clean_format_code(secondary_y_axis_format_code)

    if not primary_code and not secondary_code:
        return

    # Map valAx ID -> valAx element and axis position (l/r)
    val_axes = chart_space.findall(".//c:valAx", namespaces=_NS)
    valax_by_id: dict[str, Any] = {}
    pos_by_valax_id: dict[str, str] = {}
    for va in val_axes:
        ax_id = va.find("./c:axId", namespaces=_NS)
        ax_id_val = ax_id.get("val") if ax_id is not None else None
        if not ax_id_val:
            continue
        ax_pos = va.find("./c:axPos", namespaces=_NS)
        pos = ax_pos.get("val") if ax_pos is not None else None
        valax_by_id[str(ax_id_val)] = va
        if pos in ("l", "r"):
            pos_by_valax_id[str(ax_id_val)] = str(pos)

    def _set_numfmt(parent: Any, format_code: str) -> None:
        num_fmt = parent.find("./c:numFmt", namespaces=_NS)
        if num_fmt is None:
            num_fmt = etree.SubElement(parent, f"{{{_CHART_NS}}}numFmt")
        num_fmt.set("formatCode", format_code)
        num_fmt.set("sourceLinked", "0")

    # Apply tick label number formats per value axis (l/r)
    for va in val_axes:
        ax_pos = va.find("./c:axPos", namespaces=_NS)
        pos = ax_pos.get("val") if ax_pos is not None else None
        if pos == "l" and primary_code:
            _set_numfmt(va, primary_code)
        elif pos == "r" and secondary_code:
            _set_numfmt(va, secondary_code)

    if not apply_to_data_labels:
        return

    plot_area = chart_space.find(".//c:plotArea", namespaces=_NS)
    if plot_area is None:
        return

    # For each chart block (barChart/lineChart/etc), determine referenced value axis,
    # then set that block's data label numFmt to the corresponding axis format code.
    for chart_block in list(plot_area):
        # Only consider chart-type nodes that reference axes.
        ax_ids = chart_block.findall("./c:axId", namespaces=_NS)
        if not ax_ids:
            continue

        referenced_valax_id: str | None = None
        for ax_id in ax_ids:
            ax_id_val = ax_id.get("val")
            if ax_id_val and str(ax_id_val) in valax_by_id:
                referenced_valax_id = str(ax_id_val)
                break

        if not referenced_valax_id:
            continue

        pos = pos_by_valax_id.get(referenced_valax_id)
        if pos == "l":
            fmt = primary_code
        elif pos == "r":
            fmt = secondary_code
        else:
            fmt = None

        if not fmt:
            continue

        d_lbls = chart_block.find("./c:dLbls", namespaces=_NS)
        if d_lbls is None:
            # Only apply if data labels are already present/enabled in the template.
            continue

        _set_numfmt(d_lbls, fmt)


def _is_number(value: Any) -> bool:
    # Exclude bool (subclass of int) from numeric detection.
    if isinstance(value, bool):
        return False
    return isinstance(value, _NUMERIC_TYPES)


def has_any_numeric_values(series_data: Sequence[Tuple[str, Sequence[Any]]]) -> bool:
    """
    Return True if any values in series_data are numeric.

    Args:
        series_data: List of tuples: (series_name, values[])
    """
    for _, values in series_data:
        for v in values:
            if _is_number(v):
                return True
    return False


def apply_value_axis_number_format_to_chart_space(
    chart_space: Any, *, format_code: str
) -> None:
    """
    Apply number formatting to *all* value axes (primary + secondary) by updating OOXML.

    This avoids python-pptx limitations where chart.value_axis only exposes the primary axis.

    Args:
        chart_space: chart._chartSpace element (lxml-backed)
        format_code: Excel-style number format, e.g. '#,##0.00'
    """
    if chart_space is None:
        return

    val_axes = chart_space.findall(".//c:valAx", namespaces=_NS)
    for va in val_axes:
        # c:numFmt is a direct child of c:valAx in standard OOXML charts.
        num_fmt = va.find("./c:numFmt", namespaces=_NS)
        if num_fmt is None:
            num_fmt = etree.SubElement(va, f"{{{_CHART_NS}}}numFmt")

        num_fmt.set("formatCode", format_code)
        # 'sourceLinked' is the OOXML equivalent of python-pptx's number_format_is_linked.
        num_fmt.set("sourceLinked", "0")


def _try_set_primary_axis_tick_labels(chart: Any, *, format_code: str) -> None:
    """
    Best-effort: also set python-pptx tick label formatting for primary axis so the
    in-memory object is consistent (OOXML update handles all axes).
    """
    try:
        tick_labels = chart.value_axis.tick_labels
        tick_labels.number_format = format_code
        tick_labels.number_format_is_linked = False
    except Exception:
        # Some chart types may not expose value_axis in python-pptx.
        return


def _format_plot_data_labels(
    chart: Any, *, format_code: str, bar_inside_end: bool = False
) -> None:
    for plot in getattr(chart, "plots", []) or []:
        try:
            if not plot.has_data_labels:
                continue
            data_labels = plot.data_labels
            data_labels.number_format = format_code
            data_labels.number_format_is_linked = False

            if bar_inside_end:
                from pptx.enum.chart import XL_LABEL_POSITION

                data_labels.position = XL_LABEL_POSITION.INSIDE_END
        except Exception:
            continue


def apply_chart_number_formatting(
    chart: Any,
    *,
    series_data: Sequence[Tuple[str, Sequence[Any]]],
    config: ChartNumberFormatConfig,
) -> None:
    """
    Apply config-driven numeric formatting to a python-pptx Chart instance.

    This implements the requested algorithm:
    - If numeric_values: axis tick labels '#,##0.00' + data labels '#,##0.00'
    - If bar chart: reverse category axis, data labels '#,##0', INSIDE_END
    """
    if not config.enable_numeric_formatting:
        return

    numeric_values = has_any_numeric_values(series_data)
    if numeric_values:
        apply_value_axis_number_format_to_chart_space(
            getattr(chart, "_chartSpace", None), format_code=config.numeric_tick_label_format
        )
        _try_set_primary_axis_tick_labels(chart, format_code=config.numeric_tick_label_format)
        _format_plot_data_labels(chart, format_code=config.numeric_data_label_format)

    if not config.enable_bar_specific_formatting:
        return

    try:
        from pptx.enum.chart import XL_CHART_TYPE

        is_bar = chart.chart_type in (
            XL_CHART_TYPE.BAR_CLUSTERED,
            XL_CHART_TYPE.BAR_STACKED,
            XL_CHART_TYPE.BAR_STACKED_100,
        )
    except Exception:
        is_bar = False

    if not is_bar:
        return

    if config.bar_reverse_category_axis:
        try:
            chart.category_axis.reverse_order = True
        except Exception:
            pass

    _format_plot_data_labels(
        chart, format_code=config.bar_data_label_format, bar_inside_end=True
    )


