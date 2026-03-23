"""
PPT template configuration helpers.

Keeps track of which PPT template set should be used for each property_sub_type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, Set, Tuple, List


@dataclass(frozen=True)
class SlideConstraints:
    """Physical constraints for slide layout."""

    slide_width: float = 13.33  # inches
    slide_height: float = 7.5  # inches
    margin_top: float = 0.6  # Below header
    margin_bottom: float = 0.5  # Above footer
    margin_left: float = 0.8  # Minimal side margins
    margin_right: float = 0.4  # Reduced for wider content
    gutter_horizontal: float = 0.4  # Horizontal spacing
    gutter_vertical: float = 0.65  # Vertical spacing (increased to prevent overlaps)
    min_font_size: float = 10.0  # points
    default_font_size: float = 14.0
    second_slide_chart_width: float = 5.97  # inches (15.17 cm)
    second_slide_chart_height: float = 2.67  # inches (6.77 cm)

    @property
    def content_width(self) -> float:
        """Available width for content."""
        return self.slide_width - self.margin_left - self.margin_right

    @property
    def content_height(self) -> float:
        """Available height for content."""
        return self.slide_height - self.margin_top - self.margin_bottom


@dataclass(frozen=True)
class SlideLayoutConfig:
    """Unified slide layout configuration for both first and regular slides."""

    # Base constraints (used for regular slides, can be overridden for first slide)
    base_constraints: SlideConstraints

    # First slide specific overrides
    first_slide_style: str  # kpi_row, full_width, grid
    first_slide_start_top: float
    first_slide_margin_left: Optional[float] = None  # None = use base
    first_slide_margin_right: Optional[float] = None
    first_slide_margin_bottom: Optional[float] = None
    first_slide_gutter_horizontal: Optional[float] = None
    first_slide_gutter_vertical: Optional[float] = None
    first_slide_max_elements: Optional[int] = None
    first_slide_rows: Optional[int] = None
    first_slide_cols: Optional[int] = None
    first_slide_kpi_section_height: Optional[float] = None

    # Slide capacity configuration
    first_slide_capacity: Optional[int] = None  # None means dynamic calculation
    regular_slide_capacity: Optional[int] = None  # None means dynamic calculation
    uses_dynamic_capacity: bool = False

    # Hybrid grid layout configuration
    hybrid_grid_cols: int = 2  # Number of columns in hybrid grid layout
    hybrid_gutter_vertical: Optional[float] = (
        None  # Vertical gutter for hybrid layouts (None = use base gutter * 0.33)
    )
    hybrid_section_spacing: float = (
        0.15  # Spacing between grid and full-width sections in hybrid layout
    )
    hybrid_grid_height_ratio: float = 0.50  # Ratio of available height for grid when space is constrained (50/50 split)

    # Full-width table layout configuration
    full_width_table_gutter_vertical: Optional[float] = (
        None  # Reduced vertical gutter between consecutive tables in full-width layout (None = use 0.05")
    )

    # Section title configuration
    show_section_titles: bool = True  # Whether to show section titles on slides

    def get_constraints(self, is_first_slide: bool = False) -> SlideConstraints:
        """Get constraints for first or regular slide."""
        if not is_first_slide:
            return self.base_constraints

        # Build first slide constraints with overrides
        return SlideConstraints(
            slide_width=self.base_constraints.slide_width,
            slide_height=self.base_constraints.slide_height,
            margin_top=self.first_slide_start_top,
            margin_bottom=self.first_slide_margin_bottom
            or self.base_constraints.margin_bottom,
            margin_left=self.first_slide_margin_left
            or self.base_constraints.margin_left,
            margin_right=self.first_slide_margin_right
            or self.base_constraints.margin_right,
            gutter_horizontal=self.first_slide_gutter_horizontal
            or self.base_constraints.gutter_horizontal,
            gutter_vertical=self.first_slide_gutter_vertical
            or self.base_constraints.gutter_vertical,
            min_font_size=self.base_constraints.min_font_size,
            default_font_size=self.base_constraints.default_font_size,
            second_slide_chart_width=self.base_constraints.second_slide_chart_width,
            second_slide_chart_height=self.base_constraints.second_slide_chart_height,
        )

    def get_full_width_gutter(self, is_first_slide: bool = False) -> float:
        """Get full-width gutter for first or regular slide.

        Uses the vertical gutter from constraints (first slide override if available, otherwise base).
        """
        constraints = self.get_constraints(is_first_slide=is_first_slide)
        return constraints.gutter_vertical

    def get_capacity(self, is_first_slide: bool = False) -> Optional[int]:
        """Get capacity for first or regular slide."""
        return (
            self.first_slide_capacity if is_first_slide else self.regular_slide_capacity
        )

    def get_hybrid_gutter_vertical(self, is_first_slide: bool = False) -> float:
        """Get vertical gutter for hybrid grid layouts.

        If not explicitly configured, uses 1/3 of the base vertical gutter to minimize wasted space.
        """
        if self.hybrid_gutter_vertical is not None:
            return self.hybrid_gutter_vertical

        # Default to 1/3 of base gutter vertical for compact hybrid layouts
        constraints = self.get_constraints(is_first_slide=is_first_slide)
        return constraints.gutter_vertical / 3.0

    def get_full_width_table_gutter(self) -> float:
        """Get vertical gutter between consecutive tables in full-width layout.

        Returns a reduced gutter (0.05" default) for tighter spacing between stacked tables.
        This applies regardless of first/regular slide since table density is the priority.
        """
        if self.full_width_table_gutter_vertical is not None:
            return self.full_width_table_gutter_vertical

        # Default to 0.05" for compact table layouts
        return 0.05


# ============================================================================
# CHART-SPECIFIC LAYOUT CONFIGURATION
# ============================================================================
# Chart layout configurations grouped by chart behavior type.
# This allows fine-grained control over spacing, legend, plot area, and formatting
# for each chart group while maintaining consistency within groups.


@dataclass(frozen=True)
class ChartLayoutConfig:
    """
    Chart-specific layout configuration for a group of similar chart types.

    All values are factors (0.0 to 1.0) relative to the chart container unless
    otherwise noted. This enables consistent spacing control per chart group.
    """

    # -------------------------------------------------------------------------
    # Legend Configuration
    # -------------------------------------------------------------------------
    show_legend: bool = True
    legend_position: str = "bottom"  # bottom, right, top, none
    legend_height_max: float = 0.35  # Maximum legend height as chart factor (35%)
    legend_width: float = 0.98  # Legend width as chart factor (98%)
    legend_x: float = 0.01  # Legend X position (1% left margin)
    legend_bottom_margin: float = 0.01  # Space between legend bottom and chart edge
    legend_font_size_pt: int = 9  # Legend font size in points
    legend_char_width_factor: float = 0.0040  # Character width factor for sizing
    legend_marker_width: float = 0.18  # Legend marker (colored box) width in inches
    legend_entry_spacing: float = 0.08  # Spacing between legend entries in inches
    legend_row_height_factor: float = 0.075  # Height per legend row as chart factor
    legend_padding: float = 0.03  # Top/bottom padding for legend

    # -------------------------------------------------------------------------
    # Plot Area Configuration
    # -------------------------------------------------------------------------
    plot_area_x: float = 0.02  # Plot area X position (2% margin)
    plot_area_y: Optional[float] = None  # None = use plot_area_top_margin
    plot_area_width: float = 0.96  # Plot area width (96%)
    plot_area_height: Optional[float] = None  # None = dynamic based on legend
    plot_area_top_margin: float = 0.05  # 5% top margin - tighter spacing
    plot_area_min_height: float = 0.35  # Minimum plot area height (35%)

    # -------------------------------------------------------------------------
    # Axis Configuration
    # -------------------------------------------------------------------------
    show_axis_titles: bool = True
    primary_y_axis_title_x: float = 0.0  # Primary (left) Y-axis title X position
    secondary_y_axis_title_x: float = 0.98  # Secondary (right) Y-axis title X position
    y_axis_title_y: float = 0.0  # Y-axis titles vertical position (0.0 = top)
    axis_title_plot_gap: float = 0.1  # Gap between axis title and plot area (2%)
    y_axis_title_font_size: int = 900  # Font size in hundredths of points (9pt)

    # -------------------------------------------------------------------------
    # X-Axis Label Space
    # -------------------------------------------------------------------------
    x_axis_label_space: float = 0.20  # Space reserved for X-axis labels (20%)
    x_axis_label_space_multi_row: float = 0.25  # Space when legend has multiple rows

    # -------------------------------------------------------------------------
    # Number Formatting
    # -------------------------------------------------------------------------
    tick_label_format: str = "#,##0.00"
    data_label_format: str = "#,##0.00"
    reverse_category_axis: bool = False

    # -------------------------------------------------------------------------
    # Chart Width for Legend Calculation
    # -------------------------------------------------------------------------
    default_chart_width_inches: float = 5.5  # Approximate chart width for calculations

    def get_plot_area_y(self) -> float:
        """Get plot area Y position."""
        return self.plot_area_y if self.plot_area_y is not None else self.plot_area_top_margin

    def get_effective_plot_area_y(self) -> float:
        """
        Get effective plot area Y position based on axis title position and gap.
        
        If show_axis_titles is True, plot area starts after:
        - Y-axis title position (y_axis_title_y)
        - Estimated title height (~3-4%)
        - Gap between title and plot (axis_title_plot_gap)
        
        If show_axis_titles is False, uses plot_area_top_margin directly.
        """
        if not self.show_axis_titles:
            return self.get_plot_area_y()
        
        # Estimate title height as ~4% of chart height
        estimated_title_height = 0.04
        return self.y_axis_title_y + estimated_title_height + self.axis_title_plot_gap

    def get_plot_area_height(self, legend_height: float = 0.10) -> float:
        """Compute plot area height dynamically based on legend height."""
        if self.plot_area_height is not None:
            return self.plot_area_height
        return 1.0 - self.plot_area_top_margin - legend_height

    def calculate_legend_entry_width(self, name_length: int) -> float:
        """
        Calculate width needed for a single legend entry.

        Args:
            name_length: Number of characters in series name

        Returns:
            Width in inches
        """
        char_width = self.legend_font_size_pt * self.legend_char_width_factor
        text_width = name_length * char_width
        return self.legend_marker_width + text_width + self.legend_entry_spacing

    def calculate_legend_dimensions(
        self, series_names: List[str], chart_width_inches: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate legend height and position based on series names.

        Args:
            series_names: List of series name strings
            chart_width_inches: Chart width in inches (uses default if not provided)

        Returns:
            dict with 'height', 'y', 'num_rows', 'entries_per_row'
        """
        if not series_names:
            return {"height": 0.08, "y": 0.92, "num_rows": 1, "entries_per_row": [0]}

        chart_width = chart_width_inches or self.default_chart_width_inches
        available_width = chart_width * self.legend_width

        # Calculate width for each entry
        entry_widths = [
            self.calculate_legend_entry_width(len(name)) for name in series_names
        ]

        # Determine how many entries fit per row
        current_row_width: float = 0.0
        num_rows = 1
        entries_per_row: List[int] = []
        current_row_entries = 0

        for width in entry_widths:
            if current_row_width + width > available_width and current_row_entries > 0:
                entries_per_row.append(current_row_entries)
                num_rows += 1
                current_row_width = width
                current_row_entries = 1
            else:
                current_row_width += width
                current_row_entries += 1

        if current_row_entries > 0:
            entries_per_row.append(current_row_entries)

        # Calculate height
        legend_height = min(
            self.legend_height_max,
            num_rows * self.legend_row_height_factor + self.legend_padding,
        )

        # Calculate Y position (at bottom with margin)
        legend_y = 1.0 - legend_height - self.legend_bottom_margin

        return {
            "height": legend_height,
            "y": legend_y,
            "num_rows": num_rows,
            "entries_per_row": entries_per_row,
        }

    def calculate_plot_area_dimensions(self, legend_y: float) -> Dict[str, Any]:
        """
        Calculate plot area dimensions based on legend position.

        Args:
            legend_y: Legend Y position (factor 0.0-1.0)
                     Use 1.0 for charts with no legend (single series)

        Returns:
            dict with 'x', 'y', 'width', 'height', 'x_axis_space'
        """
        # Fixed plot area case
        if self.plot_area_height is not None:
            return {
                "x": self.plot_area_x,
                "y": self.get_plot_area_y(),
                "width": self.plot_area_width,
                "height": self.plot_area_height,
                "x_axis_space": self.x_axis_label_space,
            }

        # No legend case: legend_y = 1.0 means no legend space needed
        if legend_y >= 0.99:
            x_axis_space = self.x_axis_label_space - 0.01  # Slightly less without legend
            plot_height = 1.0 - self.plot_area_top_margin - x_axis_space
            return {
                "x": self.plot_area_x,
                "y": self.plot_area_top_margin,
                "width": self.plot_area_width,
                "height": plot_height,
                "x_axis_space": x_axis_space,
            }

        # Choose X-axis label space based on legend position
        legend_single_row_y_threshold = 0.85
        if legend_y >= legend_single_row_y_threshold:
            x_axis_space = self.x_axis_label_space
        else:
            x_axis_space = self.x_axis_label_space_multi_row

        # Calculate plot height
        max_plot_bottom = legend_y - x_axis_space
        plot_height = max(
            self.plot_area_min_height, max_plot_bottom - self.plot_area_top_margin
        )

        return {
            "x": self.plot_area_x,
            "y": self.plot_area_top_margin,
            "width": self.plot_area_width,
            "height": plot_height,
            "x_axis_space": x_axis_space,
        }


# ============================================================================
# CHART GROUP CONFIGURATIONS
# ============================================================================
# Each group contains charts with similar layout behavior.
# Override only the parameters that differ from defaults.

_CHART_GROUP_CONFIGS: Dict[str, ChartLayoutConfig] = {
    # -------------------------------------------------------------------------
    # VERTICAL_BAR: bar, stacked_bar, column charts
    # X-axis at bottom with category labels, Y-axis on left, legend at bottom
    # -------------------------------------------------------------------------
    "VERTICAL_BAR": ChartLayoutConfig(
        show_legend=True,
        legend_position="bottom",
        legend_height_max=0.12,  # Smaller legend for bar charts
        plot_area_top_margin=0.05,  # Smaller margin - bar charts don't need much
        plot_area_min_height=0.50,  # Bars need more vertical space
        x_axis_label_space=0.15,  # Less space needed for category labels
        x_axis_label_space_multi_row=0.20,
        show_axis_titles=True,
        primary_y_axis_title_x=0.0,
        secondary_y_axis_title_x=0.98,
        y_axis_title_y=0.0,  # Y-axis title at top
        axis_title_plot_gap=0.01,  # 1% gap - tighter for bar charts
        reverse_category_axis=False,
        tick_label_format="#,##0",  # Whole numbers for bar charts
        data_label_format="#,##0",
    ),
    # -------------------------------------------------------------------------
    # HORIZONTAL_BAR: horizontal_bar, stacked_horizontal_bar
    # No legend, full plot area, category axis on left (Y position)
    # -------------------------------------------------------------------------
    "HORIZONTAL_BAR": ChartLayoutConfig(
        show_legend=False,
        legend_position="none",
        plot_area_x=0.0,  # Full width
        plot_area_y=0.0,  # Start at top
        plot_area_width=1.0,  # Full width
        plot_area_height=1.0,  # Full height - no legend space needed
        plot_area_top_margin=0.0,
        plot_area_min_height=1.0,
        show_axis_titles=False,  # No axis titles for horizontal bars
        x_axis_label_space=0.0,  # No X-axis label space (category on Y)
        reverse_category_axis=True,  # Reverse for natural reading order
        tick_label_format="#,##0",
        data_label_format="#,##0",
    ),
    # -------------------------------------------------------------------------
    # LINE: line, multi_line, single_line charts
    # Similar to bar but optimized for line data with trend visibility
    # -------------------------------------------------------------------------
    "LINE": ChartLayoutConfig(
        show_legend=True,
        legend_position="bottom",
        legend_height_max=0.35,  # More space for multiple series legends
        legend_x=0.10,  # 10% left margin to avoid Y-axis tick label overlap
        legend_width=0.88,  # Reduced width to account for larger left margin
        plot_area_top_margin=0.10,  # 10% top margin for axis titles
        plot_area_min_height=0.35,
        x_axis_label_space=0.20,  # Space for date/time labels
        x_axis_label_space_multi_row=0.25,
        show_axis_titles=True,
        primary_y_axis_title_x=0.0,
        secondary_y_axis_title_x=0.98,
        y_axis_title_y=0.0,  # Y-axis title at top
        axis_title_plot_gap=0.02,  # 2% gap between title and plot
        tick_label_format="#,##0.00",
        data_label_format="#,##0.00",
    ),
    # -------------------------------------------------------------------------
    # PIE_DONUT: pie, donut charts
    # No axes, centered plot, legend on right or bottom
    # -------------------------------------------------------------------------
    "PIE_DONUT": ChartLayoutConfig(
        show_legend=True,
        legend_position="right",  # Legend on right for pie/donut
        legend_height_max=0.90,  # Can use most of height on right
        legend_width=0.30,  # Narrower legend on right side
        legend_x=0.70,  # Position legend on right
        plot_area_x=0.05,  # Centered plot area
        plot_area_y=0.05,
        plot_area_width=0.60,  # Leave room for legend on right
        plot_area_height=0.90,  # Use most of vertical space
        plot_area_top_margin=0.05,
        plot_area_min_height=0.80,
        show_axis_titles=False,  # No axes for pie/donut
        x_axis_label_space=0.0,  # No X-axis
        tick_label_format="0%",  # Percentage format for pie
        data_label_format="0%",
    ),
    # -------------------------------------------------------------------------
    # COMBO: combo charts (bar+line, area+bar, etc.)
    # Dual-axis support, complex legend handling
    # -------------------------------------------------------------------------
    "COMBO": ChartLayoutConfig(
        show_legend=True,
        legend_position="bottom",
        legend_height_max=0.35,  # More space for multiple series
        plot_area_top_margin=0.10,  # 10% top margin for dual Y-axis titles
        plot_area_min_height=0.35,
        x_axis_label_space=0.20,
        x_axis_label_space_multi_row=0.25,
        show_axis_titles=True,  # Need both Y-axis titles
        primary_y_axis_title_x=0.0,
        secondary_y_axis_title_x=0.98,
        y_axis_title_y=0.0,  # Y-axis titles at top
        axis_title_plot_gap=0.02,  # 2% gap between title and plot
        tick_label_format="#,##0.00",
        data_label_format="#,##0.00",
    ),
    # -------------------------------------------------------------------------
    # SINGLE_COLUMN_STACKED: Single column stacked chart (centered)
    # A single vertical stacked column showing component breakdown
    # Centered on the slide with no legend (data labels show series names)
    # -------------------------------------------------------------------------
    "SINGLE_COLUMN_STACKED": ChartLayoutConfig(
        show_legend=False,  # No legend - data labels show series names
        legend_position="none",  # Legend disabled
        legend_height_max=0.0,  # No legend space needed
        plot_area_x=0.25,  # Centered: 25% margin on left
        plot_area_width=0.50,  # Narrower plot area for single column (50% width)
        plot_area_top_margin=0.05,  # Small top margin
        plot_area_min_height=0.60,  # More vertical space without legend
        plot_area_height=0.90,  # Fixed plot height - full area without legend
        x_axis_label_space=0.05,  # Minimal X-axis space (single category)
        x_axis_label_space_multi_row=0.10,
        show_axis_titles=False,  # No axis titles - data labels show series names
        primary_y_axis_title_x=0.20,
        secondary_y_axis_title_x=0.80,
        y_axis_title_y=0.0,
        axis_title_plot_gap=0.01,
        reverse_category_axis=False,
        tick_label_format="#,##0",  # Whole numbers for values
        data_label_format="#,##0",
    ),
}

# ============================================================================
# CHART TYPE TO GROUP MAPPING
# ============================================================================
# Maps specific chart type strings to their behavior group.
# This enables looking up the right config by chart type name.

_CHART_TYPE_TO_GROUP: Dict[str, str] = {
    # VERTICAL_BAR group
    "bar": "VERTICAL_BAR",
    "stacked_bar": "VERTICAL_BAR",
    "column": "VERTICAL_BAR",
    "clustered_column": "VERTICAL_BAR",
    "stacked_column": "VERTICAL_BAR",
    # HORIZONTAL_BAR group
    "horizontal_bar": "HORIZONTAL_BAR",
    "stacked_horizontal_bar": "HORIZONTAL_BAR",
    # LINE group
    "line": "LINE",
    "multi_line": "LINE",
    "single_line": "LINE",
    # PIE_DONUT group
    "pie": "PIE_DONUT",
    "donut": "PIE_DONUT",
    # COMBO group
    "combo": "COMBO",
    "combo_bar_line": "COMBO",
    "combo_double_bar_line": "COMBO",
    "combo_stacked_bar_line": "COMBO",
    "combo_area_bar": "COMBO",
    "combo_singlebar_line": "COMBO",
    "combo_doublebar_line": "COMBO",
    "combo_stackedbar_line": "COMBO",
    # SINGLE_COLUMN_STACKED group
    "single_column_stacked": "SINGLE_COLUMN_STACKED",
    "single_column_stacked_chart": "SINGLE_COLUMN_STACKED",
    "Single_column_stacked_chart": "SINGLE_COLUMN_STACKED",
}

# Default group for unknown chart types
_DEFAULT_CHART_GROUP = "VERTICAL_BAR"


@dataclass(frozen=True)
class ElementDimensions:
    """
    Dimension constants for content elements (tables, charts, commentary).

    All values are configurable and can be exposed via API for admin configuration.
    This class defines the physical dimensions and styling for all PPT elements.
    """

    # ============================================================================
    # LABEL BEHAVIOR (Sizing vs Rendering)
    # ============================================================================

    # When True, layout sizing should *always* reserve space for figure labels on
    # charts/tables even if the incoming JSON doesn't include an explicit label.
    #
    # Rationale: the renderer adds "Figure X" labels for charts/tables regardless of
    # `label`, so orchestration must reserve this vertical space to avoid over-packing
    # and unintended table continuations/interleaving.
    reserve_figure_label_space_for_charts_and_tables: bool = True

    # ============================================================================
    # TABLE CONFIGURATION
    # ============================================================================

    # Table Row Configuration
    # CALIBRATED 2026-01-28: Actual PowerPoint min row height measured at ~0.26"
    # Based on: 40 rows in 10.35" table = 0.259" per row average
    table_min_row_height: float = (
        0.265  # Base row height in inches (calibrated from actual measurements)
    )
    table_height_safety_margin: float = (
        1.1  # Multiplier for row height (1.1 = 10% extra space)
    )
    # Effective row height = table_min_row_height × table_height_safety_margin

    # Table Border Configuration
    # PowerPoint tables have borders, cell padding, and internal spacing that add to the visual height
    # This value accounts for: top border + bottom border + cell internal padding + visual rendering overhead
    # Empirically measured: PowerPoint renders tables ~0.05" taller than the shape boundary due to
    # border thickness, cell padding, and content rendering
    table_border_total_height: float = 0.45  # Total height of table borders and rendering overhead in inches (used for row fitting with safety margin)

    # Border overhead for content height calculation (actual visual border height)
    # This is the fixed overhead added to table height for top + bottom borders
    # Calibrated 2025-12-22: For Snapshot tables (PowerPoint desktop), the reported table
    # shape height is fully explained by row heights (including header + source) with
    # no additional border overhead in "Size and Position".
    table_border_overhead: float = 0.00

    # Cell padding between rows (vertical spacing between table rows)
    # Calibrated 2024-12-22: PowerPoint does NOT add spacing between rows
    # Row heights already include all internal padding and borders
    table_row_gap_padding: float = 0.00  # Calibrated from actual PowerPoint measurement

    # Default max columns for height calculation when template column count is unknown
    # This ensures consistent height calculation between assignment and rendering phases
    # Should match typical table templates (most have 12 columns)
    table_default_max_columns: int = 12

    # Source row height (for tables with source label as an internal row)
    # The source row is rendered INSIDE the table as the last row
    # Calibrated 2025-12-22: PowerPoint reports the source row as the same as the
    # minimum table row height for non-wrapping content.
    table_source_row_height: float = 0.22  # Total height for source row inside table
    table_source_row_content_height: float = (
        0.22  # Height for source row (used for EMUs conversion when writing OOXML)
    )

    # Table Column Configuration
    table_min_col_width: float = 0.75  # Minimum column width in inches
    table_cell_padding: float = 0.01  # Padding between cells in inches

    # First Column Width Configuration (variable column width feature)
    # First column expands to fit content without wrapping; other columns share remaining space
    table_first_col_max_width_ratio: float = (
        0.40  # Maximum width ratio for first column (40% of table width)
    )
    table_first_col_min_width_ratio: float = (
        0.10  # Minimum width ratio for first column (10% of table width)
    )
    table_other_col_min_width: float = (
        0.50  # Minimum width for other columns in inches (ensures readability)
    )

    # Table Cell Margins (internal spacing within cells)
    table_cell_margin_top: float = 1.0  # Top margin in points
    table_cell_margin_bottom: float = 1.0  # Bottom margin in points
    table_cell_margin_left: float = 2.0  # Left margin in points
    table_cell_margin_right: float = 2.0  # Right margin in points

    # Table Text Configuration
    table_font_size: float = 9.0  # Font size in points
    table_font_name: str = "Calibre (Body)"  # Font family for table content
    table_line_spacing_multiplier: float = (
        1.2  # Line spacing multiplier (PowerPoint uses ~1.15-1.2 for Calibri)
    )

    # Character width ratios for text measurement
    # These ratios are multiplied by (font_size / 72) to get character width in inches
    # Higher ratio = wider character estimate = more conservative
    # Lower ratio for height = more chars fit per line = fewer lines = shorter rows = more rows fit
    table_char_width_ratio_for_column_width: float = (
        0.45  # For column WIDTH calculation (text columns - tighter fit)
    )
    # CALIBRATED 2026-01-28: Increased from 0.35 to 0.50 to match PowerPoint's actual
    # character rendering. At 0.35, we were calculating CPL=14 for 0.65" columns, but
    # PPT actually wraps at ~CPL=10 (effective ratio ~0.50). This caused underestimation
    # of table heights, especially for narrow text columns like SUBMARKET.
    table_char_width_ratio_for_row_height: float = 0.50  # For row HEIGHT calculation
    table_first_col_width_safety_factor: float = 1.20  # 20% safety margin to prevent wrapping

    # Narrow-column wrapping calibration (used for row-height estimation)
    # These values are used to compute chars-per-line from column width.
    # Smaller threshold => fewer columns treated as "narrow".
    table_narrow_column_threshold_inches: float = 0.55
    # Default narrow-column ratio for DATA rows
    table_narrow_column_char_width_ratio_for_row_height: float = 0.37
    # Separate ratio for HEADER row in narrow columns (headers wrap more aggressively in PowerPoint)
    # CALIBRATED 2026-01-28: Increased from 0.30 to 0.50 - headers with long column names
    # wrap significantly more than data. Actual header=0.79", need higher ratio for more wrapping.
    table_header_narrow_column_char_width_ratio_for_row_height: float = 0.50

    # Text-heavy column wrapping calibration (used for row-height estimation)
    # Some templates (e.g., "Property Name" / "Address") behave like PowerPoint is effectively
    # allowing fewer characters per line than our numeric-focused default. This is most noticeable
    # when multi-word phrases wrap at word boundaries (e.g., each word on its own line).
    #
    # Apply a more conservative char-width ratio only when:
    # - the column appears "text-heavy" based on sampled values, AND
    # - the column width is below this threshold (inches)
    # CALIBRATED 2026-01: Increased from 1.05 to 1.15 to include columns like
    # PROPERTY_NAME (1.057") that contain long text requiring proper wrapping estimation.
    table_text_column_max_width_inches: float = 1.15
    # Use different ratios for alpha-heavy vs mixed (address-like) columns.
    # - Alpha-heavy (names): less conservative (more chars per line) - proportional fonts are narrower
    # - Mixed (addresses with digits + words): slightly more conservative (fewer chars per line)
    # CALIBRATED 2026-01: Reduced from 0.45 to 0.40 - "Sysco International Food Group" was
    # calculating 3 lines when PPT renders it in 2 lines at 0.986" column width
    table_text_alpha_column_char_width_ratio_for_row_height: float = 0.40
    # CALIBRATED 2026-01: Reduced from 0.55 to 0.50 - the 0.55 ratio was too aggressive,
    # causing addresses like "1420 Gordon Food Service Dr" to wrap to 3 lines when PPT
    # actually renders them as 2 lines.
    table_text_mixed_column_char_width_ratio_for_row_height: float = 0.50
    # Heuristic thresholds for classifying a column as text-heavy
    table_text_column_min_alpha_ratio: float = 0.20
    table_text_column_min_space_ratio: float = 0.05
    table_text_column_min_digit_ratio_for_mixed: float = 0.15

    # Wrapping / line-count bounds
    table_max_wrapped_lines: int = 5

    # Numeric column no-wrap configuration
    # Numeric columns with values <= max_chars will not wrap (prioritized over first column)
    table_numeric_column_no_wrap_enabled: bool = True  # Enable no-wrap for numeric columns
    table_numeric_column_max_chars_no_wrap: int = 16   # Max chars before wrapping (16 = ~999 billion)

    # Header styling adds extra height beyond the wrapped lines (bold/style)
    table_header_extra_padding_inches: float = 0.0

    table_word_wrap: bool = True  # Enable text wrapping in table cells
    table_auto_size_disabled: bool = (
        True  # Disable auto-resize to maintain fixed dimensions
    )

    # Table overflow prevention and row management
    table_max_rows_enforcement: bool = (
        True  # Enable strict row count enforcement based on available height
    )
    table_overflow_strategy: str = (
        "drop"  # Strategy for handling overflow: "drop" excess rows or "truncate" data
    )
    table_height_calculation_padding: float = (
        1.15  # Safety padding multiplier for height calculations (15% extra)
    )
    table_reserve_source_space: bool = (
        True  # Always reserve space for source label even if empty
    )
    table_min_rows_before_overflow: int = (
        2  # Minimum rows (header + data) a table needs to fit before moving to next slide
    )

    # Layout-specific behavior flags
    fixed_layout_strict_dimensions: bool = (
        True  # Enforce strict dimensions in fixed layouts (grid_2x2, hybrid_grid)
    )
    dynamic_layout_accurate_sizing: bool = (
        True  # Use accurate height calculations in dynamic layouts (full_width)
    )

    # Full-width layout overflow behavior
    # When True: Elements in full_width layouts use their true intrinsic height and overflow to next slide if needed
    # When False: Elements are capped to available slide height (legacy behavior)
    allow_full_width_overflow: bool = (
        True  # Allow full_width elements to overflow to next slide
    )

    # Dynamic layout constraints (for layouts without fixed rows×cols like full_width)
    # These apply to charts and commentary elements
    dynamic_layout_min_height_ratio: float = 0.20  # Min height as 20% of element width
    dynamic_layout_max_height_ratio: float = 0.50  # Max height as 50% of element width

    # Table layout constraints
    # Tables in dynamic layouts can use full slide height
    # Tables in fixed layouts use cell dimensions
    table_min_width_ratio: float = (
        0.6  # Table min width as ratio of content_width (for validation)
    )

    # Commentary estimation constants
    commentary_line_height: float = 0.2  # inches per line
    commentary_chars_per_line: int = 80  # characters per line

    # Fit tolerance constraints
    vertical_fit_tolerance: float = 1.05  # 5% tolerance for vertical fit checks
    quadrant_fit_tolerance: float = 1.1  # 10% tolerance for quadrant fit checks
    minimum_dimension_tolerance: float = (
        0.95  # 5% tolerance for minimum dimension validation
    )

    # ============================================================================
    # LABEL CONFIGURATION (Figure labels, Table headings, Source labels)
    # ============================================================================

    # Label Dimensions
    figure_label_height: float = (
        0.18  # Height for figure labels and table headings in inches
    )
    figure_gap: float = (
        -0.03  # No gap between figure label and chart (tighter layout for charts)
    )
    table_figure_gap: float = (
        0.08  # Gap between figure label and table (larger to prevent overlapping)
    )
    section_title_gap: float = 0.10  # Vertical gap after section title to content in inches (larger for visual separation)
    source_label_height: float = 0.20  # Height for source labels in inches
    source_gap: float = 0.02  # Vertical gap before source label in inches (accounts for PPT rendering overflow)
    source_positioning_safety_margin: float = 0.05  # Safety margin when positioning source labels to account for PowerPoint rendering variations

    # Label Text Styling
    figure_label_font_size: float = 9.0  # Font size for figure labels in points
    figure_label_font_name: str = "Calibre (Body)"  # Font family for figure labels
    table_heading_font_size: float = 9.0  # Font size for table headings in points
    table_heading_font_name: str = "Calibre (Body)"  # Font family for table headings
    source_label_font_size: float = 8.0  # Font size for source labels in points
    source_label_font_name: str = "Calibre"  # Font family for source labels
    source_text_vertical_alignment: str = "ctr"  # Vertical alignment for source text in table cells: "t" (top), "ctr" (center), "b" (bottom)

    # ============================================================================
    # SPACING HELPER METHODS - Single Source of Truth
    # ============================================================================

    def get_section_title_total_height(self) -> float:
        """
        Total height for section title including gap to figure label.

        This is the SINGLE SOURCE OF TRUTH for section title spacing.
        Use this method instead of manually calculating figure_label_height + section_title_gap.
        """
        return self.figure_label_height + self.section_title_gap

    def get_figure_label_total_height(self) -> float:
        """
        Total height for figure label including gap to content (chart).

        This is the SINGLE SOURCE OF TRUTH for figure label spacing for CHARTS.
        Use this method instead of manually calculating figure_label_height + figure_gap.
        """
        return self.figure_label_height + self.figure_gap

    def get_table_label_total_height(self) -> float:
        """
        Total height for figure label including gap to content (table).

        This is the SINGLE SOURCE OF TRUTH for figure label spacing for TABLES.
        Tables need a larger gap than charts to prevent overlapping.
        Use this method instead of manually calculating figure_label_height + table_figure_gap.
        """
        return self.figure_label_height + self.table_figure_gap

    # ============================================================================
    # CHART LAYOUT CONFIGURATION (Config-Driven, DRY Principles)
    # ============================================================================
    # All chart layout values are centralized here for easy tuning.
    # Values are factors (0.0 to 1.0) relative to the chart container.

    # --- Legend Configuration ---
    legend_font_size_pt: int = 9  # Legend font size in points
    legend_char_width_factor: float = (
        0.0040  # Character width = font_size * this factor (inches) - tight estimate
    )
    legend_marker_width: float = 0.18  # Legend marker (colored box) width in inches
    legend_entry_spacing: float = 0.08  # Spacing between legend entries in inches
    legend_row_height_factor: float = (
        0.075  # Height per legend row as chart factor (7.5%)
    )
    legend_padding: float = 0.03  # Top/bottom padding for legend
    legend_height_max: float = 0.35  # Maximum legend height as chart factor (35%)
    legend_width: float = 0.98  # Legend width as chart factor (98%)
    legend_x: float = 0.01  # Legend X position (1% left margin)
    legend_bottom_margin: float = 0.01  # Space between legend bottom and chart edge

    # --- Legend Position Thresholds ---
    # When legend Y position is >= this value, use single-row spacing
    legend_single_row_y_threshold: float = 0.85

    # --- X-Axis Label Space ---
    # Space reserved for rotated X-axis labels between plot area and legend
    x_axis_label_space_single_row: float = 0.20  # 20% for single-row legends
    x_axis_label_space_multi_row: float = 0.25  # 25% for multi-row legends

    # --- Plot Area Configuration ---
    plot_area_top_margin: float = 0.05  # 5% top margin - tighter spacing
    plot_area_min_height: float = 0.35  # Minimum plot area height (35%)
    plot_area_x: float = 0.02  # Plot area X position (2% margin)
    plot_area_width: float = 0.96  # Plot area width (96%)

    # --- Y-Axis Title Configuration ---
    y_axis_title_font_size: int = 900  # Font size in hundredths of points (9pt)
    primary_y_axis_title_x: float = 0.0  # Primary (left) Y-axis title X position
    secondary_y_axis_title_x: float = 0.98  # Secondary (right) Y-axis title X position

    # Maximum number of characters to allow in chart axis titles before truncation.
    # This is applied by the chart XML writer to keep titles from overlapping the plot area.
    chart_axis_title_max_chars: int = 20

    # --- Chart Width for Legend Calculation ---
    default_chart_width_inches: float = (
        5.5  # Approximate chart width for legend calculations (most charts are wide)
    )

    # ============================================================================
    # CHART NUMBER FORMATTING (Config-Driven, One-For-All-Charts)
    # ============================================================================
    # These settings control how numeric tick labels and data labels are formatted.
    # They are applied after chart data is populated (python-pptx + OOXML update paths).

    # Master switch for all numeric tick/data label formatting.
    chart_enable_numeric_formatting: bool = True

    # If True, apply bar-specific formatting rules (reverse category axis order and
    # override data label formatting/position for bar charts).
    chart_enable_bar_specific_formatting: bool = True

    # Numeric tick label number format (applied to all value axes: primary + secondary).
    chart_numeric_tick_label_format: str = "#,##0.00"

    # Numeric data label number format for non-bar charts (when data labels exist).
    chart_numeric_data_label_format: str = "#,##0.00"

    # Bar chart data label number format override (when data labels exist).
    chart_bar_data_label_format: str = "#,##0"

    # If True, reverse the category axis order for bar charts (PowerPoint default
    # for horizontal bars is often inverted relative to desired reading order).
    chart_bar_reverse_category_axis: bool = True

    # Legacy properties for backward compatibility
    chart_plot_area_x: float = 0.02
    chart_plot_area_width: float = 0.96
    chart_axis_title_top_margin_base: float = 0.10
    chart_axis_title_y_position: float = 0.00
    chart_legend_height_max: float = 0.12
    chart_plot_legend_gap: float = 0.00

    def get_chart_axis_title_top_margin(self) -> float:
        """Get the top margin for Y-axis titles."""
        return self.plot_area_top_margin

    def get_chart_plot_area_y(self) -> float:
        """Get plot area Y position."""
        return self.plot_area_top_margin

    def get_chart_plot_area_height(self, legend_height: float = 0.10) -> float:
        """Compute plot area height dynamically based on legend height."""
        return 1.0 - self.plot_area_top_margin - legend_height

    def calculate_legend_entry_width(self, name_length: int) -> float:
        """
        Calculate width needed for a single legend entry.

        Args:
            name_length: Number of characters in series name

        Returns:
            Width in inches
        """
        char_width = self.legend_font_size_pt * self.legend_char_width_factor
        text_width = name_length * char_width
        return self.legend_marker_width + text_width + self.legend_entry_spacing

    def calculate_legend_dimensions(
        self, series_names: list, chart_width_inches: Optional[float] = None
    ) -> dict:
        """
        Calculate legend height and position based on series names.

        Args:
            series_names: List of series name strings
            chart_width_inches: Chart width in inches (uses default if not provided)

        Returns:
            dict with 'height', 'y', 'num_rows', 'entries_per_row'
        """
        if not series_names:
            return {"height": 0.08, "y": 0.92, "num_rows": 1, "entries_per_row": [0]}

        chart_width = chart_width_inches or self.default_chart_width_inches
        available_width = chart_width * self.legend_width

        # Calculate width for each entry
        entry_widths = [
            self.calculate_legend_entry_width(len(name)) for name in series_names
        ]

        # Determine how many entries fit per row
        current_row_width: float = 0.0
        num_rows = 1
        entries_per_row: List[int] = []
        current_row_entries = 0

        for width in entry_widths:
            if current_row_width + width > available_width and current_row_entries > 0:
                entries_per_row.append(current_row_entries)
                num_rows += 1
                current_row_width = width
                current_row_entries = 1
            else:
                current_row_width += width
                current_row_entries += 1

        if current_row_entries > 0:
            entries_per_row.append(current_row_entries)

        # Calculate height
        legend_height = min(
            self.legend_height_max,
            num_rows * self.legend_row_height_factor + self.legend_padding,
        )

        # Calculate Y position (at bottom with margin)
        legend_y = 1.0 - legend_height - self.legend_bottom_margin

        return {
            "height": legend_height,
            "y": legend_y,
            "num_rows": num_rows,
            "entries_per_row": entries_per_row,
        }

    def calculate_plot_area_dimensions(self, legend_y: float) -> dict:
        """
        Calculate plot area dimensions based on legend position.

        Args:
            legend_y: Legend Y position (factor 0.0-1.0)
                     Use 1.0 for charts with no legend (single series)

        Returns:
            dict with 'x', 'y', 'width', 'height', 'x_axis_space'
        """
        # No legend case: legend_y = 1.0 means no legend space needed
        if legend_y >= 0.99:
            # No legend - reserve space for X-axis labels only (19%)
            # With legend it's 20% (labels + legend gap), without legend just need labels
            x_axis_space = 0.19
            plot_height = 1.0 - self.plot_area_top_margin - x_axis_space
            return {
                "x": self.plot_area_x,
                "y": self.plot_area_top_margin,
                "width": self.plot_area_width,
                "height": plot_height,
                "x_axis_space": x_axis_space,
            }

        # Choose X-axis label space based on legend position
        if legend_y >= self.legend_single_row_y_threshold:
            x_axis_space = self.x_axis_label_space_single_row
        else:
            x_axis_space = self.x_axis_label_space_multi_row

        # Calculate plot height
        max_plot_bottom = legend_y - x_axis_space
        plot_height = max(
            self.plot_area_min_height, max_plot_bottom - self.plot_area_top_margin
        )

        return {
            "x": self.plot_area_x,
            "y": self.plot_area_top_margin,
            "width": self.plot_area_width,
            "height": plot_height,
            "x_axis_space": x_axis_space,
        }

    # Chart axis title font size - Calibri 9pt to match other chart text
    chart_axis_title_font_size: int = (
        900  # 9pt in hundredths of a point (PowerPoint XML format)
    )

    # ============================================================================
    # CHART AXIS TITLE POSITIONING
    # ============================================================================
    # These settings control the X position of Y-axis titles relative to the chart.
    # All values are factors (0.0 to 1.0) relative to the chart container edges.
    #
    # Y-axis title Y position is calculated using get_chart_plot_area_y() to align
    # titles with the plot area top. This ensures dual Y-axis titles (for combo
    # charts like double bar + line) are on the same horizontal line.
    #
    # Note: PowerPoint renders axis labels INSIDE the plot area automatically.
    # The Y-axis title should be positioned just outside the plot area edge.

    # Primary (left) Y-axis title X position - at left edge of chart
    chart_primary_y_axis_title_x: float = 0.0  # X position (left edge)

    # Secondary (right) Y-axis title X position - at right edge of chart
    chart_secondary_y_axis_title_x: float = 0.98  # X position (right edge)

    # ============================================================================
    # EMBEDDED EXCEL DATA LAYOUT CONFIGURATION
    # ============================================================================
    # These settings control how chart data is written to embedded Excel workbooks.
    # Standard Excel chart data layout: Row 1 = headers, Column A = categories,
    # Columns B onwards = series data.

    excel_header_row: int = 1  # Row number for series headers
    excel_data_start_row: int = 2  # Row number where data begins
    excel_category_column: int = 1  # Column number for categories (A=1)
    excel_series_start_column: int = 2  # Column number where series data begins (B=2)
    excel_default_sheet_name: str = (
        "Sheet1"  # Default sheet name for formula references
    )

    # PPTX/OOXML standard directory names (part of OOXML specification)
    pptx_ppt_dir: str = "ppt"  # Main PPT content directory
    pptx_embeddings_dir: str = "embeddings"  # Embedded files directory

    # ============================================================================
    # EMBEDDED EXCEL UPDATE MODE
    # ============================================================================
    # Controls how we keep the embedded Excel workbook (used by "Edit Data in Excel")
    # in sync with the chart.
    #
    # - "auto": use OpenXML XLSX update for combo charts (to preserve structure),
    #           otherwise use python-pptx replace_data().
    # - "openxml": always update XLSX via OpenXML (pure zip/xml manipulation).
    # - "python_pptx": always update via python-pptx replace_data() (may break combo charts).
    embedded_excel_update_mode: str = "auto"


@dataclass(frozen=True)
class TemplateSet:
    """Represents the PPT templates that should be used for a run."""

    first_slide: Optional[str]
    base_slide: str
    last_slide: Optional[str]


@dataclass(frozen=True)
class LayoutPreferenceRule:
    """Conditional rule that can override the default layout sequence."""

    condition: Optional[str]
    layout_sequence: Tuple[str, ...]


@dataclass(frozen=True)
class LayoutPreferenceConfig:
    """Defines the default and conditional layout sequences per sub-type."""

    default_sequence: Tuple[str, ...]
    rules: Tuple[LayoutPreferenceRule, ...] = ()


@dataclass(frozen=True)
class LayoutThresholdConfig:
    """Thresholds for layout decision making."""

    full_width_detection_threshold: float = 0.9  # 90% of half-width triggers full_width
    min_scale_threshold_aggressive: float = (
        0.4  # 40% minimum scale for aggressive scaling
    )
    min_scale_threshold_normal: float = 0.6  # 60% minimum scale for normal scaling
    aspect_ratio_distortion_tolerance: float = (
        0.3  # 30% tolerance for aspect ratio distortion
    )


_DEFAULT_PROPERTY_SUB_TYPE = "figures"

_TEMPLATE_CONFIGS: Dict[str, TemplateSet] = {
    "figures": TemplateSet(
        first_slide="first_slide_base.pptx",
        base_slide="base_clean.pptx",
        last_slide="last_slide.pptx",
    ),
    "snapshot": TemplateSet(
        first_slide="snapshot_first_slide_base.pptx",
        base_slide="snapshot_base_clean.pptx",
        last_slide="snapshot_last_slide.pptx",
    ),
    "submarket": TemplateSet(
        first_slide="submarket_first_slide_base.pptx",
        base_slide="base_clean.pptx",
        last_slide=None,
    ),
}

_SLIDE_CONSTRAINT_PROFILES: Dict[str, SlideConstraints] = {
    "figures": SlideConstraints(
        gutter_vertical=0.05,
        margin_bottom=0.40,
        margin_top=0.45,
        gutter_horizontal=0.1
    ),
    "submarket": SlideConstraints(
        slide_width=13.33,
        slide_height=7.5,
        margin_top=0.5,
        margin_bottom=0.3,
        margin_left=0.4,
        margin_right=0.4,
        gutter_horizontal=0.1,
        gutter_vertical=0.2,
        min_font_size=10.0,
        default_font_size=14.0,
    ),
    "snapshot": SlideConstraints(
        slide_width=8.5,
        slide_height=11.0,
        margin_top=0.8,
        margin_bottom=0.6,
        margin_left=0.35,
        margin_right=0.45,
        gutter_horizontal=0.0,
        gutter_vertical=0.1,  # Increased spacing between Note and Figure labels
        min_font_size=10.0,
        default_font_size=14.0,
    ),
}


TitleStrategy = Dict[str, Any]

_TITLE_STRATEGIES: Dict[str, TitleStrategy] = {
    "figures": {
        "strategy": "default",
    },
    "snapshot": {
        "strategy": "format",
        "template": "{market_name} {sector_type} Snapshot",
    },
    "submarket": {
        "strategy": "geography",
        "template_placeholder": "[Submarket Name] Submarket Snapshot",
        "geography_patterns": {
            "district": "{value} District Snapshot",
            "submarket": "{value} Submarket Snapshot",
            "vacancy_index": "{value} Index Snapshot",
        },
        "default_template": "{market_name} {sector_type} Snapshot",
    },
}

_HEADER_FORMAT_CONFIGS: Dict[str, str] = {
    "figures": "FIGURES | {market_name} {header_prefix}| {quarter}",
    "snapshot": "SNAPSHOT | {market_name} {sector_type} | {quarter}",
    # Submarket uses dynamic title (geography-based) instead of market_name + sector_type
    "submarket": "SNAPSHOT | {title} | {quarter}",
}

_ALLOWED_LAYOUT_TYPES: Dict[str, Set[str]] = {
    "figures": {"base_slide", "grid_2x2", "full_width", "hybrid_grid"},
    "snapshot": {"base_slide", "full_width"},
    "submarket": {"base_slide", "full_width"},
}

# Element exclusion configuration per property_sub_type
# By default, all element types are included unless explicitly listed here
# Element types: commentary, chart, table
_ELEMENT_EXCLUSION_CONFIG: Dict[str, Set[str]] = {
    "figures": set(),  # No exclusions - include all elements
    "snapshot": {"commentary"},  # Exclude commentary only - charts and tables remain
    "submarket": {"commentary"},  # Exclude commentary only - charts and tables remain
}

_LAYOUT_PREFERENCE_CONFIGS: Dict[str, LayoutPreferenceConfig] = {
    "figures": LayoutPreferenceConfig(
        default_sequence=("grid_2x2", "full_width"),
        rules=(
            LayoutPreferenceRule(
                condition="all_tables",
                layout_sequence=("full_width", "grid_2x2"),
            ),
        ),
    ),
    "snapshot": LayoutPreferenceConfig(
        default_sequence=("full_width", "grid_2x2"),
    ),
    "submarket": LayoutPreferenceConfig(
        default_sequence=("full_width", "grid_2x2"),
    ),
}


# Unified slide layout configurations (defined after _SLIDE_CONSTRAINT_PROFILES)
def _build_slide_layout_configs() -> Dict[str, SlideLayoutConfig]:
    """Build unified slide layout configs from existing constraint profiles."""
    return {
        "figures": SlideLayoutConfig(
            base_constraints=_SLIDE_CONSTRAINT_PROFILES["figures"],
            first_slide_style="kpi_row",
            first_slide_start_top=0.8 + 2.8 + 0.2,  # header margin + KPI band + spacer
            first_slide_margin_left=0.84,
            first_slide_margin_right=0.5,
            first_slide_margin_bottom=0.45,
            first_slide_gutter_horizontal=0.1,
            first_slide_gutter_vertical=0.1,
            first_slide_max_elements=2,
            first_slide_rows=1,  # 1×2 grid for first slide
            first_slide_cols=2,
            first_slide_kpi_section_height=2.8,
            first_slide_capacity=2,
            regular_slide_capacity=4,
            uses_dynamic_capacity=False,
            show_section_titles=True,  # Show section titles for figures
            full_width_table_gutter_vertical=0.05,  # Reduced gutter between consecutive tables
        ),
        "snapshot": SlideLayoutConfig(
            base_constraints=_SLIDE_CONSTRAINT_PROFILES["snapshot"],
            first_slide_style="full_width",
            first_slide_start_top=2.3,  # Reduced to fit Figure 3 on first slide
            first_slide_margin_left=0.35,
            first_slide_margin_right=0.45,
            first_slide_margin_bottom=0.6,
            first_slide_gutter_horizontal=0.0,
            first_slide_gutter_vertical=0.1,  # Reduced gutter to fit more figures on first slide
            first_slide_max_elements=None,
            first_slide_capacity=None,  # Dynamic
            regular_slide_capacity=None,  # Dynamic
            uses_dynamic_capacity=True,
            show_section_titles=False,  # Hide section titles for snapshot
            full_width_table_gutter_vertical=0.05,  # Reduced gutter between consecutive tables
        ),
        "submarket": SlideLayoutConfig(
            base_constraints=_SLIDE_CONSTRAINT_PROFILES["submarket"],
            first_slide_style="grid",
            first_slide_start_top=1.85,
            first_slide_margin_left=0.3,
            first_slide_margin_right=0.3,
            first_slide_margin_bottom=0.3,
            first_slide_gutter_horizontal=0.1,
            first_slide_gutter_vertical=0.1,
            first_slide_max_elements=6,
            first_slide_rows=2,
            first_slide_cols=3,
            first_slide_capacity=6,
            regular_slide_capacity=None,  # Dynamic
            uses_dynamic_capacity=True,
            show_section_titles=False,  # Hide section titles for submarket
            full_width_table_gutter_vertical=0.05,  # Reduced gutter between consecutive tables
        ),
    }


_SLIDE_LAYOUT_CONFIGS = _build_slide_layout_configs()

_LAYOUT_THRESHOLD_CONFIGS: Dict[str, LayoutThresholdConfig] = {
    "figures": LayoutThresholdConfig(),
    "snapshot": LayoutThresholdConfig(),
    "submarket": LayoutThresholdConfig(),
}


def get_ppt_template_config(property_sub_type: Optional[str]) -> TemplateSet:
    """
    Return the template set for the provided property_sub_type.

    Falls back to the figures template set whenever the input is empty or
    not explicitly defined.
    """

    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    return _TEMPLATE_CONFIGS.get(key, _TEMPLATE_CONFIGS[_DEFAULT_PROPERTY_SUB_TYPE])


def get_title_strategy(property_sub_type: Optional[str]) -> TitleStrategy:
    """
    Return the title strategy dict for given property_sub_type.
    """

    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    return _TITLE_STRATEGIES.get(key, _TITLE_STRATEGIES[_DEFAULT_PROPERTY_SUB_TYPE])


def get_header_format_config(property_sub_type: Optional[str]) -> str:
    """
    Return the header format template string for given property_sub_type.

    The template should be formatted with:
    - market_name: Market name (will be uppercased for figures, snapshot, submarket)
    - header_prefix: Header prefix (for figures only, will be uppercased)
    - sector_type: Sector type (for snapshot/submarket only, will be uppercased)
    - quarter: Quarter string (already formatted)
    """
    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    return _HEADER_FORMAT_CONFIGS.get(
        key, _HEADER_FORMAT_CONFIGS[_DEFAULT_PROPERTY_SUB_TYPE]
    )


def should_exclude_element(property_sub_type: Optional[str], element_type: str) -> bool:
    """
    Check if an element type should be excluded for the given property_sub_type.

    This function enables flexible, config-driven element filtering for PPT generation.
    To exclude additional element types for any property_sub_type, simply update the
    _ELEMENT_EXCLUSION_CONFIG dictionary above.

    Args:
        property_sub_type: Property sub type (figures, submarket, snapshot, etc.)
        element_type: Element type (commentary, chart, table, title, kpi, summary)

    Returns:
        True if element should be excluded (filtered out), False if it should be included

    Examples:
        >>> should_exclude_element("snapshot", "commentary")
        True  # Commentary is excluded for snapshot
        >>> should_exclude_element("snapshot", "chart")
        False  # Charts are included for snapshot
        >>> should_exclude_element("figures", "commentary")
        False  # Commentary is included for figures
    """
    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    excluded_elements = _ELEMENT_EXCLUSION_CONFIG.get(key, set())
    return element_type.lower() in excluded_elements


def get_allowed_layout_types(property_sub_type: Optional[str]) -> Set[str]:
    """
    Return the allowed layout type values for the property_sub_type.
    """

    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    return _ALLOWED_LAYOUT_TYPES.get(
        key, _ALLOWED_LAYOUT_TYPES[_DEFAULT_PROPERTY_SUB_TYPE]
    )


def get_layout_preference_config(
    property_sub_type: Optional[str],
) -> LayoutPreferenceConfig:
    """
    Return layout preference config for the property_sub_type.
    """

    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    return _LAYOUT_PREFERENCE_CONFIGS.get(
        key, _LAYOUT_PREFERENCE_CONFIGS[_DEFAULT_PROPERTY_SUB_TYPE]
    )


def get_slide_layout_config(
    property_sub_type: Optional[str],
) -> SlideLayoutConfig:
    """
    Return the unified slide layout configuration for the property_sub_type.
    This is the primary function to use for all slide-related configuration.
    """
    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    return _SLIDE_LAYOUT_CONFIGS.get(
        key, _SLIDE_LAYOUT_CONFIGS[_DEFAULT_PROPERTY_SUB_TYPE]
    )


def get_slide_constraint_profile(
    property_sub_type: Optional[str],
) -> SlideConstraints:
    """
    Return the slide constraint profile for the property_sub_type.
    Convenience wrapper around get_slide_layout_config().get_constraints().
    """
    layout_config = get_slide_layout_config(property_sub_type)
    return layout_config.get_constraints(is_first_slide=False)


def get_element_dimensions(
    property_sub_type: Optional[str] = None,
) -> ElementDimensions:
    """
    Return element dimension constants for the property_sub_type.

    Currently returns default dimensions for all property types.
    Can be extended later to support property_sub_type-specific values if needed.
    """
    # For now, return default dimensions for all types
    # Can be extended with _ELEMENT_DIMENSION_PROFILES dict if needed
    return ElementDimensions()


def get_layout_threshold_config(
    property_sub_type: Optional[str],
) -> LayoutThresholdConfig:
    """
    Return layout threshold configuration for the property_sub_type.
    """
    key = (property_sub_type or _DEFAULT_PROPERTY_SUB_TYPE).strip().lower()
    return _LAYOUT_THRESHOLD_CONFIGS.get(
        key, _LAYOUT_THRESHOLD_CONFIGS[_DEFAULT_PROPERTY_SUB_TYPE]
    )


def determine_layout_type_from_criteria(
    property_sub_type: str,
    is_first_slide: bool = False,
    normalized_preference: Optional[str] = None,
    elements: Optional[List[Dict[str, Any]]] = None,
    blocks: Optional[List[Any]] = None,
) -> str:
    """
    Determine layout type based on criteria rules, element types, and preferences.

    This function works with either element dictionaries (from JSON) or ContentBlock objects.
    At least one of 'elements' or 'blocks' must be provided.

    Priority:
    1. Normalized layout preference (if provided and valid)
    2. Criteria-based rules (property_sub_type rules, element type rules, layout preference configs)
    3. Default based on property_sub_type

    Args:
        property_sub_type: Property sub type (figures, submarket, snapshot)
        is_first_slide: Whether this is the first slide
        normalized_preference: Normalized layout preference (None if not provided or invalid)
        elements: List of element dictionaries (from JSON format)
        blocks: List of ContentBlock objects (from orchestrator)

    Returns:
        Layout type string: "full_width", "grid_2x2", "hybrid_grid", or "base_slide"
    """
    # Priority 1: Use normalized preference if provided
    if normalized_preference:
        return normalized_preference

    # Priority 3: Apply criteria-based rules
    preference_config = get_layout_preference_config(property_sub_type)

    # Determine if all elements/blocks are tables
    all_tables = False
    if elements:
        # Check element dictionaries
        selected_elements = [e for e in elements if e.get("selected", True)]
        all_tables = len(selected_elements) > 0 and all(
            e.get("element_type") == "table" for e in selected_elements
        )
    elif blocks:
        # Check ContentBlock objects
        # Import here to avoid circular dependency
        from hello.utils.ppt_helpers_utils.ppt_helpers.slide_orchestrator import (
            ContentType,
        )

        all_tables = len(blocks) > 0 and all(
            hasattr(block, "type") and block.type == ContentType.TABLE
            for block in blocks
        )

    # Evaluate layout preference rules
    for rule in preference_config.rules:
        if rule.condition == "all_tables" and all_tables:
            # Return first layout in the sequence
            if rule.layout_sequence:
                return rule.layout_sequence[0]

    # Priority 4: Use default sequence from preference config
    if preference_config.default_sequence:
        # For first slide, use property_sub_type specific rules
        if is_first_slide:
            if property_sub_type in ("figures", "submarket"):
                return "grid_2x2"  # First slide uses grid for these types
            else:
                return "full_width"  # Other types use full_width for first slide
        else:
            # For middle slides, use first layout in default sequence
            return preference_config.default_sequence[0]

    # Priority 5: Fallback based on property_sub_type
    if property_sub_type == "submarket" and not is_first_slide:
        return "full_width"
    elif property_sub_type == "snapshot":
        return "full_width"
    elif property_sub_type == "figures":
        if all_tables and not is_first_slide:
            return "full_width"
        else:
            return "grid_2x2"
    else:
        return "full_width"


# ============================================================================
# CHART LAYOUT CONFIG HELPER FUNCTIONS
# ============================================================================


def get_chart_group(chart_type: Optional[str]) -> str:
    """
    Get the chart group name for a given chart type.

    Args:
        chart_type: Chart type string (e.g., 'bar', 'line', 'pie', 'combo_bar_line')

    Returns:
        Group name (e.g., 'VERTICAL_BAR', 'LINE', 'PIE_DONUT', 'COMBO')
    """
    if not chart_type:
        return _DEFAULT_CHART_GROUP

    # Normalize chart type: lowercase and strip
    normalized = chart_type.strip().lower()

    # Direct lookup first (exact match)
    if normalized in _CHART_TYPE_TO_GROUP:
        return _CHART_TYPE_TO_GROUP[normalized]

    # Priority checks for specific chart types (before generic substring matching)
    # These are checked first because they have complex names that might contain
    # substrings of other chart types (e.g., "combo_chart_doublebar_line" contains "bar")

    # Check for single column stacked first (must check before generic "column" check)
    if "single_column_stacked" in normalized or "single column stacked" in normalized:
        return "SINGLE_COLUMN_STACKED"

    # Check for combo charts first (they often have complex names with "bar" in them)
    if "combo" in normalized:
        return "COMBO"

    # Check for horizontal bar (must check before generic "bar" check)
    if "horizontal" in normalized and "bar" in normalized:
        return "HORIZONTAL_BAR"

    # Check for pie/donut
    if "pie" in normalized or "donut" in normalized:
        return "PIE_DONUT"

    # Check for line charts (check before bar since some charts might have both)
    if "line" in normalized and "bar" not in normalized:
        return "LINE"

    # Try to match by prefix/substring for remaining cases
    for type_key, group in _CHART_TYPE_TO_GROUP.items():
        if type_key in normalized or normalized in type_key:
            return group

    # Final fallback checks for generic types
    if "line" in normalized:
        return "LINE"

    if "bar" in normalized or "column" in normalized:
        return "VERTICAL_BAR"

    return _DEFAULT_CHART_GROUP


def get_chart_layout_config(chart_type: Optional[str]) -> ChartLayoutConfig:
    """
    Get the chart layout configuration for a given chart type.

    Args:
        chart_type: Chart type string (e.g., 'bar', 'line', 'pie', 'combo_bar_line')

    Returns:
        ChartLayoutConfig for the chart's group
    """
    group = get_chart_group(chart_type)
    return _CHART_GROUP_CONFIGS.get(group, _CHART_GROUP_CONFIGS[_DEFAULT_CHART_GROUP])


def get_chart_group_config(group_name: str) -> ChartLayoutConfig:
    """
    Get the chart layout configuration for a given group name directly.

    Args:
        group_name: Group name (e.g., 'VERTICAL_BAR', 'LINE', 'PIE_DONUT', 'COMBO')

    Returns:
        ChartLayoutConfig for the group
    """
    return _CHART_GROUP_CONFIGS.get(
        group_name.upper(), _CHART_GROUP_CONFIGS[_DEFAULT_CHART_GROUP]
    )


def get_available_chart_groups() -> List[str]:
    """
    Get list of all available chart group names.

    Returns:
        List of group names
    """
    return list(_CHART_GROUP_CONFIGS.keys())


__all__ = [
    "SlideLayoutConfig",
    "get_slide_layout_config",
    "SlideConstraints",
    "ElementDimensions",
    "TemplateSet",
    "get_slide_constraint_profile",
    "LayoutThresholdConfig",
    "get_ppt_template_config",
    "get_title_strategy",
    "get_header_format_config",
    "get_allowed_layout_types",
    "get_element_dimensions",
    "get_layout_threshold_config",
    "LayoutPreferenceRule",
    "LayoutPreferenceConfig",
    "get_layout_preference_config",
    "determine_layout_type_from_criteria",
    "should_exclude_element",
    # Chart-specific config exports
    "ChartLayoutConfig",
    "get_chart_layout_config",
    "get_chart_group",
    "get_chart_group_config",
    "get_available_chart_groups",
]
