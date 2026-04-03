"""
Comprehensive PPT Generation Test Script

Generates a presentation that exercises EVERY feature of the PPT engine:
- All 14 chart types (Bar, Line Single/Multi, Area Single/Multi, Horizontal Bar,
  Stacked Bar, Pie, Donut, Single Column Stacked, 4 Combo types)
- All 4 table types (table, market_stats_table, market_stats_sub_table,
  industrial_figures_template)
- All layout preferences (Full Width, Content 2x2 Grid, grid_2x2, full_width)
- All 3 property_sub_types (figures, snapshot, submarket) in separate output files
- Commentary / text blocks with bullet points and paragraphs
- Section titles, figure numbering, axis config, quadrant positions
- Mixed content sections (charts + commentary, tables + commentary)
- Edge cases: large tables, single-element sections, 4-element grid sections

Each section is named with the feature it tests so failures are immediately
identifiable (e.g., "SEC_01_BAR_CHART_full_width" tells you exactly what broke).
"""

import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

current_dir = Path(__file__).parent
backend_dir = current_dir.parent.parent
sys.path.insert(0, str(backend_dir))

from app.ppt_engine.ppt_helpers_utils.services.frontend_json_processor import FrontendJSONProcessor
from app.ppt_engine.ppt_helpers_utils.services.presentation_generator import PresentationGenerator


# ---------------------------------------------------------------------------
# Realistic chart data fixtures
# ---------------------------------------------------------------------------

CHART_DATA = {
    "bar": [
        {"Market": "Chicago", "Volume_MSF": 42},
        {"Market": "Dallas", "Volume_MSF": 38},
        {"Market": "Atlanta", "Volume_MSF": 31},
        {"Market": "Phoenix", "Volume_MSF": 28},
        {"Market": "Denver", "Volume_MSF": 22},
    ],
    "line_single": [
        {"Quarter": "2023 Q1", "Vacancy_Rate": 4.2},
        {"Quarter": "2023 Q2", "Vacancy_Rate": 4.5},
        {"Quarter": "2023 Q3", "Vacancy_Rate": 4.8},
        {"Quarter": "2023 Q4", "Vacancy_Rate": 5.1},
        {"Quarter": "2024 Q1", "Vacancy_Rate": 5.3},
        {"Quarter": "2024 Q2", "Vacancy_Rate": 5.0},
        {"Quarter": "2024 Q3", "Vacancy_Rate": 4.7},
    ],
    "line_multi": [
        {"Quarter": "2024 Q1", "Asking_Rent": 12.10, "Effective_Rent": 10.80},
        {"Quarter": "2024 Q2", "Asking_Rent": 12.50, "Effective_Rent": 11.20},
        {"Quarter": "2024 Q3", "Asking_Rent": 12.80, "Effective_Rent": 11.50},
        {"Quarter": "2024 Q4", "Asking_Rent": 13.20, "Effective_Rent": 11.90},
        {"Quarter": "2025 Q1", "Asking_Rent": 13.10, "Effective_Rent": 12.00},
    ],
    "area_single": [
        {"Month": "Jan", "Absorption_SF": 120000},
        {"Month": "Feb", "Absorption_SF": 145000},
        {"Month": "Mar", "Absorption_SF": 132000},
        {"Month": "Apr", "Absorption_SF": 158000},
        {"Month": "May", "Absorption_SF": 167000},
        {"Month": "Jun", "Absorption_SF": 149000},
    ],
    "area_multi": [
        {"Quarter": "2024 Q1", "Class_A": 320, "Class_B": 210, "Class_C": 90},
        {"Quarter": "2024 Q2", "Class_A": 340, "Class_B": 225, "Class_C": 85},
        {"Quarter": "2024 Q3", "Class_A": 360, "Class_B": 230, "Class_C": 100},
        {"Quarter": "2024 Q4", "Class_A": 375, "Class_B": 245, "Class_C": 95},
        {"Quarter": "2025 Q1", "Class_A": 390, "Class_B": 260, "Class_C": 105},
    ],
    "horizontal_bar": [
        {"Region": "Northeast", "Rent_Growth_Pct": 5.2},
        {"Region": "Mid-Atlantic", "Rent_Growth_Pct": 4.4},
        {"Region": "Midwest", "Rent_Growth_Pct": 3.8},
        {"Region": "South", "Rent_Growth_Pct": 6.1},
        {"Region": "Mountain West", "Rent_Growth_Pct": 5.0},
        {"Region": "Pacific", "Rent_Growth_Pct": 4.9},
    ],
    "stacked_bar": [
        {"Market": "North", "Direct_SF": 820000, "Sublease_SF": 140000},
        {"Market": "South", "Direct_SF": 610000, "Sublease_SF": 210000},
        {"Market": "East", "Direct_SF": 705000, "Sublease_SF": 95000},
        {"Market": "West", "Direct_SF": 890000, "Sublease_SF": 260000},
        {"Market": "Central", "Direct_SF": 540000, "Sublease_SF": 120000},
    ],
    "pie": [
        {"Segment": "Class A", "Share": 42},
        {"Segment": "Class B", "Share": 33},
        {"Segment": "Class C", "Share": 18},
        {"Segment": "Unclassified", "Share": 7},
    ],
    "donut": [
        {"Tenant_Type": "Logistics / 3PL", "Pct": 48},
        {"Tenant_Type": "Light Mfg", "Pct": 27},
        {"Tenant_Type": "R&D / Lab", "Pct": 14},
        {"Tenant_Type": "Other", "Pct": 11},
    ],
    "single_column_stacked": [
        {"Component": "Core / Core+", "Value": 48},
        {"Component": "Value-Add", "Value": 28},
        {"Component": "Opportunistic", "Value": 14},
        {"Component": "Development", "Value": 10},
    ],
    "combo_single_bar_line": [
        {"City": "Chicago", "Leasing_Vol": 118, "Cap_Rate": 5.4},
        {"City": "Dallas", "Leasing_Vol": 96, "Cap_Rate": 5.8},
        {"City": "Atlanta", "Leasing_Vol": 104, "Cap_Rate": 5.6},
        {"City": "Phoenix", "Leasing_Vol": 88, "Cap_Rate": 6.1},
        {"City": "Denver", "Leasing_Vol": 72, "Cap_Rate": 6.3},
    ],
    "combo_double_bar_line": [
        {"Year": "2022", "New_Supply": 42, "Net_Absorption": 38, "Vacancy": 5.1},
        {"Year": "2023", "New_Supply": 55, "Net_Absorption": 44, "Vacancy": 5.4},
        {"Year": "2024", "New_Supply": 48, "Net_Absorption": 41, "Vacancy": 5.7},
        {"Year": "2025E", "New_Supply": 40, "Net_Absorption": 45, "Vacancy": 5.3},
    ],
    "combo_stacked_bar_line": [
        {"Quarter": "2024 Q1", "Direct": 320, "Sublease": 90, "Rent_Index": 100},
        {"Quarter": "2024 Q2", "Direct": 340, "Sublease": 110, "Rent_Index": 102},
        {"Quarter": "2024 Q3", "Direct": 360, "Sublease": 95, "Rent_Index": 105},
        {"Quarter": "2024 Q4", "Direct": 375, "Sublease": 125, "Rent_Index": 108},
    ],
    "combo_area_bar": [
        {"Month": "Jan", "Pipeline_MSF": 72, "Deliveries_MSF": 58},
        {"Month": "Feb", "Pipeline_MSF": 88, "Deliveries_MSF": 64},
        {"Month": "Mar", "Pipeline_MSF": 91, "Deliveries_MSF": 70},
        {"Month": "Apr", "Pipeline_MSF": 85, "Deliveries_MSF": 90},
    ],
}

# ---------------------------------------------------------------------------
# Realistic table data fixtures
# ---------------------------------------------------------------------------

TABLE_DATA = {
    "generic": [
        {"Metric": "Asking Rent ($/SF)", "High": "15.50", "Low": "8.25", "Avg": "11.20"},
        {"Metric": "Sale Price ($/SF)", "High": "210", "Low": "145", "Avg": "178"},
        {"Metric": "Cap Rate (%)", "High": "6.5", "Low": "4.8", "Avg": "5.4"},
        {"Metric": "NOI Growth (%)", "High": "4.2", "Low": "1.8", "Avg": "3.1"},
    ],
    "market_stats": [
        {"Submarket": "O'Hare", "Inventory_SF": "120,450,000", "Vacancy": "4.2%", "Net_Absorption": "245,000", "Under_Construction": "1,200,000"},
        {"Submarket": "I-88 Corridor", "Inventory_SF": "85,200,000", "Vacancy": "5.1%", "Net_Absorption": "(12,000)", "Under_Construction": "450,000"},
        {"Submarket": "South Suburbs", "Inventory_SF": "92,100,000", "Vacancy": "6.8%", "Net_Absorption": "115,000", "Under_Construction": "0"},
        {"Submarket": "Central City", "Inventory_SF": "45,000,000", "Vacancy": "3.5%", "Net_Absorption": "45,000", "Under_Construction": "85,000"},
        {"Submarket": "Lake County", "Inventory_SF": "38,700,000", "Vacancy": "7.2%", "Net_Absorption": "(8,500)", "Under_Construction": "0"},
    ],
    "market_stats_sub": [
        {"Item": "Leasing Activity", "Chicago": "1.2M SF", "Dallas": "0.9M SF", "New York": "0.5M SF", "Phoenix": "0.7M SF"},
        {"Item": "Net Absorption", "Chicago": "450K SF", "Dallas": "120K SF", "New York": "(50K) SF", "Phoenix": "280K SF"},
        {"Item": "Deliveries", "Chicago": "800K SF", "Dallas": "1.5M SF", "New York": "200K SF", "Phoenix": "950K SF"},
        {"Item": "Under Construction", "Chicago": "2.1M SF", "Dallas": "3.0M SF", "New York": "0.8M SF", "Phoenix": "1.2M SF"},
    ],
    "industrial_figures": [
        {"Market": "Hub Alpha", "Total_SF": "10,000,000", "Available_SF": "500,000", "Availability_Rate": "5.0%"},
        {"Market": "Hub Beta", "Total_SF": "15,000,000", "Available_SF": "1,200,000", "Availability_Rate": "8.0%"},
        {"Market": "Hub Gamma", "Total_SF": "8,500,000", "Available_SF": "340,000", "Availability_Rate": "4.0%"},
    ],
    "large_table": [
        {"Submarket": f"Submarket_{chr(65 + i)}", "Inventory": f"{(i + 5) * 10},000,000",
         "Vacancy": f"{3.5 + i * 0.4:.1f}%", "Absorption": f"{(i + 1) * 50},000",
         "Rent_PSF": f"${8.50 + i * 0.75:.2f}", "YoY_Change": f"{1.5 + i * 0.3:.1f}%",
         "Under_Const": f"{i * 200},000"}
        for i in range(12)
    ],
}


def _chart_element(eid, chart_type_display, chart_name, data_key, order, label=None, axis_config=None):
    """Helper to build a chart element dict."""
    elem = {
        "id": eid,
        "element_type": "chart",
        "label": label or chart_name,
        "selected": True,
        "display_order": order,
        "config": {
            "chart_type": chart_type_display,
            "chart_name": chart_name,
            "chart_data": CHART_DATA[data_key],
        },
    }
    if axis_config:
        elem["config"]["axisConfig"] = axis_config
    return elem


def _table_element(eid, table_data_key, table_type, label, order, render_full=False):
    """Helper to build a table element dict."""
    elem = {
        "id": eid,
        "element_type": "table",
        "label": label,
        "selected": True,
        "display_order": order,
        "config": {
            "table_data": TABLE_DATA[table_data_key],
        },
    }
    if table_type:
        elem["config"]["table_type"] = table_type
    if render_full:
        elem["config"]["render_full_table"] = True
    return elem


def _commentary_element(eid, heading, text, order):
    """Helper to build a commentary element dict."""
    return {
        "id": eid,
        "element_type": "commentary",
        "label": heading,
        "selected": True,
        "display_order": order,
        "config": {
            "section_alias": heading,
            "commentary_text": text,
        },
    }


def build_comprehensive_json(property_sub_type="figures"):
    """
    Build the full-coverage JSON payload.

    Section naming convention: SEC_NN_<FEATURE>_<LAYOUT>
    so any failure log immediately reveals what broke.
    """
    sid = 1000  # element id counter

    sections = []

    # ------------------------------------------------------------------
    # SEC_01: Bar Chart — Full Width
    # ------------------------------------------------------------------
    sid += 1
    sections.append({
        "id": 1,
        "key": "SEC_01_BAR_CHART",
        "name": "SEC_01: Bar Chart (Full Width)",
        "display_order": 0,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Bar Chart", "Leasing Volume by Market (MSF)", "bar", 0),
            _commentary_element(sid + 1, "Bar Chart Analysis",
                                "Chicago leads in leasing volume with 42 MSF, followed by Dallas at 38 MSF. "
                                "The spread between top and bottom markets has narrowed year-over-year.",
                                1),
        ],
    })
    sid += 2

    # ------------------------------------------------------------------
    # SEC_02: Line Single Axis — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 2,
        "key": "SEC_02_LINE_SINGLE",
        "name": "SEC_02: Line Single Axis (Full Width)",
        "display_order": 1,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Line - Single axis", "Quarterly Vacancy Rate Trend (%)", "line_single", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_03: Line Multi Axis — Full Width (with axisConfig)
    # ------------------------------------------------------------------
    axis_cfg_multi_line = {
        "xAxis": [{"key": "Quarter", "name": "Quarter"}],
        "yAxis": [
            {"key": "Asking_Rent", "name": "Asking Rent ($/SF)", "isPrimary": True},
            {"key": "Effective_Rent", "name": "Effective Rent ($/SF)", "isPrimary": False},
        ],
        "isMultiAxis": True,
    }
    sections.append({
        "id": 3,
        "key": "SEC_03_LINE_MULTI",
        "name": "SEC_03: Line Multi Axis + axisConfig (Full Width)",
        "display_order": 2,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Line - Multi axis", "Asking vs Effective Rent", "line_multi", 0,
                           axis_config=axis_cfg_multi_line),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_04: Area Single Axis — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 4,
        "key": "SEC_04_AREA_SINGLE",
        "name": "SEC_04: Area Single Axis (Full Width)",
        "display_order": 3,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Area - Single axis", "Monthly Absorption (SF)", "area_single", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_05: Area Multi Axis — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 5,
        "key": "SEC_05_AREA_MULTI",
        "name": "SEC_05: Area Multi Axis (Full Width)",
        "display_order": 4,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Area - Multi axis", "Availability by Class (000 SF)", "area_multi", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_06: Horizontal Bar — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 6,
        "key": "SEC_06_HORIZONTAL_BAR",
        "name": "SEC_06: Horizontal Bar (Full Width)",
        "display_order": 5,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Horizontal Bar", "YoY Rent Growth by Region (%)", "horizontal_bar", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_07: Stacked Bar — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 7,
        "key": "SEC_07_STACKED_BAR",
        "name": "SEC_07: Stacked Bar (Full Width)",
        "display_order": 6,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Stacked bar", "Direct vs Sublease Availability (SF)", "stacked_bar", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_08: Pie + Donut side-by-side — 2x2 Grid
    # ------------------------------------------------------------------
    sections.append({
        "id": 8,
        "key": "SEC_08_PIE_DONUT_GRID",
        "name": "SEC_08: Pie + Donut (2x2 Grid)",
        "display_order": 7,
        "selected": True,
        "layout_preference": "Content (2x2 Grid)",
        "elements": [
            _chart_element(sid, "Pie Chart", "Inventory by Class", "pie", 0),
            _chart_element(sid + 1, "Donut Chart", "Leasing by Tenant Type", "donut", 1),
            _chart_element(sid + 2, "Single Column Stacked Chart", "Allocation by Risk Profile", "single_column_stacked", 2),
            _commentary_element(sid + 3, "Pie/Donut/Stacked Summary",
                                "Class A properties dominate the inventory at 42%. "
                                "Logistics and 3PL tenants account for nearly half of all leasing volume.\n\n"
                                "- Class A leads with 42% of total inventory\n"
                                "- 3PL tenants represent 48% of leasing volume\n"
                                "- Value-Add strategies comprise 28% of allocations",
                                3),
        ],
    })
    sid += 4

    # ------------------------------------------------------------------
    # SEC_09: All 4 Combo charts — 2x2 Grid
    # ------------------------------------------------------------------
    sections.append({
        "id": 9,
        "key": "SEC_09_COMBO_CHARTS_GRID",
        "name": "SEC_09: All 4 Combo Charts (2x2 Grid)",
        "display_order": 8,
        "selected": True,
        "layout_preference": "Content (2x2 Grid)",
        "elements": [
            _chart_element(sid, "Combo - Single Bar + Line", "Leasing Vol vs Cap Rate", "combo_single_bar_line", 0),
            _chart_element(sid + 1, "Combo - Double Bar + Line", "Supply vs Absorption + Vacancy", "combo_double_bar_line", 1),
            _chart_element(sid + 2, "Combo - Stacked Bar + Line", "Direct/Sublease + Rent Index", "combo_stacked_bar_line", 2),
            _chart_element(sid + 3, "Combo - Area + Bar", "Pipeline vs Deliveries (MSF)", "combo_area_bar", 3),
        ],
    })
    sid += 4

    # ------------------------------------------------------------------
    # SEC_10: Generic Table — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 10,
        "key": "SEC_10_TABLE_GENERIC",
        "name": "SEC_10: Generic Table (Full Width)",
        "display_order": 9,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _table_element(sid, "generic", "", "Pricing Summary Metrics", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_11: Market Stats Table — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 11,
        "key": "SEC_11_TABLE_MARKET_STATS",
        "name": "SEC_11: Market Stats Table (Full Width)",
        "display_order": 10,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _table_element(sid, "market_stats", "market_stats_table", "Submarket Statistics Overview", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_12: Market Stats Sub-Table — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 12,
        "key": "SEC_12_TABLE_MARKET_STATS_SUB",
        "name": "SEC_12: Market Stats Sub-Table (Full Width)",
        "display_order": 11,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _table_element(sid, "market_stats_sub", "market_stats_sub_table", "Cross-Market Comparison", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_13: Industrial Figures Template — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 13,
        "key": "SEC_13_TABLE_INDUSTRIAL",
        "name": "SEC_13: Industrial Figures Table (Full Width)",
        "display_order": 12,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _table_element(sid, "industrial_figures", "industrial_figures_template", "Industrial Market Summary", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_14: Large Table with render_full_table — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 14,
        "key": "SEC_14_TABLE_LARGE_RENDER_FULL",
        "name": "SEC_14: Large Table render_full_table=True (Full Width)",
        "display_order": 13,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _table_element(sid, "large_table", "", "12-Row Submarket Detail (Full Render)", 0, render_full=True),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_15: Commentary Only — Full Width (bullets + paragraphs)
    # ------------------------------------------------------------------
    sections.append({
        "id": 15,
        "key": "SEC_15_COMMENTARY_ONLY",
        "name": "SEC_15: Commentary Only (Full Width)",
        "display_order": 14,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _commentary_element(
                sid, "Strategic Outlook",
                "Headline: Market Resilience Continues\n\n"
                "We observe a strong flight-to-quality trend in the industrial sector. "
                "Vacancy rates in core logistics hubs remain below historical averages, "
                "although new deliveries are beginning to impact supply-demand dynamics. "
                "Rent growth is moderating but remains positive across most primary markets.\n\n"
                "- Vacancy rates remain compressed in prime submarkets at 3.5-5.0%\n"
                "- Construction deliveries are reaching a multi-year peak of 48M SF\n"
                "- Rent growth is moderating to 3-5% YoY from 6-8% in 2023\n"
                "- Cap rate compression has stabilized around 5.0-5.5%",
                0,
            ),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_16: Mixed — 2 Charts + 1 Table + Commentary in 2x2 Grid
    # ------------------------------------------------------------------
    sections.append({
        "id": 16,
        "key": "SEC_16_MIXED_GRID",
        "name": "SEC_16: Mixed Content (2x2 Grid)",
        "display_order": 15,
        "selected": True,
        "layout_preference": "Content (2x2 Grid)",
        "elements": [
            _chart_element(sid, "Bar Chart", "Top Markets by Volume", "bar", 0),
            _chart_element(sid + 1, "Line - Single axis", "Vacancy Trend", "line_single", 1),
            _table_element(sid + 2, "generic", "", "Key Metrics", 2),
            _commentary_element(sid + 3, "Mixed Section Notes",
                                "This section combines charts, a table, and commentary "
                                "in a single 2x2 grid layout to test mixed content rendering.",
                                3),
        ],
    })
    sid += 4

    # ------------------------------------------------------------------
    # SEC_17: Two Tables stacked — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 17,
        "key": "SEC_17_TWO_TABLES_STACKED",
        "name": "SEC_17: Two Tables Stacked (Full Width)",
        "display_order": 16,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _table_element(sid, "market_stats", "market_stats_table", "Market Statistics (Primary)", 0),
            _table_element(sid + 1, "generic", "", "Pricing Summary (Secondary)", 1),
        ],
    })
    sid += 2

    # ------------------------------------------------------------------
    # SEC_18: Chart with explicit quadrant_position — 2x2 Grid
    # ------------------------------------------------------------------
    chart_tl = _chart_element(sid, "Pie Chart", "Top-Left Pie", "pie", 0)
    chart_tl["config"]["quadrant_position"] = 0
    chart_tr = _chart_element(sid + 1, "Donut Chart", "Top-Right Donut", "donut", 1)
    chart_tr["config"]["quadrant_position"] = 1
    chart_bl = _chart_element(sid + 2, "Bar Chart", "Bottom-Left Bar", "bar", 2)
    chart_bl["config"]["quadrant_position"] = 2
    chart_br = _chart_element(sid + 3, "Horizontal Bar", "Bottom-Right HBar", "horizontal_bar", 3)
    chart_br["config"]["quadrant_position"] = 3

    sections.append({
        "id": 18,
        "key": "SEC_18_QUADRANT_POSITIONS",
        "name": "SEC_18: Explicit Quadrant Positions (2x2 Grid)",
        "display_order": 17,
        "selected": True,
        "layout_preference": "Content (2x2 Grid)",
        "elements": [chart_tl, chart_tr, chart_bl, chart_br],
    })
    sid += 4

    # ------------------------------------------------------------------
    # SEC_19: Single chart (only 1 element) — Full Width
    # ------------------------------------------------------------------
    sections.append({
        "id": 19,
        "key": "SEC_19_SINGLE_ELEMENT",
        "name": "SEC_19: Single Element Section (Full Width)",
        "display_order": 18,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [
            _chart_element(sid, "Stacked bar", "Single Stacked Bar Element", "stacked_bar", 0),
        ],
    })
    sid += 1

    # ------------------------------------------------------------------
    # SEC_20: Table with column_sequence reordering
    # ------------------------------------------------------------------
    tbl_elem = _table_element(sid, "market_stats_sub", "market_stats_sub_table",
                              "Reordered Columns Table", 0)
    tbl_elem["config"]["table_columns_sequence"] = ["Item", "New York", "Dallas", "Chicago", "Phoenix"]
    sections.append({
        "id": 20,
        "key": "SEC_20_TABLE_COL_REORDER",
        "name": "SEC_20: Table Column Reorder (Full Width)",
        "display_order": 19,
        "selected": True,
        "layout_preference": "Full Width",
        "elements": [tbl_elem],
    })
    sid += 1

    # Assemble the full JSON payload
    return {
        "report": {
            "id": 999,
            "name": f"Comprehensive Test ({property_sub_type})",
            "template_name": "first_slide_base",
            "property_type": "Industrial",
            "property_sub_type": property_sub_type,
            "defined_markets": ["Chicago"],
            "quarter": "2025 Q1",
            "title_only_first_slide": True,
        },
        "sections": sections,
    }


def run_test(property_sub_type, templates_dir, output_dir):
    """Run generation for one property_sub_type and return result dict."""
    label = property_sub_type.upper()
    print(f"\n{'=' * 70}")
    print(f"  TESTING property_sub_type = {label}")
    print(f"{'=' * 70}\n")

    json_data = build_comprehensive_json(property_sub_type)

    # Map template names per sub_type
    template_map = {
        "figures": "first_slide_base",
        "snapshot": "snapshot_first_slide_base",
        "submarket": "submarket_first_slide_base",
    }
    json_data["report"]["template_name"] = template_map.get(property_sub_type, "first_slide_base")

    processor = FrontendJSONProcessor(templates_dir=str(templates_dir))
    generator = PresentationGenerator(output_dir=str(output_dir))

    metadata = processor.extract_presentation_metadata(json_data)
    sections = processor.parse_frontend_json(json_data)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"COMPREHENSIVE_TEST_{property_sub_type}_{timestamp}.pptx"

    result = {
        "property_sub_type": property_sub_type,
        "sections_parsed": len(sections),
        "output_file": None,
        "slide_count": 0,
        "file_size_kb": 0,
        "status": "UNKNOWN",
        "error": None,
    }

    try:
        final_path = generator.generate_presentation(
            sections=sections,
            title=metadata["title"],
            author=metadata.get("author", "CBRE Research"),
            output_filename=output_filename,
            metadata=metadata,
        )
        result["output_file"] = str(final_path)

        from pptx import Presentation
        prs = Presentation(final_path)
        result["slide_count"] = len(prs.slides)
        result["file_size_kb"] = round(os.path.getsize(final_path) / 1024, 2)
        result["status"] = "PASS"

    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
        traceback.print_exc()

    return result


def main():
    print("=" * 70)
    print("  COMPREHENSIVE PPT ENGINE TEST")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    templates_dir = current_dir / "ppt_helpers_utils" / "individual_templates"
    output_dir = backend_dir / "data" / "output_ppt"
    output_dir.mkdir(parents=True, exist_ok=True)

    sub_types = ["figures", "snapshot", "submarket"]
    results = []

    for st in sub_types:
        r = run_test(st, templates_dir, output_dir)
        results.append(r)

    # ------------------------------------------------------------------
    # Summary Report
    # ------------------------------------------------------------------
    print("\n")
    print("=" * 70)
    print("  TEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"{'SubType':<14} {'Status':<8} {'Sections':<10} {'Slides':<8} {'Size(KB)':<10} {'File'}")
    print("-" * 70)

    all_passed = True
    for r in results:
        fname = Path(r["output_file"]).name if r["output_file"] else "N/A"
        print(
            f"{r['property_sub_type']:<14} "
            f"{r['status']:<8} "
            f"{r['sections_parsed']:<10} "
            f"{r['slide_count']:<8} "
            f"{r['file_size_kb']:<10} "
            f"{fname}"
        )
        if r["status"] != "PASS":
            all_passed = False
            print(f"  ERROR: {r['error']}")

    print("-" * 70)

    # Feature coverage summary
    print("\nFEATURE COVERAGE:")
    features = [
        ("Chart: Bar Chart", "SEC_01"),
        ("Chart: Line - Single axis", "SEC_02"),
        ("Chart: Line - Multi axis + axisConfig", "SEC_03"),
        ("Chart: Area - Single axis", "SEC_04"),
        ("Chart: Area - Multi axis", "SEC_05"),
        ("Chart: Horizontal Bar", "SEC_06"),
        ("Chart: Stacked bar", "SEC_07"),
        ("Chart: Pie Chart", "SEC_08"),
        ("Chart: Donut Chart", "SEC_08"),
        ("Chart: Single Column Stacked", "SEC_08"),
        ("Chart: Combo - Single Bar + Line", "SEC_09"),
        ("Chart: Combo - Double Bar + Line", "SEC_09"),
        ("Chart: Combo - Stacked Bar + Line", "SEC_09"),
        ("Chart: Combo - Area + Bar", "SEC_09"),
        ("Table: Generic (default)", "SEC_10"),
        ("Table: market_stats_table", "SEC_11"),
        ("Table: market_stats_sub_table", "SEC_12"),
        ("Table: industrial_figures_template", "SEC_13"),
        ("Table: Large 12-row render_full_table", "SEC_14"),
        ("Table: Column reorder sequence", "SEC_20"),
        ("Commentary: Bullets + paragraphs", "SEC_15"),
        ("Commentary: With chart (mixed)", "SEC_01, SEC_08"),
        ("Layout: Full Width", "SEC_01-07, 10-15, 17, 19-20"),
        ("Layout: Content (2x2 Grid)", "SEC_08, 09, 16, 18"),
        ("Layout: Explicit quadrant_position", "SEC_18"),
        ("Section: Single element", "SEC_19"),
        ("Section: Mixed chart+table+text", "SEC_16"),
        ("Section: Two tables stacked", "SEC_17"),
        ("property_sub_type: figures", "Full run"),
        ("property_sub_type: snapshot", "Full run (commentary excluded)"),
        ("property_sub_type: submarket", "Full run (commentary excluded)"),
    ]
    for feat, where in features:
        print(f"  [x] {feat:<45} ({where})")

    print()
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED - see errors above")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
