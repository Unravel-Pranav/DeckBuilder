"""ppt_agent — assemble the PPT payload and generate the file.

Normal path:  builds the {"report": {...}, "sections": [...]} JSON shape
              that pptx_builder expects from structure + data + viz + commentary.
Skeleton path: skeleton_payload_builder uses DataContracts with example_data
              and a chart_type mapping to produce the same shape.
"""

from __future__ import annotations

import re
from typing import Any

from langgraph.types import RunnableConfig

from app.agents.state import AgentState
from app.schemas.tool_schema import DataContract
from app.tools.ppt_tool import generate_ppt
from app.utils.logger import logger

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
    # viz_tool can also emit these — map to nearest chart template
    "kpi_card": "bar_chart",
    "table": "bar_chart",
}

# Viz outputs that should redirect the section to render as a table instead
# of forcing a chart that has no useful data shape.
_VIZ_TYPES_FORCING_TABLE = {"table"}

# Single-series → multi-series upgrade map. Applied when y_axis has >1 column
# so we never silently render only the first series.
_MULTI_SERIES_UPGRADE: dict[str, str] = {
    "bar": "grouped_bar",
    "line": "multi_line",
    "area": "multi_line",
}


# ---------------------------------------------------------------------------
# Section-name driven y-axis filtering
# ---------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    """Extract lowercase word tokens for case-insensitive matching."""
    return {t for t in re.split(r"[^a-zA-Z0-9]+", (text or "").lower()) if t}


def _filter_y_by_section_name(
    section_name: str, all_y: list[str]
) -> list[str]:
    """Pick y-columns whose names appear in the section title.

    If the section title mentions specific metric names (e.g.
    "Nifty 50 vs Gold and Silver Prices"), restrict the y-axis to
    those columns. Falls back to all y-columns if no match is found,
    so we never render an empty chart.
    """
    if not section_name or not all_y:
        return all_y

    title_tokens = _tokens(section_name)
    if not title_tokens:
        return all_y

    matched: list[str] = []
    for col in all_y:
        col_tokens = _tokens(col)
        if col_tokens & title_tokens:
            matched.append(col)

    return matched or all_y


# We drive the engine through its "frontend-layout fast-path"
# (``slide_number_assigner._assign_with_frontend_layout``) by stamping every
# element's ``config`` with a ``layout_category`` and a ``slide_group``.  When
# any element carries a ``layout_category``, the engine bypasses the
# height-based packing heuristics and respects our grouping verbatim:
#
#   * elements that share a ``slide_group`` land on the same slide
#   * ``layout_category="two_column"`` / ``"grid"``  → backend ``grid_2x2``
#     (chart/table on one half, commentary on the other)
#   * ``layout_category="full_width"``               → backend ``full_width``
#     (single element fills the slide)
#
# Different sections automatically get different slides because the outer
# section loop advances the slide pointer between calls.  This sidesteps both
# of the bugs we were fighting:
#   - "full_width" mode used to push chart and commentary onto separate slides
#     because their combined virtual height exceeded the slide
#   - "grid_2x2" mode used to merge two unrelated sibling sections into one
#     four-cell slide with a misleading title from only the first section


def _pick_layout_category(element_type: str, num_elements: int) -> str:
    """Pick the per-element ``layout_category`` for the engine fast-path.

    A section with more than one element (typically chart+commentary or
    table+commentary) goes side-by-side via ``two_column`` (mapped to
    ``grid_2x2``).  Single-element sections take the whole slide via
    ``full_width``.
    """
    if num_elements > 1:
        return "two_column"
    if element_type in ("chart", "table"):
        return "full_width"
    return "full_width"


# ---------------------------------------------------------------------------
# Skeleton payload builder
# ---------------------------------------------------------------------------


def _build_skeleton_payload(
    contracts: list[dict[str, Any]],
    intent: str,
    presentation_type: str,
) -> dict[str, Any]:
    """Build a PPT-engine-compatible payload from DataContracts.

    Maps contract.chart_type to the PPT engine's expected strings via
    _CHART_TYPE_TO_PPT.  "table" and "kpi_card" are handled as separate
    element_type values — they never go through the chart mapping.
    """
    sections: list[dict[str, Any]] = []

    for contract_dict in contracts:
        contract = (
            contract_dict
            if isinstance(contract_dict, DataContract)
            else DataContract(**contract_dict)
        )
        idx = contract.slide_index
        chart_type = contract.chart_type

        element_id = f"agent_elem_{idx}_0"

        if chart_type == "table":
            element = {
                "id": element_id,
                "element_type": "table",
                "label": f"Section {idx + 1} — Table [Sample Data]",
                "selected": True,
                "display_order": 0,
                "config": {
                    "table_type": "table",
                    "table_data": contract.example_data,
                    "table_columns_sequence": (
                        list(contract.example_data[0].keys())
                        if contract.example_data
                        else []
                    ),
                },
            }
        elif chart_type == "kpi_card":
            kpi_value = ""
            if contract.example_data:
                first_row = contract.example_data[0]
                numeric_vals = [v for v in first_row.values() if isinstance(v, (int, float))]
                kpi_value = str(numeric_vals[0]) if numeric_vals else str(next(iter(first_row.values()), ""))
            element = {
                "id": element_id,
                "element_type": "commentary",
                "label": f"Section {idx + 1} — KPI [Sample Data]",
                "selected": True,
                "display_order": 0,
                "config": {
                    "commentary_text": f"Sample KPI: {kpi_value}" if kpi_value else "Sample KPI",
                    "content": f"Sample KPI: {kpi_value}" if kpi_value else "Sample KPI",
                    "section_alias": f"Section {idx + 1}",
                },
            }
        elif chart_type == "none":
            element = {
                "id": element_id,
                "element_type": "commentary",
                "label": f"Section {idx + 1} — Commentary",
                "selected": True,
                "display_order": 0,
                "config": {
                    "commentary_text": "Commentary-only slide — no data required.",
                    "content": "Commentary-only slide — no data required.",
                    "section_alias": f"Section {idx + 1}",
                },
            }
        else:
            ppt_chart_type = _CHART_TYPE_TO_PPT.get(chart_type, "bar")
            readable_label = chart_type.replace("_", " ").title()
            x_key = "Category"
            y_keys: list[dict[str, Any]] = []

            if contract.required_columns:
                x_col = next(
                    (c for c in contract.required_columns if c.role == "x_axis"),
                    None,
                )
                if x_col:
                    x_key = x_col.name
                y_cols = [c for c in contract.required_columns if c.role == "y_axis"]
                y_keys = [
                    {"key": c.name, "name": c.name, "isPrimary": True}
                    for c in y_cols
                ]

            if not y_keys and contract.example_data:
                numeric_keys = [
                    k for k, v in contract.example_data[0].items()
                    if isinstance(v, (int, float)) and k != x_key
                ]
                y_keys = [
                    {"key": k, "name": k, "isPrimary": True}
                    for k in numeric_keys
                ]

            element = {
                "id": element_id,
                "element_type": "chart",
                "label": f"Section {idx + 1} — {readable_label} [Sample Data]",
                "selected": True,
                "display_order": 0,
                "config": {
                    "chart_type": ppt_chart_type,
                    "chart_data": contract.example_data,
                    "chart_label": f"{readable_label} [Sample Data]",
                    "chart_source": "",
                    "axisConfig": {
                        "xAxis": [{"key": x_key, "name": x_key}],
                        "yAxis": y_keys or [{"key": "value", "name": "Value", "isPrimary": True}],
                        "isMultiAxis": False,
                    },
                },
            }

        section_name = f"Section {idx + 1}"
        layout_category = _pick_layout_category(element["element_type"], 1)
        element["config"]["layout_category"] = layout_category
        element["slide_group"] = 0
        sections.append({
            "id": idx,
            "key": f"section_{idx}",
            "name": section_name,
            "sectionname_alias": section_name,
            "display_order": idx,
            "selected": True,
            "elements": [element],
        })

    return {
        "report": {
            "id": 0,
            "name": f"Skeleton — {intent[:60]}",
            "property_type": presentation_type,
            "property_sub_type": "Figures",
            "quarter": "",
            "division": "",
            "publishing_group": "",
            "hero_fields": {},
            "template_id": None,
        },
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Normal payload builder
# ---------------------------------------------------------------------------


def _build_normal_payload(state: AgentState) -> dict[str, Any]:
    """Assemble the PPT payload from structure + data + viz + commentary."""
    structure = state.get("structure", {})
    sections_data = state.get("sections_data", [])
    viz_mappings = state.get("viz_mappings", [])
    commentaries = state.get("commentaries", {})

    raw_sections = (
        structure.get("sections", [])
        if isinstance(structure, dict)
        else structure.sections
    )

    pipeline_sections: list[dict[str, Any]] = []

    for idx, section in enumerate(raw_sections):
        sec_dict = section if isinstance(section, dict) else section.model_dump()
        sec_name = sec_dict.get("name", f"Section {idx + 1}")
        element_type = sec_dict.get("element_type", "chart")

        viz = viz_mappings[idx] if idx < len(viz_mappings) else {}
        chart_type = viz.get("chart_type", sec_dict.get("chart_type", "bar"))

        data = sections_data[idx] if idx < len(sections_data) else {}
        data_dict = data if isinstance(data, dict) else {}
        commentary = commentaries.get(sec_name, "")

        # --- Resolve x and y from the data mapping, then filter by section name ---
        x_axis = data_dict.get("x_axis") or "Category"
        all_y: list[str] = list(data_dict.get("y_axis") or [])
        y_axis = _filter_y_by_section_name(sec_name, all_y)

        # If viz couldn't pick a chart and fell back to "table" but the
        # planner asked for a chart, render as table instead of forcing a
        # broken chart. Honors viz's expert recommendation.
        if (
            element_type == "chart"
            and chart_type in _VIZ_TYPES_FORCING_TABLE
            and y_axis
        ):
            logger.info(
                "PPT [%d] %s: viz returned 'table' — rendering as table instead of chart",
                idx, sec_name,
            )
            element_type = "table"

        # When multiple y-columns are bound, upgrade single-series charts so we
        # don't silently render only the first column.
        if len(y_axis) > 1 and chart_type in _MULTI_SERIES_UPGRADE:
            upgraded = _MULTI_SERIES_UPGRADE[chart_type]
            logger.info(
                "PPT [%d] %s: upgraded chart_type %s → %s for %d y-cols",
                idx, sec_name, chart_type, upgraded, len(y_axis),
            )
            chart_type = upgraded

        ppt_chart_type = _CHART_TYPE_TO_PPT.get(chart_type, "bar_chart")

        # --- Slice data to only the relevant columns ---
        full_slice = data_dict.get("data_slice") or []
        kept_cols = [c for c in [x_axis, *y_axis] if c]
        if full_slice and kept_cols:
            data_slice = [
                {c: row[c] for c in kept_cols if c in row}
                for row in full_slice
            ]
        else:
            data_slice = full_slice

        elements: list[dict[str, Any]] = []

        if element_type == "commentary":
            elements.append({
                "id": f"agent_elem_{idx}_0",
                "element_type": "commentary",
                "label": f"{sec_name} — Commentary",
                "selected": True,
                "display_order": 0,
                "config": {
                    "commentary_text": commentary,
                    "content": commentary,
                    "section_alias": sec_name,
                },
            })
        elif element_type == "table":
            # Always lead with the categorical/temporal axis column so tables
            # are readable. Falls back to whatever keys the slice has.
            if data_slice:
                first_row_keys = list(data_slice[0].keys())
                table_columns = [c for c in [x_axis, *y_axis] if c in first_row_keys]
                if not table_columns:
                    table_columns = first_row_keys
            else:
                table_columns = [c for c in [x_axis, *y_axis] if c]

            elements.append({
                "id": f"agent_elem_{idx}_0",
                "element_type": "table",
                "label": f"{sec_name} — Table",
                "selected": True,
                "display_order": 0,
                "config": {
                    "table_type": "table",
                    "table_data": data_slice,
                    "table_columns_sequence": table_columns,
                },
            })
            if commentary:
                elements.append({
                    "id": f"agent_elem_{idx}_1",
                    "element_type": "commentary",
                    "label": f"{sec_name} — Commentary",
                    "selected": True,
                    "display_order": 1,
                    "config": {
                        "commentary_text": commentary,
                        "content": commentary,
                        "section_alias": sec_name,
                    },
                })
        else:
            y_keys = [
                {"key": y, "name": y, "isPrimary": True}
                for y in y_axis
            ] if y_axis else [{"key": "value", "name": "Value", "isPrimary": True}]

            elements.append({
                "id": f"agent_elem_{idx}_0",
                "element_type": "chart",
                "label": f"{sec_name} — {chart_type.replace('_', ' ').title()}",
                "selected": True,
                "display_order": 0,
                "config": {
                    "chart_type": ppt_chart_type,
                    "chart_data": data_slice,
                    "chart_label": sec_name,
                    "chart_source": "",
                    "axisConfig": {
                        "xAxis": [{"key": x_axis, "name": x_axis}],
                        "yAxis": y_keys,
                        "isMultiAxis": False,
                    },
                },
            })
            if commentary:
                elements.append({
                    "id": f"agent_elem_{idx}_1",
                    "element_type": "commentary",
                    "label": f"{sec_name} — Commentary",
                    "selected": True,
                    "display_order": 1,
                    "config": {
                        "commentary_text": commentary,
                        "content": commentary,
                        "section_alias": sec_name,
                    },
                })

        layout_category = _pick_layout_category(element_type, len(elements))
        for elem in elements:
            elem.setdefault("config", {})["layout_category"] = layout_category
            elem["slide_group"] = 0

        pipeline_sections.append({
            "id": idx,
            "key": f"section_{idx}",
            "name": sec_name,
            "sectionname_alias": sec_name,
            "display_order": idx,
            "selected": True,
            "elements": elements,
        })

    intent = state.get("intent", "Untitled")
    presentation_type = state.get("presentation_type", "Office")

    return {
        "report": {
            "id": 0,
            "name": intent[:120],
            "property_type": presentation_type,
            "property_sub_type": "Figures",
            "quarter": "",
            "division": "",
            "publishing_group": "",
            "hero_fields": _build_hero_fields(state),
            "template_id": None,
        },
        "sections": pipeline_sections,
    }


# ---------------------------------------------------------------------------
# Cover slide stats
# ---------------------------------------------------------------------------

# Template hero-field slots (slide_1) — keyed in order. The labels are
# rewritten per-deck from the actual data, so the key names themselves don't
# leak into the rendered slide.
_HERO_SLOTS = [
    "vacancy_rate",
    "sf_net_absorption",
    "sf_construction_delivered",
    "sf_under_construction",
    "lease_rate",
]


def _format_kpi_value(value: float) -> str:
    """Compact, human-friendly formatting for a numeric KPI."""
    abs_v = abs(value)
    if abs_v >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_v >= 1_000:
        return f"{value / 1_000:.1f}K"
    if abs_v >= 100:
        return f"{value:,.0f}"
    if abs_v >= 1:
        return f"{value:,.2f}"
    return f"{value:.3f}"


def _build_hero_fields(state: AgentState) -> dict[str, Any]:
    """Build hero_fields.stats from the data profile + ingested file.

    Picks up to 5 numeric columns and emits {label, value, trend} for each.
    Labels override the static template text ("Vacancy Rate" etc.) so the
    cover slide reflects the actual data instead of CBRE real-estate defaults.
    """
    profile_raw = state.get("data_profile")
    if not profile_raw:
        return {}

    profile = profile_raw if isinstance(profile_raw, dict) else profile_raw.model_dump()

    numeric_cols = [
        c for c in profile.get("columns", [])
        if c.get("data_type") in ("numeric", "percentage")
    ]
    if not numeric_cols:
        return {}

    data_source = state.get("data_source")
    last_row: dict[str, Any] | None = None
    prev_row: dict[str, Any] | None = None

    if data_source and getattr(data_source, "file_id", None):
        try:
            from pathlib import Path

            import pandas as pd

            from app.core.config import settings

            path = Path(settings.upload_dir) / data_source.file_id / data_source.filename
            if path.exists():
                df = (
                    pd.read_csv(path) if path.suffix.lower() == ".csv"
                    else pd.read_excel(path)
                )
                if len(df) > 0:
                    last_row = df.iloc[-1].to_dict()
                if len(df) > 1:
                    prev_row = df.iloc[-2].to_dict()
        except Exception:  # noqa: BLE001 — best-effort enrichment
            logger.debug("Could not load source for hero stats", exc_info=True)

    stats: dict[str, dict[str, Any]] = {}
    for slot, col in zip(_HERO_SLOTS, numeric_cols[: len(_HERO_SLOTS)]):
        col_name = col.get("name", "Metric")
        label = col_name.replace("_", " ").title()

        value_str = "—"
        trend = "neutral"

        if last_row is not None and col_name in last_row:
            try:
                latest = float(last_row[col_name])
                value_str = _format_kpi_value(latest)
                if col.get("data_type") == "percentage":
                    value_str = f"{value_str}%"
                if prev_row is not None and col_name in prev_row:
                    prev = float(prev_row[col_name])
                    if latest > prev:
                        trend = "up"
                    elif latest < prev:
                        trend = "down"
            except (TypeError, ValueError):
                pass
        elif col.get("stats", {}).get("mean") is not None:
            value_str = _format_kpi_value(float(col["stats"]["mean"]))

        stats[slot] = {"label": label, "value": value_str, "trend": trend}

    return {"stats": stats} if stats else {}


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


async def ppt_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    mode = state.get("mode", "full")
    dry_run = state.get("dry_run", False)

    if dry_run:
        logger.info("PPT: dry_run=True — skipping actual generation")
        return {"ppt_result": {"dry_run": True}}

    # --- Skeleton path ---
    if mode == "skeleton":
        contracts = state.get("data_contracts", [])
        if not contracts:
            raise RuntimeError("Skeleton mode requires data_contracts but none found in state")

        payload = _build_skeleton_payload(
            contracts=contracts,
            intent=state.get("intent", "Skeleton"),
            presentation_type=state.get("presentation_type", "financial"),
        )
        logger.info("PPT: skeleton payload built with %d sections", len(payload["sections"]))
    else:
        payload = _build_normal_payload(state)
        logger.info("PPT: normal payload built with %d sections", len(payload["sections"]))

    session_factory = state.get("session_factory")
    if session_factory is None:
        raise RuntimeError("session_factory required for PPT generation but not found in state")

    async with session_factory() as session:
        result = await generate_ppt(
            session=session,
            report=payload["report"],
            sections=payload["sections"],
        )

    if not result.success:
        raise RuntimeError(f"PPT generation failed: {result.error}")

    logger.info("PPT: generated %s (%d bytes)", result.data["filename"], result.data.get("file_size", 0))
    return {"ppt_result": result.data}
