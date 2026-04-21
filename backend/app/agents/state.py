"""AgentState — the TypedDict flowing through every LangGraph node."""

from __future__ import annotations

from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.agent_schema import AgentOverrides, DataSourceConfig, StepMetric
from app.schemas.tool_schema import DataContract, DataProfile, PresentationStructure


class AgentState(TypedDict, total=False):
    # ---- input context (set once at pipeline start) ----
    job_id: str
    intent: str
    presentation_type: str
    audience: str
    tone: str
    mode: str  # "full" | "structure_only" | "ppt_only" | "skeleton"
    dry_run: bool
    data_source: DataSourceConfig | None
    overrides: AgentOverrides | None

    # ---- infrastructure (managed by orchestrator) ----
    session_factory: async_sessionmaker[AsyncSession]
    errors: list[dict[str, Any]]  # [{"step": str, "message": str, "timestamp": float}]
    retry_counts: dict[str, int]  # keyed by step name
    metrics: dict[str, StepMetric]
    steps_completed: list[str]

    # ---- pipeline artifacts (set by individual nodes) ----
    data_profile: DataProfile | None
    structure: PresentationStructure | None
    sections_data: list[dict[str, Any]]
    data_mappings: list[dict[str, Any]]
    viz_mappings: list[dict[str, Any]]
    commentaries: dict[str, str]  # section_name -> commentary text
    ppt_result: dict[str, Any] | None
    data_contracts: list[DataContract] | None
