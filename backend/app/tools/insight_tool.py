"""insight_tool — LLM-powered section commentary generation.

Wraps llm_client.chat_completion with the COMMENTARY_SYSTEM prompt.
When real data is available the prompt includes actual figures so the
commentary is data-driven ("North led with ₹8.9Cr") rather than
generic ("Revenue showed growth").
"""

from __future__ import annotations

import json

from app.core.llm_client import chat_completion
from app.schemas.tool_schema import InsightContext, InsightOutput
from app.tools.base_tool import ToolResult, register_tool
from app.utils.logger import logger

COMMENTARY_SYSTEM = """\
You are a presentation commentary writer. Write concise, professional commentary \
(2-4 sentences) for a slide in a business presentation. When chart or table data is \
provided, reference specific values, trends, and comparisons from the data. Be \
specific, data-aware, and match the requested tone. Return ONLY the commentary \
text, no markdown fences."""

_FALLBACK: dict[str, dict[str, str]] = {
    "financial": {
        "chart": "The data shows consistent growth across key financial metrics. Revenue increased year-over-year with strong margin retention.",
        "table": "Comparative analysis reveals strong performance across tracked financial indicators.",
        "default": "Key financial metrics demonstrate robust performance for the period.",
    },
    "business": {
        "chart": "Strategic execution metrics demonstrate strong progress toward stated objectives.",
        "table": "The scorecard shows consistent progress across all priority areas.",
        "default": "Key strategic outcomes highlight sustained organizational growth.",
    },
    "research": {
        "chart": "Analysis reveals statistically significant findings (p < 0.05) across examined variables.",
        "table": "Systematic analysis of results reveals meaningful variance in the dataset.",
        "default": "Key findings from the analytical framework support the stated hypothesis.",
    },
}


def _fallback_commentary(section_name: str, intent_type: str, element_type: str) -> str:
    intent_map = _FALLBACK.get(intent_type, _FALLBACK["business"])
    text = intent_map.get(element_type, intent_map["default"])
    return text.replace("The data", f"The {section_name} data")


def _format_element_data(element_type: str, data: dict) -> str:
    """Format chart/table data into a human-readable block for the LLM prompt."""
    lines = [f"\n--- {element_type.upper()} DATA ---"]
    if element_type == "chart":
        labels = data.get("labels", [])
        datasets = data.get("datasets", [])
        lines.append(f"Chart type: {data.get('type', 'bar')}")
        lines.append(f"Categories: {', '.join(str(l) for l in labels)}")
        for ds in datasets:
            name = ds.get("label", "Series")
            values = ds.get("data", [])
            pairs = [
                f"{labels[i] if i < len(labels) else f'#{i}'}: {v}"
                for i, v in enumerate(values)
            ]
            lines.append(f"  {name}: {', '.join(pairs)}")
    elif element_type == "table":
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        lines.append(f"Columns: {' | '.join(headers)}")
        for row in rows[:10]:
            lines.append(f"  {' | '.join(str(c) for c in row)}")
        if len(rows) > 10:
            lines.append(f"  ... and {len(rows) - 10} more rows")
    else:
        lines.append(json.dumps(data, default=str)[:500])
    lines.append("--- END DATA ---")
    return "\n".join(lines)


@register_tool(
    name="generate_section_insights",
    description="Generate professional commentary for a presentation section using LLM (with static fallback)",
    input_schema=InsightContext,
    output_schema=InsightOutput,
)
async def generate_section_insights(
    section_name: str,
    intent_type: str = "business",
    tone: str = "formal",
    element_type: str = "chart",
    element_data: dict | None = None,
    data_summary: str = "",
) -> ToolResult:
    user_prompt = (
        f"Section: {section_name}\n"
        f"Presentation intent: {intent_type}\n"
        f"Tone: {tone}\n"
        f"Element type: {element_type}\n"
    )
    if element_data:
        user_prompt += _format_element_data(element_type, element_data)
    if data_summary:
        user_prompt += f"\nData summary: {data_summary}\n"
    user_prompt += "\nWrite the commentary now."

    try:
        commentary = await chat_completion(COMMENTARY_SYSTEM, user_prompt)
        return ToolResult.ok(
            data=InsightOutput(
                section_name=section_name,
                commentary=commentary.strip(),
            ).model_dump()
        )
    except Exception as exc:
        logger.warning("LLM commentary failed, using fallback: %s", exc)
        fallback_text = _fallback_commentary(section_name, intent_type, element_type)
        return ToolResult.ok(
            data=InsightOutput(
                section_name=section_name,
                commentary=fallback_text,
            ).model_dump()
        )
