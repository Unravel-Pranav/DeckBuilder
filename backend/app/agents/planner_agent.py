"""planner_agent — generate presentation structure from intent.

Includes DataProfile column metadata (not raw rows) in the LLM prompt
when available, so the planner can suggest sections tailored to the
actual data.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import RunnableConfig

from app.agents.state import AgentState
from app.tools.structure_tool import generate_structure
from app.utils.logger import logger


def _summarize_profile(data_profile: dict[str, Any]) -> str:
    """Build a compact text summary of DataProfile for the LLM prompt."""
    lines = [
        f"Rows: {data_profile['row_count']}, Columns: {data_profile['column_count']}",
        f"Pattern: {data_profile['data_patterns']['dominant_pattern']}",
        "Columns:",
    ]
    for col in data_profile.get("columns", []):
        lines.append(f"  - {col['name']} ({col['data_type']}, role={col['role']})")
    if data_profile.get("suggested_groupings"):
        lines.append("Suggested groupings:")
        for g in data_profile["suggested_groupings"]:
            lines.append(
                f"  - axis={g['axis']}, values={g['values']}, chart={g['recommended_chart']}"
            )
    return "\n".join(lines)


async def planner_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    intent = state.get("intent", "")
    presentation_type = state.get("presentation_type", "financial")
    audience = state.get("audience", "stakeholders")
    tone = state.get("tone", "formal")

    profile_summary = ""
    data_profile = state.get("data_profile")
    if data_profile:
        profile_summary = _summarize_profile(data_profile)
        logger.info("Planner: including data profile summary (%d chars)", len(profile_summary))

    result = await generate_structure(
        intent=intent,
        presentation_type=presentation_type,
        audience=audience,
        tone=tone,
        data_profile_summary=profile_summary,
    )
    if not result.success:
        raise RuntimeError(f"Structure generation failed: {result.error}")

    logger.info("Planner: generated %d sections", len(result.data.get("sections", [])))
    return {"structure": result.data}
