"""visualization_agent — select chart types for each section.

Override precedence:
  chart_layout[i]  >  chart_type (global)  >  AI recommendation
Bounds check: if chart_layout is shorter than the section list,
sections beyond the layout array fall through to chart_type or AI.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import RunnableConfig

from app.agents.state import AgentState
from app.schemas.tool_schema import DataProfile, DataShapeInput
from app.tools.viz_tool import recommend_chart_type
from app.utils.logger import logger


async def visualization_node(
    state: AgentState, config: RunnableConfig
) -> dict[str, Any]:
    structure = state.get("structure")
    if not structure:
        return {"viz_mappings": []}

    sections = (
        structure.get("sections", [])
        if isinstance(structure, dict)
        else structure.sections
    )

    overrides = state.get("overrides")
    global_chart = overrides.chart_type if overrides else None
    chart_layout = overrides.chart_layout if overrides else None

    data_profile_raw = state.get("data_profile")
    data_profile = None
    if data_profile_raw is not None:
        data_profile = (
            data_profile_raw
            if isinstance(data_profile_raw, DataProfile)
            else DataProfile(**data_profile_raw)
        )

    viz_mappings: list[dict[str, Any]] = []

    for idx, section in enumerate(sections):
        sec_dict = section if isinstance(section, dict) else section.model_dump()
        sec_name = sec_dict.get("name", f"Section {idx}")

        # --- Override precedence: chart_layout[i] > chart_type > AI ---
        per_slide = None
        if chart_layout and idx < len(chart_layout):
            per_slide = chart_layout[idx]

        if per_slide:
            viz_mappings.append({
                "section_index": idx,
                "chart_type": per_slide,
                "confidence": 1.0,
                "reasoning": "User override (chart_layout)",
                "source": "override_layout",
            })
            logger.info("Viz [%d] %s: chart_layout override → %s", idx, sec_name, per_slide)
            continue

        if global_chart:
            viz_mappings.append({
                "section_index": idx,
                "chart_type": global_chart,
                "confidence": 1.0,
                "reasoning": "User override (chart_type)",
                "source": "override_global",
            })
            logger.info("Viz [%d] %s: global chart_type override → %s", idx, sec_name, global_chart)
            continue

        # --- AI recommendation ---
        # NOTE: when no DataProfile exists, a generic DataShapeInput is used.
        # All non-profiled sections get identical shape assumptions; adjust
        # defaults here if Phase 6 testing shows unexpected recommendations.
        if data_profile:
            result = await recommend_chart_type(data_profile=data_profile)
        else:
            shape = DataShapeInput(
                column_count=2,
                row_count=10,
                has_temporal=False,
                has_categorical=True,
                numeric_columns=1,
                categorical_distinct_max=6,
            )
            result = await recommend_chart_type(data_shape=shape)

        if result.success:
            viz_mappings.append({
                "section_index": idx,
                **result.data,
                "source": "ai",
            })
            logger.info(
                "Viz [%d] %s: AI → %s (%.2f)",
                idx, sec_name, result.data["chart_type"], result.data["confidence"],
            )
        else:
            viz_mappings.append({
                "section_index": idx,
                "chart_type": "table",
                "confidence": 0.5,
                "reasoning": f"Fallback — viz failed: {result.error}",
                "source": "fallback",
            })
            logger.warning("Viz [%d] %s: fallback to table — %s", idx, sec_name, result.error)

    logger.info("Viz: completed %d section mappings", len(viz_mappings))
    return {"viz_mappings": viz_mappings}
