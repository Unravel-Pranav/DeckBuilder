"""insight_agent — generate commentary for each section.

When sections_data or data_mappings contain real values, the prompt
includes actual figures so commentary is data-driven rather than
generic.

NOTE: _build_data_summary truncates to 5 rows but does not limit
column width.  If Phase 6 wide-CSV tests blow the LLM token budget,
restrict the summary to only the mapped x_axis / y_axis / grouper
columns per row rather than the full row dict.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import RunnableConfig

from app.agents.state import AgentState
from app.tools.insight_tool import generate_section_insights
from app.utils.logger import logger


def _build_data_summary(section_data: dict[str, Any]) -> str:
    """Extract a compact text summary from a section's data for the LLM."""
    lines: list[str] = []
    data_slice = section_data.get("data_slice", [])
    if data_slice:
        lines.append(f"Data rows ({len(data_slice)} samples):")
        for row in data_slice[:5]:
            lines.append(f"  {row}")
    x_axis = section_data.get("x_axis")
    y_axis = section_data.get("y_axis", [])
    if x_axis:
        lines.append(f"X-axis: {x_axis}")
    if y_axis:
        lines.append(f"Y-axis: {', '.join(y_axis)}")
    return "\n".join(lines)


async def insight_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    structure = state.get("structure")
    if not structure:
        return {"commentaries": {}}

    sections = (
        structure.get("sections", [])
        if isinstance(structure, dict)
        else structure.sections
    )

    presentation_type = state.get("presentation_type", "business")
    tone = state.get("tone", "formal")
    sections_data = state.get("sections_data", [])
    data_mappings = state.get("data_mappings", [])

    commentaries: dict[str, str] = {}

    for idx, section in enumerate(sections):
        sec_dict = section if isinstance(section, dict) else section.model_dump()
        sec_name = sec_dict.get("name", f"Section {idx}")
        element_type = sec_dict.get("element_type", "chart")

        data_summary = ""
        if idx < len(data_mappings) and data_mappings[idx]:
            data_summary = _build_data_summary(data_mappings[idx])
        elif idx < len(sections_data) and sections_data[idx]:
            mapping = sections_data[idx]
            if isinstance(mapping, dict):
                data_summary = _build_data_summary(mapping)

        result = await generate_section_insights(
            section_name=sec_name,
            intent_type=presentation_type,
            tone=tone,
            element_type=element_type,
            data_summary=data_summary,
        )
        if result.success:
            commentaries[sec_name] = result.data["commentary"]
            logger.info("Insight [%d] %s: %d chars", idx, sec_name, len(result.data["commentary"]))
        else:
            commentaries[sec_name] = (
                f"Key findings for {sec_name} are detailed in the data above."
            )
            logger.warning("Insight [%d] %s: fallback — %s", idx, sec_name, result.error)

    logger.info("Insight: generated commentary for %d sections", len(commentaries))
    return {"commentaries": commentaries}
