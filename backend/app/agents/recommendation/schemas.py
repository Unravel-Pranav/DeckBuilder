"""Pydantic schemas for the recommendation agent I/O."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RecommendationAgentRequest(BaseModel):
    presentation_type: str = "financial"
    audience: str = "stakeholders"
    tone: str = "formal"
    objective: str | None = None
    key_metrics: list[str] = Field(default_factory=list)
    audience_expertise: Literal["executive", "analyst", "mixed"] = "mixed"
    data_source: dict[str, Any] | None = None


class SlotAssignment(BaseModel):
    slot_display_order: int
    element_type: Literal["chart", "table", "commentary"]
    data_columns: list[str] = Field(default_factory=list)
    chart_type: str | None = None
    insight_directive: str = ""


class RecommendedSection(BaseModel):
    name: str
    description: str = ""
    narrative_role: Literal["hook", "analysis", "detail", "summary"] = "analysis"
    template_id: int | None = None
    slot_assignments: list[SlotAssignment] = Field(default_factory=list)


class RecommendationAgentResponse(BaseModel):
    sections: list[RecommendedSection]
    reviewer_score: int
    reviewer_feedback: str
    bound_sections: list[dict[str, Any]]
    planner_attempts: int
