"""AiService — real LLM-powered recommendations + commentary via NVIDIA NIM."""
from __future__ import annotations

import json
import uuid

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.ai_schema import (
    AiRecommendationResponse,
    CommentaryRequest,
    RecommendationRequest,
    SectionRecommendationResponse,
    TemplateRecommendationResponse,
)
from app.utils.logger import logger

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if not settings.nvidia_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
        )
    return _client


async def _chat(system: str, user: str) -> str:
    """Send a chat completion request to NVIDIA NIM."""
    client = _get_client()
    if client is None:
        raise RuntimeError("NVIDIA API key not configured")
    response = await client.chat.completions.create(
        model=settings.nvidia_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=settings.nvidia_temperature,
        max_tokens=settings.nvidia_max_tokens,
    )
    return response.choices[0].message.content or ""


SECTION_FALLBACK: dict[str, list[dict]] = {
    "financial": [
        {"name": "Executive Summary", "desc": "High-level overview of key findings", "templates": [
            {"name": "Key Metrics Dashboard", "type": "chart-heavy", "layout": "chart-commentary"},
            {"name": "Summary Table", "type": "table-heavy", "layout": "table-commentary"},
        ]},
        {"name": "Financial Analysis", "desc": "Revenue, costs, profitability", "templates": [
            {"name": "Revenue Breakdown", "type": "chart-heavy", "layout": "chart-commentary"},
            {"name": "P&L Summary", "type": "table-heavy", "layout": "full-table"},
        ]},
        {"name": "Market Overview", "desc": "Market landscape and positioning", "templates": [
            {"name": "Market Trend Lines", "type": "chart-heavy", "layout": "full-chart"},
            {"name": "Competitive Matrix", "type": "table-heavy", "layout": "table-commentary"},
        ]},
        {"name": "Key Insights", "desc": "Strategic recommendations", "templates": [
            {"name": "Insight Cards", "type": "mixed", "layout": "mixed"},
            {"name": "Action Items", "type": "commentary", "layout": "commentary-only"},
        ]},
    ],
    "business": [
        {"name": "Executive Summary", "desc": "Strategic overview", "templates": [
            {"name": "KPI Dashboard", "type": "chart-heavy", "layout": "chart-commentary"},
        ]},
        {"name": "Strategy & Goals", "desc": "Objectives and progress", "templates": [
            {"name": "Goal Tracker", "type": "table-heavy", "layout": "table-commentary"},
        ]},
        {"name": "Action Plan", "desc": "Next steps and timeline", "templates": [
            {"name": "Timeline View", "type": "mixed", "layout": "mixed"},
        ]},
    ],
    "research": [
        {"name": "Introduction", "desc": "Research context", "templates": [
            {"name": "Research Overview", "type": "commentary", "layout": "commentary-only"},
        ]},
        {"name": "Key Findings", "desc": "Primary results", "templates": [
            {"name": "Data Visualization", "type": "chart-heavy", "layout": "full-chart"},
            {"name": "Results Table", "type": "table-heavy", "layout": "table-commentary"},
        ]},
        {"name": "Conclusions", "desc": "Summary", "templates": [
            {"name": "Conclusion Narrative", "type": "commentary", "layout": "commentary-only"},
        ]},
    ],
}
CHART_PREFS = {
    "financial": ["bar", "line", "pie"],
    "business": ["bar", "doughnut", "line"],
    "research": ["scatter", "line", "bar"],
}


def _fallback_recommendations(body: RecommendationRequest) -> AiRecommendationResponse:
    raw = SECTION_FALLBACK.get(body.type, SECTION_FALLBACK["business"])
    sections = [
        SectionRecommendationResponse(
            id=str(uuid.uuid4()),
            name=s["name"],
            description=s["desc"],
            suggested_templates=[
                TemplateRecommendationResponse(
                    id=str(uuid.uuid4()),
                    name=t["name"],
                    type=t["type"],
                    layout=t["layout"],
                    preview_description=f'{t["type"]} for {s["name"]}',
                )
                for t in s["templates"]
            ],
            accepted=True,
        )
        for s in raw
    ]
    return AiRecommendationResponse(
        sections=sections,
        suggested_style="Professional with data-driven emphasis",
        suggested_chart_types=CHART_PREFS.get(body.type, ["bar", "pie"]),
    )


RECOMMENDATIONS_SYSTEM = """\
You are a presentation architecture AI. Given a presentation type, audience, and tone, \
return a JSON array of recommended sections. Each section object must have:
  "name": string, "description": string,
  "templates": [{"name": string, "type": one of "chart-heavy"|"table-heavy"|"commentary"|"mixed", \
"layout": one of "chart-commentary"|"table-commentary"|"full-chart"|"full-table"|"commentary-only"|"mixed"}]
Return ONLY valid JSON array, no markdown fences, no extra text."""

COMMENTARY_SYSTEM = """\
You are a presentation commentary writer. Write concise, professional commentary \
(2-4 sentences) for a slide in a business presentation. When chart or table data is \
provided, reference specific values, trends, and comparisons from the data. Be \
specific, data-aware, and match the requested tone. Return ONLY the commentary \
text, no markdown fences."""


class AiService:
    async def generate_recommendations(
        self, body: RecommendationRequest
    ) -> AiRecommendationResponse:
        logger.info("AI recommendations: type=%s, key_set=%s", body.type, bool(settings.nvidia_api_key))

        if not settings.nvidia_api_key:
            return _fallback_recommendations(body)

        try:
            user_prompt = (
                f"Presentation type: {body.type}\n"
                f"Audience: {body.audience or 'general business stakeholders'}\n"
                f"Tone: {body.tone or 'formal'}\n\n"
                "Suggest 3-5 sections with 1-2 template options each."
            )
            raw = await _chat(RECOMMENDATIONS_SYSTEM, user_prompt)

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            sections_data = json.loads(cleaned)
            sections = [
                SectionRecommendationResponse(
                    id=str(uuid.uuid4()),
                    name=s["name"],
                    description=s.get("description", ""),
                    suggested_templates=[
                        TemplateRecommendationResponse(
                            id=str(uuid.uuid4()),
                            name=t["name"],
                            type=t.get("type", "mixed"),
                            layout=t.get("layout", "mixed"),
                            preview_description=f'{t.get("type", "mixed")} for {s["name"]}',
                        )
                        for t in s.get("templates", [])
                    ],
                    accepted=True,
                )
                for s in sections_data
            ]
            return AiRecommendationResponse(
                sections=sections,
                suggested_style="AI-recommended professional layout",
                suggested_chart_types=CHART_PREFS.get(body.type, ["bar", "line"]),
            )
        except Exception as e:
            logger.warning("LLM recommendations failed, using fallback: %s", e)
            return _fallback_recommendations(body)

    async def generate_commentary(self, body: CommentaryRequest) -> str:
        section = body.section_name or "this section"
        logger.info(
            "AI commentary: section=%s, element_type=%s, has_data=%s, key_set=%s",
            section, body.element_type, body.element_data is not None, bool(settings.nvidia_api_key),
        )

        if not settings.nvidia_api_key:
            return self._fallback_commentary(body)

        try:
            tone_label = body.intent_tone or "formal"
            user_prompt = (
                f"Presentation: {body.presentation_name or 'Untitled'}\n"
                f"Section: {section}\n"
                f"Slide title: {body.slide_title or 'Untitled Slide'}\n"
                f"Slide component type: {body.component_type}\n"
                f"Presentation intent: {body.intent_type or 'business'}\n"
                f"Tone: {tone_label}\n"
            )

            if body.element_data:
                user_prompt += self._format_element_data(
                    body.element_type or body.component_type, body.element_data,
                )

            if body.prompt:
                user_prompt += f"User direction: {body.prompt}\n"
            user_prompt += "\nWrite the commentary now."

            return await _chat(COMMENTARY_SYSTEM, user_prompt)
        except Exception as e:
            logger.warning("LLM commentary failed, using fallback: %s", e)
            return self._fallback_commentary(body)

    @staticmethod
    def _format_element_data(element_type: str, data: dict) -> str:
        """Format chart/table data into a human-readable block for the LLM prompt."""
        lines = [f"\n--- {element_type.upper()} DATA ---\n"]
        if element_type == "chart":
            chart_type = data.get("type", "bar")
            labels = data.get("labels", [])
            datasets = data.get("datasets", [])
            lines.append(f"Chart type: {chart_type}")
            lines.append(f"Categories: {', '.join(str(l) for l in labels)}")
            for ds in datasets:
                name = ds.get("label", "Series")
                values = ds.get("data", [])
                pairs = [f"{labels[i] if i < len(labels) else f'#{i}'}: {v}" for i, v in enumerate(values)]
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
        lines.append("--- END DATA ---\n")
        return "\n".join(lines)

    def _fallback_commentary(self, body: CommentaryRequest) -> str:
        section = body.section_name or "this section"
        intent = body.intent_type or "business"
        fallback = {
            "financial": {
                "chart": f"The {section} data shows consistent growth. Revenue increased 23% YoY.",
                "table": f"Comparative analysis for {section} reveals strong performance.",
                "default": f"Key financial metrics for {section} demonstrate strong performance.",
            },
            "business": {
                "chart": f"{section} metrics demonstrate strong execution.",
                "table": f"The {section} scorecard shows progress across all priority areas.",
                "default": f"Key strategic outcomes for {section} highlight growth.",
            },
            "research": {
                "chart": f"{section} findings show statistically significant results (p < 0.05).",
                "table": f"Systematic analysis of {section} reveals significant variance.",
                "default": f"Key findings from {section} analytical framework.",
            },
        }
        intent_map = fallback.get(intent, fallback["business"])
        return intent_map.get(body.component_type, intent_map["default"])
