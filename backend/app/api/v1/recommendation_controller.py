"""Recommendation controller — LangGraph-powered intent-aware section planning."""
from __future__ import annotations

from fastapi import APIRouter

from app.agents.recommendation import (
    RecommendationAgentRequest,
    RecommendationAgentResponse,
    recommendation_graph,
)
from app.agents.recommendation.schemas import RecommendedSection, SlotAssignment
from app.schemas.response import success_response
from app.utils.logger import logger

router = APIRouter()


@router.post("/generate-plan")
async def generate_recommendation_plan(body: RecommendationAgentRequest):
    """
    Run the recommendation agent graph.

    Accepts enriched intent (objective, key_metrics, audience_expertise) plus
    an optional data_source. Returns template-bound sections with pre-built
    chart/table data and a reviewer confidence score.
    """
    initial_state = {
        "presentation_type": body.presentation_type,
        "audience": body.audience,
        "tone": body.tone,
        "objective": body.objective,
        "key_metrics": body.key_metrics,
        "audience_expertise": body.audience_expertise,
        "data_source": body.data_source,
        "planner_attempts": 0,
        "reviewer_score": 0,
        "reviewer_feedback": "",
        "errors": [],
        "steps_completed": [],
    }

    logger.info(
        "generate-plan: type=%s audience=%s objective=%s",
        body.presentation_type, body.audience, body.objective,
    )

    result = await recommendation_graph.ainvoke(initial_state)

    raw_plan = result.get("recommendation_plan", [])
    sections = []
    for sec in raw_plan:
        slot_objs = [
            SlotAssignment(**s) if isinstance(s, dict) else s
            for s in sec.get("slot_assignments", [])
        ]
        sections.append(
            RecommendedSection(
                name=sec.get("name", ""),
                description=sec.get("description", ""),
                narrative_role=sec.get("narrative_role", "analysis"),
                slide_structure=sec.get("slide_structure", "two-col"),
                template_id=sec.get("template_id"),
                slot_assignments=slot_objs,
            )
        )

    response = RecommendationAgentResponse(
        sections=sections,
        reviewer_score=result.get("reviewer_score", 0),
        reviewer_feedback=result.get("reviewer_feedback", ""),
        bound_sections=result.get("bound_sections", []),
        planner_attempts=result.get("planner_attempts", 1),
    )

    return success_response(response.model_dump())
