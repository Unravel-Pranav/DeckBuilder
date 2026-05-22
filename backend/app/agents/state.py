"""Shared state type for v2 agent pipeline."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    intent: str
    audience: str
    tone: str
    presentation_type: str
    mode: str
    dry_run: bool
    data_source: dict[str, Any] | None
    overrides: dict[str, Any] | None
    structure: dict[str, Any] | None
    sections_data: list[dict[str, Any]]
    viz_mappings: list[dict[str, Any]]
    commentaries: dict[str, str]
    data_profile: dict[str, Any] | None
    data_contracts: list[dict[str, Any]]
    ppt_result: dict[str, Any] | None
    errors: list[str]
    steps_completed: list[str]
    metrics: dict[str, dict[str, Any]]

    # ── Recommendation agent fields ──────────────────────────────────────────
    objective: str | None
    key_metrics: list[str]
    audience_expertise: str | None  # "executive" | "analyst" | "mixed"
    available_templates: list[dict[str, Any]]
    recommendation_plan: list[dict[str, Any]]
    reviewer_score: int
    reviewer_feedback: str
    planner_attempts: int
    bound_sections: list[dict[str, Any]]
