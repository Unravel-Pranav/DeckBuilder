"""AiService — AI recommendations + context-aware commentary."""
from __future__ import annotations
import uuid
from app.schemas.ai_schema import (
    RecommendationRequest, AiRecommendationResponse, SectionRecommendationResponse,
    TemplateRecommendationResponse, CommentaryRequest,
)
from app.utils.logger import logger

SECTION_CONFIGS: dict[str, list[dict]] = {
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
        {"name": "Executive Summary", "desc": "Strategic overview", "templates": [{"name": "KPI Dashboard", "type": "chart-heavy", "layout": "chart-commentary"}]},
        {"name": "Strategy & Goals", "desc": "Objectives and progress", "templates": [{"name": "Goal Tracker", "type": "table-heavy", "layout": "table-commentary"}]},
        {"name": "Action Plan", "desc": "Next steps and timeline", "templates": [{"name": "Timeline View", "type": "mixed", "layout": "mixed"}]},
    ],
    "research": [
        {"name": "Introduction", "desc": "Research context", "templates": [{"name": "Research Overview", "type": "commentary", "layout": "commentary-only"}]},
        {"name": "Key Findings", "desc": "Primary results", "templates": [{"name": "Data Visualization", "type": "chart-heavy", "layout": "full-chart"}, {"name": "Results Table", "type": "table-heavy", "layout": "table-commentary"}]},
        {"name": "Conclusions", "desc": "Summary", "templates": [{"name": "Conclusion Narrative", "type": "commentary", "layout": "commentary-only"}]},
    ],
}
CHART_PREFS = {"financial": ["bar", "line", "pie"], "business": ["bar", "doughnut", "line"], "research": ["scatter", "line", "bar"]}
COMMENTARIES = {
    "financial": {"chart": "The data shows consistent growth. Revenue increased 23% YoY.", "table": "Comparative analysis reveals strong performance.", "default": "Key financial metrics demonstrate strong performance."},
    "business": {"chart": "Metrics demonstrate strong execution.", "table": "The scorecard shows progress across all priority areas.", "default": "Key strategic outcomes highlight growth."},
    "research": {"chart": "Findings show statistically significant results (p < 0.05).", "table": "Systematic analysis reveals significant variance.", "default": "Key findings from the analytical framework."},
}

class AiService:
    async def generate_recommendations(self, body: RecommendationRequest) -> AiRecommendationResponse:
        logger.info("AI recommendations: type=%s", body.type)
        raw = SECTION_CONFIGS.get(body.type, SECTION_CONFIGS["business"])
        sections = [
            SectionRecommendationResponse(id=str(uuid.uuid4()), name=s["name"], description=s["desc"],
                suggested_templates=[TemplateRecommendationResponse(id=str(uuid.uuid4()), name=t["name"], type=t["type"], layout=t["layout"], preview_description=f'{t["type"]} for {s["name"]}') for t in s["templates"]], accepted=True)
            for s in raw
        ]
        return AiRecommendationResponse(sections=sections, suggested_style="Professional with data-driven emphasis", suggested_chart_types=CHART_PREFS.get(body.type, ["bar", "pie"]))

    async def generate_commentary(self, body: CommentaryRequest) -> str:
        section = body.section_name or "this section"
        intent = body.intent_type or "business"
        if body.prompt:
            return f'Based on your direction — "{body.prompt[:80]}" — Analysis of {section} reveals actionable patterns.'
        intent_map = COMMENTARIES.get(intent, COMMENTARIES["business"])
        text = intent_map.get(body.component_type, intent_map["default"])
        return text.replace("The data", f"The {section} data").replace("Metrics", f"{section} metrics")
