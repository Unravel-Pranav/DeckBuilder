"""Request/response schemas for v2 agent endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DataSourceConfig(BaseModel):
    source_type: Literal["csv_upload", "xlsx_upload", "report_id", "template_id", "inline_json"]
    file_id: str | None = None
    filename: str | None = None
    report_id: int | None = None
    template_id: int | None = None
    inline_data: list[dict[str, Any]] | None = None


class AgentOverrides(BaseModel):
    chart_type: str | None = None
    chart_layout: list[str] | None = None
    skip_insights: bool = False
    skip_viz: bool = False


class AgentGenerateRequest(BaseModel):
    intent: str
    presentation_type: str = "financial"
    audience: str = "stakeholders"
    tone: str = "formal"
    mode: Literal["full", "structure_only", "ppt_only", "skeleton"] = "full"
    dry_run: bool = False
    data_source: DataSourceConfig | None = None
    overrides: AgentOverrides | None = None


class AgentGenerateResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]


class AgentJobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] = Field(default_factory=dict)
    ppt_file_path: str | None = None
