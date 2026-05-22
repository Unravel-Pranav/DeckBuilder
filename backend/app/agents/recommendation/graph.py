"""LangGraph StateGraph for the recommendation agent."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.utils.logger import logger

from .nodes import (
    data_profile_node,
    intent_node,
    planner_node,
    reviewer_node,
    slot_filler_node,
    template_fetch_node,
)

_MAX_PLANNER_ATTEMPTS = 3
_MIN_REVIEWER_SCORE = 7


def _route_after_review(state: dict[str, Any]) -> str:
    from app.services.ai_service import _get_client  # noqa: PLC0415
    score = state.get("reviewer_score", 0)
    attempts = state.get("planner_attempts", 0)
    # If no LLM is available, retrying produces the same fallback — skip straight to slot_filler
    if not _get_client() or score >= _MIN_REVIEWER_SCORE or attempts >= _MAX_PLANNER_ATTEMPTS:
        return "slot_filler"
    logger.info("reviewer score=%d (attempt %d) — retrying planner", score, attempts)
    return "planner"


def build_graph() -> Any:
    g = StateGraph(AgentState)

    g.add_node("intent", intent_node)
    g.add_node("template_fetch", template_fetch_node)
    g.add_node("data_profile", data_profile_node)
    g.add_node("planner", planner_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("slot_filler", slot_filler_node)

    g.set_entry_point("intent")

    # Fan-out: intent → parallel fetch + profile
    g.add_edge("intent", "template_fetch")
    g.add_edge("intent", "data_profile")

    # Fan-in: both must finish before planner runs
    g.add_edge("template_fetch", "planner")
    g.add_edge("data_profile", "planner")

    g.add_edge("planner", "reviewer")

    g.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {"planner": "planner", "slot_filler": "slot_filler"},
    )

    g.add_edge("slot_filler", END)

    return g.compile()


recommendation_graph = build_graph()
