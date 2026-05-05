"""Executable v2 agent pipeline orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from app.schemas.ai_schema import CommentaryRequest, RecommendationRequest
from app.schemas.agent_schema import AgentGenerateRequest
from app.schemas.tool_schema import DataProfile
from app.services.ai_service import AiService
from app.tools.ingest_tool import profile_data
from app.tools.ppt_tool import generate_ppt
from app.tools.viz_tool import recommend_chart_type

_CHART_TYPE_TO_PPT: dict[str, str] = {
    "bar": "bar_chart",
    "grouped_bar": "bar_chart",
    "stacked_bar": "stacked_bar_chart",
    "horizontal_bar": "horizontal_bar_chart",
    "line": "line_chart",
    "multi_line": "multi_line_chart",
    "pie": "pie_chart",
    "combo": "combo_chart_singlebar_line",
    "scatter": "bar_chart",
    "area": "area_chart",
    "donut": "donut_chart",
    "table": "bar_chart",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_uploaded_dataframe(file_id: str, filename: str) -> pd.DataFrame:
    path = Path(settings.upload_dir) / file_id / filename
    if not path.exists():
        raise FileNotFoundError(f"Uploaded file not found: {path}")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _resolve_xy(df: pd.DataFrame) -> tuple[str, list[str]]:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric_cols = [c for c in df.columns.tolist() if c not in numeric_cols]
    x_axis = non_numeric_cols[0] if non_numeric_cols else df.columns.tolist()[0]
    y_axis = [c for c in numeric_cols if c != x_axis][:3]
    if not y_axis:
        y_axis = [c for c in df.columns.tolist() if c != x_axis][:1]
    return x_axis, y_axis


def _rows_for_chart(df: pd.DataFrame, x_axis: str, y_axis: list[str]) -> list[dict[str, Any]]:
    cols = [c for c in [x_axis, *y_axis] if c in df.columns]
    if not cols:
        return []
    return df[cols].head(25).to_dict(orient="records")


def _pick_section_y_axis(section_name: str, numeric_cols: list[str], section_idx: int) -> list[str]:
    if not numeric_cols:
        return []
    name_tokens = {t for t in section_name.lower().replace("_", " ").split() if t}
    matched = [c for c in numeric_cols if any(tok in c.lower() for tok in name_tokens)]
    if matched:
        return matched[:2]
    offset = section_idx % len(numeric_cols)
    picked = [numeric_cols[offset]]
    if len(numeric_cols) > 1:
        picked.append(numeric_cols[(offset + 1) % len(numeric_cols)])
    return list(dict.fromkeys(picked))


def _chart_type_for_template(template_type: str, default_chart: str) -> str:
    if template_type == "table-heavy":
        return "table"
    if template_type == "commentary":
        return "none"
    return default_chart


def _section_commentary_fallback(section_name: str, chart_type: str) -> str:
    if chart_type == "table":
        return f"{section_name}: tabular comparison highlights differences across the selected metrics."
    if chart_type == "none":
        return f"{section_name}: this section provides narrative insights for the presentation intent."
    return f"{section_name}: chart uses {chart_type.replace('_', ' ')} based on profiled data."


async def run_agent_pipeline(req: AgentGenerateRequest) -> dict[str, Any]:
    started_at = _now_iso()
    steps_completed: list[str] = []
    metrics: dict[str, dict[str, Any]] = {}
    ai = AiService()

    if req.mode == "structure_only":
        rec = await ai.generate_recommendations(
            RecommendationRequest(
                type=req.presentation_type,
                audience=req.audience,
                tone=req.tone,
            )
        )
        return {
            "status": "completed",
            "steps_completed": ["planner"],
            "metrics": metrics,
            "structure": {
                "sections": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "template_type": (s.suggested_templates[0].type if s.suggested_templates else "mixed"),
                    }
                    for s in rec.sections
                ]
            },
            "errors": [],
            "started_at": started_at,
            "completed_at": _now_iso(),
        }

    if not req.data_source:
        raise RuntimeError("data_source is required for full/ppt_only modes")

    source = req.data_source
    if source.source_type not in {"csv_upload", "xlsx_upload", "inline_json"}:
        raise RuntimeError(f"Unsupported data_source for v2 pipeline: {source.source_type}")

    if source.source_type in {"csv_upload", "xlsx_upload"}:
        if not source.file_id or not source.filename:
            raise RuntimeError("file_id and filename are required for uploaded data_source")
        profile_res = await profile_data(file_id=source.file_id, filename=source.filename)
        if not profile_res.success:
            raise RuntimeError(profile_res.error or "profile_data failed")
        profile = DataProfile(**(profile_res.data or {}))
        df = _load_uploaded_dataframe(source.file_id, source.filename)
    else:
        rows = source.inline_data or []
        if not rows:
            raise RuntimeError("inline_json source requires non-empty inline_data")
        df = pd.DataFrame(rows)
        from app.tools.ingest_tool import _profile_dataframe  # noqa: PLC0415

        profile = _profile_dataframe(df)

    steps_completed.append("data_profile")
    x_axis, y_axis = _resolve_xy(df)
    numeric_cols = [c for c in df.select_dtypes(include="number").columns.tolist() if c != x_axis]

    chart_type = "bar"
    if req.overrides and req.overrides.chart_type:
        chart_type = req.overrides.chart_type
    elif not (req.overrides and req.overrides.skip_viz):
        viz_res = await recommend_chart_type(data_profile=profile, data_shape=None)
        if viz_res.success and viz_res.data:
            chart_type = (viz_res.data or {}).get("chart_type", "bar")
    steps_completed.append("visualization")
    llm_enabled = bool(settings.nvidia_api_key)
    rec = await ai.generate_recommendations(
        RecommendationRequest(
            type=req.presentation_type,
            audience=req.audience,
            tone=req.tone,
        )
    )
    steps_completed.append("planner")

    plan_sections = rec.sections[:6] if rec.sections else []
    if not plan_sections:
        plan_sections = []
    chart_layout_override = req.overrides.chart_layout if req.overrides and req.overrides.chart_layout else None

    sections: list[dict[str, Any]] = []
    viz_mappings: list[dict[str, Any]] = []
    for idx, sec in enumerate(plan_sections or []):
        name = sec.name or f"Section {idx + 1}"
        template_type = sec.suggested_templates[0].type if sec.suggested_templates else "mixed"
        section_y = _pick_section_y_axis(name, numeric_cols or y_axis, idx) or y_axis
        section_rows = _rows_for_chart(df, x_axis, section_y)
        current_chart = _chart_type_for_template(template_type, chart_type)
        if chart_layout_override and idx < len(chart_layout_override):
            current_chart = chart_layout_override[idx] or current_chart
        if req.overrides and req.overrides.chart_type:
            current_chart = req.overrides.chart_type

        viz_mappings.append(
            {
                "section": name,
                "template_type": template_type,
                "chart_type": current_chart,
                "y_axis": section_y,
            }
        )

        elements: list[dict[str, Any]] = []
        if current_chart == "table":
            table_cols = [c for c in [x_axis, *section_y] if c in df.columns]
            elements.append(
                {
                    "id": f"agent_elem_{idx}_0",
                    "element_type": "table",
                    "label": f"{name} — Table",
                    "selected": True,
                    "display_order": 0,
                    "slide_group": 0,
                    "config": {
                        "layout_category": "two_column",
                        "table_type": "table",
                        "table_data": section_rows,
                        "table_columns_sequence": table_cols,
                    },
                }
            )
        elif current_chart != "none":
            axis_y = [{"key": y, "name": y, "isPrimary": True} for y in section_y] or [
                {"key": "value", "name": "Value", "isPrimary": True}
            ]
            elements.append(
                {
                    "id": f"agent_elem_{idx}_0",
                    "element_type": "chart",
                    "label": f"{name} — {current_chart.replace('_', ' ').title()}",
                    "selected": True,
                    "display_order": 0,
                    "slide_group": 0,
                    "config": {
                        "layout_category": "two_column",
                        "chart_type": _CHART_TYPE_TO_PPT.get(current_chart, "bar_chart"),
                        "chart_data": section_rows,
                        "chart_label": name,
                        "chart_source": "",
                        "axisConfig": {
                            "xAxis": [{"key": x_axis, "name": x_axis}],
                            "yAxis": axis_y,
                            "isMultiAxis": False,
                        },
                    },
                }
            )

        if not (req.overrides and req.overrides.skip_insights):
            commentary_text = _section_commentary_fallback(name, current_chart)
            try:
                labels = [str(r.get(x_axis, "")) for r in section_rows]
                datasets = [{"label": y, "data": [r.get(y) for r in section_rows]} for y in section_y]
                element_type = "table" if current_chart == "table" else "chart"
                commentary_text = await ai.generate_commentary(
                    CommentaryRequest(
                        component_type=element_type,
                        section_name=name,
                        intent_type=req.presentation_type,
                        intent_tone=req.tone,
                        prompt=req.intent,
                        element_type=element_type,
                        element_data={
                            "type": current_chart,
                            "labels": labels,
                            "datasets": datasets,
                        },
                        presentation_name=req.intent,
                        slide_title=name,
                    )
                ) or commentary_text
            except Exception:  # noqa: BLE001
                pass
            elements.append(
                {
                    "id": f"agent_elem_{idx}_1",
                    "element_type": "commentary",
                    "label": f"{name} — Commentary",
                    "selected": True,
                    "display_order": 1,
                    "slide_group": 0,
                    "config": {
                        "layout_category": "two_column",
                        "commentary_text": commentary_text,
                        "content": commentary_text,
                        "section_alias": name,
                    },
                }
            )
        sections.append(
            {
                "id": idx,
                "key": f"section_{idx}",
                "name": name,
                "sectionname_alias": name,
                "display_order": idx,
                "selected": True,
                "elements": elements,
            }
        )

    if not sections:
        fallback_rows = _rows_for_chart(df, x_axis, y_axis)
        sections = [
            {
                "id": 0,
                "key": "section_0",
                "name": "Overview",
                "sectionname_alias": "Overview",
                "display_order": 0,
                "selected": True,
                "elements": [
                    {
                        "id": "agent_elem_0_0",
                        "element_type": "chart",
                        "label": "Overview — Chart",
                        "selected": True,
                        "display_order": 0,
                        "slide_group": 0,
                        "config": {
                            "layout_category": "two_column",
                            "chart_type": _CHART_TYPE_TO_PPT.get(chart_type, "bar_chart"),
                            "chart_data": fallback_rows,
                            "chart_label": "Overview",
                            "chart_source": "",
                            "axisConfig": {
                                "xAxis": [{"key": x_axis, "name": x_axis}],
                                "yAxis": [{"key": y, "name": y, "isPrimary": True} for y in y_axis] or [
                                    {"key": "value", "name": "Value", "isPrimary": True}
                                ],
                                "isMultiAxis": False,
                            },
                        },
                    }
                ],
            }
        ]

    if not (req.overrides and req.overrides.skip_insights):
        steps_completed.append("insight_generation")
    report = {
        "id": 0,
        "name": req.intent[:120],
        "property_type": req.presentation_type,
        "property_sub_type": "Figures",
        "quarter": "",
        "division": "",
        "publishing_group": "",
        "hero_fields": {},
        "template_id": None,
    }

    if req.dry_run:
        return {
            "status": "completed",
            "steps_completed": [*steps_completed, "dry_run"],
            "metrics": metrics,
            "errors": [],
            "structure": {"sections": [{"name": s["name"]} for s in sections]},
            "viz_mappings": viz_mappings,
            "started_at": started_at,
            "completed_at": _now_iso(),
        }

    ppt_res = await generate_ppt(session=None, report=report, sections=sections)
    if not ppt_res.success:
        raise RuntimeError(ppt_res.error or "generate_ppt failed")
    file_info = ppt_res.data or {}
    steps_completed.append("ppt_generation")

    return {
        "status": "completed",
        "steps_completed": steps_completed,
        "metrics": metrics,
        "errors": [],
        "ppt_file_id": file_info.get("file_id"),
        "ppt_file_path": file_info.get("file_path"),
        "ppt_filename": file_info.get("filename"),
        "ppt_download_url": None,  # set by controller with job context
        "profile_summary": {
            "rows": profile.row_count,
            "columns": profile.column_count,
            "dominant_pattern": profile.data_patterns.dominant_pattern,
        },
        "structure": {"sections": [{"name": s["name"]} for s in sections]},
        "viz_mappings": viz_mappings,
        "insights": {
            "llm_enabled": llm_enabled,
            "used_commentary": not (req.overrides and req.overrides.skip_insights),
        },
        "started_at": started_at,
        "completed_at": _now_iso(),
    }
