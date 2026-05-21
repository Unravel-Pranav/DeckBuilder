"""intent_node — validate and enrich intent before the pipeline runs."""
from __future__ import annotations

from typing import Any


async def intent_node(state: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "planner_attempts": 0,
        "reviewer_score": 0,
        "reviewer_feedback": "",
        "available_templates": [],
        "recommendation_plan": [],
        "bound_sections": [],
        "errors": state.get("errors") or [],
        "steps_completed": [*(state.get("steps_completed") or []), "intent"],
    }

    if not state.get("objective"):
        updates["objective"] = "Present key findings clearly and support data-driven decisions"
    if not state.get("key_metrics"):
        updates["key_metrics"] = []
    if not state.get("audience_expertise"):
        updates["audience_expertise"] = "mixed"
    if not state.get("presentation_type"):
        updates["presentation_type"] = "business"
    if not state.get("audience"):
        updates["audience"] = "stakeholders"
    if not state.get("tone"):
        updates["tone"] = "formal"

    return updates
