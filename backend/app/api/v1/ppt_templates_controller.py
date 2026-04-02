"""PPT Templates Controller — Expose backend .pptx templates via API (no DB required)."""

from __future__ import annotations

import os
from pathlib import Path
from fastapi import APIRouter

from app.ppt_engine.ppt_helpers_utils.services.ppt_template_registry import (
    is_registered_ppt_template,
)

router = APIRouter()

# Path to the individual_templates directory
# Controller is at: app/api/v1/ppt_templates_controller.py
# Templates at:     app/ppt_engine/ppt_helpers_utils/individual_templates/
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "ppt_engine" / "ppt_helpers_utils" / "individual_templates"


def _categorize_template(filename: str) -> dict:
    """Categorize a .pptx template file by its name."""
    stem = filename.replace(".pptx", "")
    name = stem.replace("_", " ").title()
    
    # Determine category
    if "first_slide" in stem:
        category = "front_page"
    elif "last_slide" in stem:
        category = "last_page"
    elif "base_clean" in stem or "snapshot_base" in stem:
        category = "base"
    elif "table" in stem:
        category = "table"
    elif "chart" in stem or "combo" in stem or "bar" in stem or "line" in stem or "pie" in stem or "donut" in stem or "stacked" in stem:
        category = "chart"
    else:
        category = "other"
    
    # Determine chart sub-type for chart templates
    chart_type = None
    if category == "chart":
        if "combo" in stem and "area" in stem:
            chart_type = "Combo - Area + Bar"
        elif "combo" in stem and "doublebar" in stem:
            chart_type = "Combo - Double Bar + Line"
        elif "combo" in stem and "singlebar" in stem:
            chart_type = "Combo - Single Bar + Line"
        elif "combo" in stem and "stacked" in stem:
            chart_type = "Combo - Stacked Bar + Line"
        elif "stacked_bar" in stem:
            chart_type = "Stacked bar"
        elif "horizontal_bar" in stem:
            chart_type = "Horizontal Bar"
        elif "bar_chart" in stem:
            chart_type = "Bar Chart"
        elif "multi_line" in stem:
            chart_type = "Line - Multi axis"
        elif "line_chart" in stem:
            chart_type = "Line - Single axis"
        elif "pie_chart" in stem:
            chart_type = "Pie Chart"
        elif "donut_chart" in stem:
            chart_type = "Donut Chart"
        elif "single_column_stacked" in stem.lower():
            chart_type = "Single Column Stacked Chart"
    
    # Determine table sub-type
    table_type = None
    if category == "table":
        if "market_stats_sub" in stem:
            table_type = "Market Stats (Sub)"
        elif "market_stats" in stem:
            table_type = "Market Stats"
        elif "industrial_figures" in stem:
            table_type = "Industrial Figures"
        else:
            table_type = "Generic Table"
    
    return {
        "filename": filename,
        "stem": stem,
        "name": name,
        "category": category,
        "chart_type": chart_type,
        "table_type": table_type,
        "size": 0,  # Will be populated
    }


@router.get("/")
async def list_ppt_templates():
    """
    List all available .pptx templates from the individual_templates directory.
    No database required — reads directly from the filesystem.
    """
    from app.schemas.response import success_response

    if not TEMPLATES_DIR.exists():
        return success_response({"templates": [], "count": 0, "directory": str(TEMPLATES_DIR)})

    templates = []
    for f in sorted(TEMPLATES_DIR.glob("*.pptx")):
        if not is_registered_ppt_template(f.name):
            continue
        info = _categorize_template(f.name)
        info["size"] = f.stat().st_size
        templates.append(info)

    # Group by category
    categories = {}
    for t in templates:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(t)

    return success_response({
        "templates": templates,
        "count": len(templates),
        "categories": categories,
        "directory": str(TEMPLATES_DIR),
    })


@router.get("/categories")
async def list_template_categories():
    """Return just the category summary."""
    from app.schemas.response import success_response

    if not TEMPLATES_DIR.exists():
        return success_response({"categories": {}})

    templates = []
    for f in sorted(TEMPLATES_DIR.glob("*.pptx")):
        if not is_registered_ppt_template(f.name):
            continue
        templates.append(_categorize_template(f.name))

    summary: dict = {}
    for t in templates:
        cat = t["category"]
        if cat not in summary:
            summary[cat] = {"count": 0, "templates": []}
        summary[cat]["count"] += 1
        summary[cat]["templates"].append(t["name"])

    return success_response({"categories": summary})
