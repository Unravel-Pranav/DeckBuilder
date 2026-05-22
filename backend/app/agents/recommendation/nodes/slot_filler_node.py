"""slot_filler_node — bind data columns to chart/table configs for each section slot."""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.paths import uploads_dir
from app.utils.logger import logger

_CHART_TYPE_TO_PPT: dict[str, str] = {
    "bar": "bar_chart",
    "bar_chart": "bar_chart",
    "grouped_bar": "bar_chart",
    "stacked_bar": "stacked_bar_chart",
    "stacked_bar_chart": "stacked_bar_chart",
    "horizontal_bar": "horizontal_bar_chart",
    "line": "line_chart",
    "line_chart": "line_chart",
    "multi_line": "multi_line_chart",
    "pie": "pie_chart",
    "pie_chart": "pie_chart",
    "combo": "combo_chart_singlebar_line",
    "area": "area_chart",
    "donut": "donut_chart",
    "donut_chart": "donut_chart",
    "table": "bar_chart",
}


def _load_df(data_source: dict[str, Any] | None) -> pd.DataFrame | None:
    if not data_source:
        return None
    src_type = data_source.get("source_type", "")
    try:
        if src_type in {"csv_upload", "xlsx_upload"}:
            file_id = data_source.get("file_id", "")
            filename = data_source.get("filename", "")
            if not file_id or not filename:
                return None
            path = uploads_dir() / file_id / filename
            if not path.exists():
                return None
            return pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path)
        if src_type == "inline_json":
            rows = data_source.get("inline_data") or []
            return pd.DataFrame(rows) if rows else None
    except Exception:  # noqa: BLE001
        return None
    return None


def _resolve_xy(df: pd.DataFrame, data_columns: list[str]) -> tuple[str, list[str]]:
    available = [c for c in data_columns if c in df.columns]
    if not available:
        available = df.columns.tolist()
    numeric_in = [c for c in available if pd.api.types.is_numeric_dtype(df[c])]
    non_numeric = [c for c in available if c not in numeric_in]
    x = non_numeric[0] if non_numeric else (available[0] if available else "")
    y = [c for c in numeric_in if c != x][:3] or [c for c in available if c != x][:1]
    return x, y


def _chart_rows(df: pd.DataFrame, x: str, y_list: list[str]) -> list[dict[str, Any]]:
    cols = [c for c in [x, *y_list] if c in df.columns]
    if not cols:
        return []
    return df[cols].head(25).to_dict(orient="records")


def _build_chart_element(
    idx: int, slot_order: int, section_name: str,
    df: pd.DataFrame, slot: dict[str, Any]
) -> dict[str, Any]:
    data_columns = slot.get("data_columns") or []
    chart_type_raw = slot.get("chart_type") or "bar_chart"
    chart_type_ppt = _CHART_TYPE_TO_PPT.get(chart_type_raw, "bar_chart")

    x_col, y_cols = _resolve_xy(df, data_columns)
    rows = _chart_rows(df, x_col, y_cols)

    return {
        "id": f"rec_elem_{idx}_{slot_order}",
        "element_type": "chart",
        "label": f"{section_name} — {chart_type_raw.replace('_', ' ').title()}",
        "selected": True,
        "display_order": slot_order,
        "slide_group": 0,
        "config": {
            "layout_category": "two_column",
            "chart_type": chart_type_ppt,
            "chart_data": rows,
            "chart_label": section_name,
            "chart_source": "",
            "axisConfig": {
                "xAxis": [{"key": x_col, "name": x_col}],
                "yAxis": [{"key": y, "name": y, "isPrimary": True} for y in y_cols]
                         or [{"key": "value", "name": "Value", "isPrimary": True}],
                "isMultiAxis": False,
            },
        },
    }


def _build_table_element(
    idx: int, slot_order: int, section_name: str,
    df: pd.DataFrame, slot: dict[str, Any]
) -> dict[str, Any]:
    data_columns = slot.get("data_columns") or []
    cols = [c for c in data_columns if c in df.columns] or df.columns.tolist()[:4]
    rows = df[cols].head(25).to_dict(orient="records")

    return {
        "id": f"rec_elem_{idx}_{slot_order}",
        "element_type": "table",
        "label": f"{section_name} — Table",
        "selected": True,
        "display_order": slot_order,
        "slide_group": 0,
        "config": {
            "layout_category": "two_column",
            "table_type": "table",
            "table_data": rows,
            "table_columns_sequence": cols,
        },
    }


def _build_commentary_element(
    idx: int, slot_order: int, section_name: str, slot: dict[str, Any]
) -> dict[str, Any]:
    directive = slot.get("insight_directive", "")
    text = directive if directive else f"{section_name}: key insights and analysis."

    return {
        "id": f"rec_elem_{idx}_{slot_order}",
        "element_type": "commentary",
        "label": f"{section_name} — Commentary",
        "selected": True,
        "display_order": slot_order,
        "slide_group": 0,
        "config": {
            "layout_category": "two_column",
            "commentary_text": text,
            "content": text,
            "section_alias": section_name,
        },
    }


async def slot_filler_node(state: dict[str, Any]) -> dict[str, Any]:
    plan = state.get("recommendation_plan") or []
    data_source = state.get("data_source")
    steps = [*(state.get("steps_completed") or []), "slot_filler"]

    df = _load_df(data_source)
    bound: list[dict[str, Any]] = []

    for idx, sec in enumerate(plan):
        name = sec.get("name", f"Section {idx + 1}")
        elements: list[dict[str, Any]] = []

        for slot in sec.get("slot_assignments", []):
            order = slot.get("slot_display_order", len(elements))
            etype = slot.get("element_type", "commentary")

            if etype == "chart" and df is not None:
                elements.append(_build_chart_element(idx, order, name, df, slot))
            elif etype == "table" and df is not None:
                elements.append(_build_table_element(idx, order, name, df, slot))
            else:
                elements.append(_build_commentary_element(idx, order, name, slot))

        if not elements:
            elements.append(_build_commentary_element(idx, 0, name, {"insight_directive": ""}))

        bound.append({
            "id": idx,
            "key": f"section_{idx}",
            "name": name,
            "description": sec.get("description", ""),
            "narrative_role": sec.get("narrative_role", "analysis"),
            "slide_structure": sec.get("slide_structure", "two-col"),
            "template_id": sec.get("template_id"),
            "sectionname_alias": name,
            "display_order": idx,
            "selected": True,
            "elements": elements,
        })

    logger.info("slot_filler_node: built %d bound sections", len(bound))
    return {"bound_sections": bound, "steps_completed": steps}
