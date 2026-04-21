"""structure_tool — LLM-powered presentation structure generation.

Wraps llm_client.chat_completion with the RECOMMENDATIONS_SYSTEM prompt.
Falls back to a static section template when the LLM is unreachable.
"""

from __future__ import annotations

import json
import uuid

from app.core.llm_client import chat_completion
from app.schemas.tool_schema import IntentInput, PresentationStructure, SectionDef
from app.tools.base_tool import ToolResult, register_tool
from app.utils.logger import logger

RECOMMENDATIONS_SYSTEM = """\
You are a presentation architecture AI. Given a presentation type, audience, and tone, \
return a JSON array of recommended sections. Each section object must have:
  "name": string, "description": string,
  "chart_type": one of "bar"|"line"|"pie"|"grouped_bar"|"stacked_bar"|"table"|null,
  "layout": one of "chart-commentary"|"table-commentary"|"full-chart"|"full-table"|"commentary-only"|"mixed",
  "element_type": one of "chart"|"table"|"commentary"
Return ONLY valid JSON array, no markdown fences, no extra text."""

SECTION_FALLBACK: dict[str, list[dict[str, str]]] = {
    "financial": [
        {"name": "Executive Summary", "description": "High-level overview", "chart_type": "bar", "layout": "chart-commentary", "element_type": "chart"},
        {"name": "Financial Analysis", "description": "Revenue, costs, profitability", "chart_type": "grouped_bar", "layout": "chart-commentary", "element_type": "chart"},
        {"name": "Market Overview", "description": "Market landscape", "chart_type": "line", "layout": "full-chart", "element_type": "chart"},
        {"name": "Key Insights", "description": "Strategic recommendations", "layout": "commentary-only", "element_type": "commentary"},
    ],
    "business": [
        {"name": "Executive Summary", "description": "Strategic overview", "chart_type": "bar", "layout": "chart-commentary", "element_type": "chart"},
        {"name": "Strategy & Goals", "description": "Objectives and progress", "layout": "table-commentary", "element_type": "table"},
        {"name": "Action Plan", "description": "Next steps and timeline", "layout": "mixed", "element_type": "chart"},
    ],
    "research": [
        {"name": "Introduction", "description": "Research context", "layout": "commentary-only", "element_type": "commentary"},
        {"name": "Key Findings", "description": "Primary results", "chart_type": "bar", "layout": "full-chart", "element_type": "chart"},
        {"name": "Conclusions", "description": "Summary and recommendations", "layout": "commentary-only", "element_type": "commentary"},
    ],
}


def _fallback_structure(presentation_type: str) -> PresentationStructure:
    raw = SECTION_FALLBACK.get(presentation_type, SECTION_FALLBACK["business"])
    sections = [
        SectionDef(
            name=s["name"],
            description=s.get("description", ""),
            chart_type=s.get("chart_type"),
            layout=s.get("layout", "chart-commentary"),
            element_type=s.get("element_type", "chart"),
        )
        for s in raw
    ]
    chart_types = [s.chart_type for s in sections if s.chart_type]
    return PresentationStructure(
        sections=sections,
        suggested_style="Professional with data-driven emphasis",
        suggested_chart_types=chart_types,
    )


def _clean_json(raw: str) -> str:
    """Strip markdown fences if the LLM wraps JSON in them."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    return cleaned


@register_tool(
    name="generate_structure",
    description="Generate a presentation section structure from intent using LLM (with static fallback)",
    input_schema=IntentInput,
    output_schema=PresentationStructure,
)
async def generate_structure(
    intent: str,
    presentation_type: str = "financial",
    audience: str = "stakeholders",
    tone: str = "formal",
    data_profile_summary: str = "",
) -> ToolResult:
    user_prompt = (
        f"Presentation type: {presentation_type}\n"
        f"Audience: {audience}\n"
        f"Tone: {tone}\n"
        f"Intent: {intent}\n"
    )
    if data_profile_summary:
        user_prompt += f"\nData available:\n{data_profile_summary}\n"
    user_prompt += "\nSuggest 3-5 sections with layout and chart type for each."

    try:
        raw = await chat_completion(RECOMMENDATIONS_SYSTEM, user_prompt)
        cleaned = _clean_json(raw)
        sections_data = json.loads(cleaned)

        sections = [
            SectionDef(
                name=s["name"],
                description=s.get("description", ""),
                chart_type=s.get("chart_type"),
                layout=s.get("layout", "chart-commentary"),
                element_type=s.get("element_type", "chart"),
            )
            for s in sections_data
        ]
        chart_types = list({s.chart_type for s in sections if s.chart_type})
        structure = PresentationStructure(
            sections=sections,
            suggested_style="AI-recommended professional layout",
            suggested_chart_types=chart_types,
        )
        return ToolResult.ok(data=structure.model_dump())

    except Exception as exc:
        logger.warning("LLM structure generation failed, using fallback: %s", exc)
        fallback = _fallback_structure(presentation_type)
        return ToolResult.ok(data=fallback.model_dump())
