"""
Which .pptx files under individual_templates/ are addressable by the PPT engine.

Must stay aligned with:
- chart_type_mapping / table_type resolution in frontend_json_processor.py
- _TEMPLATE_CONFIGS in template_config.py
- table_type strings passed through to template filenames (e.g. market_stats_table)
"""

from __future__ import annotations

from pathlib import Path
from typing import FrozenSet

from app.ppt_engine.ppt_helpers_utils.services.template_config import _TEMPLATE_CONFIGS


def _template_set_stems() -> set[str]:
    stems: set[str] = set()
    for ts in _TEMPLATE_CONFIGS.values():
        if ts.first_slide:
            stems.add(Path(ts.first_slide).stem)
        stems.add(Path(ts.base_slide).stem)
        if ts.last_slide:
            stems.add(Path(ts.last_slide).stem)
    return stems


# Unique .pptx stems from FrontendJSONProcessor.chart_type_mapping values
_CHART_ENGINE_STEMS: FrozenSet[str] = frozenset(
    {
        "line_chart",
        "multi_line_chart",
        "bar_chart",
        "horizontal_bar_chart",
        "stacked_bar_chart",
        "combo_chart_singlebar_line",
        "combo_chart_doublebar_line",
        "combo_chart_stackedbar_line",
        "combo_chart _area_bar",
        "pie_chart",
        "donut_chart",
        "Single_column_stacked_chart",
    }
)

# table_type_mapping values + passthrough types used in production JSON
_TABLE_ENGINE_STEMS: FrozenSet[str] = frozenset(
    {
        "table",
        "market_stats_table",
        "market_stats_sub_table",
        "industrial_figures_template",
    }
)


def _collect_registered_template_stems() -> FrozenSet[str]:
    stems: set[str] = set()
    stems.update(_CHART_ENGINE_STEMS)
    stems.update(_TABLE_ENGINE_STEMS)
    stems.update(_template_set_stems())
    return frozenset(stems)


REGISTERED_PPT_TEMPLATE_STEMS: FrozenSet[str] = _collect_registered_template_stems()


def is_registered_ppt_template(filename: str) -> bool:
    """True if this .pptx name is part of the engine registry."""
    stem = Path(filename).stem
    return stem in REGISTERED_PPT_TEMPLATE_STEMS
