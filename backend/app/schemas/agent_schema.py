"""Pydantic models for the V2 agent API — request, response, overrides, metrics."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.tool_schema import DataContract, PresentationStructure


# ---------------------------------------------------------------------------
# Data source configuration
# ---------------------------------------------------------------------------

class DataHints(BaseModel):
    """Optional user-provided hints about their data."""
    time_column: str | None = None
    value_columns: list[str] | None = None
    group_column: str | None = None
    date_format: str | None = None


class DataSourceConfig(BaseModel):
    source_type: Literal["csv_upload", "xlsx_upload", "report_id", "template_id", "inline_json"]
    file_id: str | None = None
    filename: str | None = None
    report_id: int | None = None
    template_id: int | None = None
    inline_data: list[dict[str, Any]] | None = None
    data_hints: DataHints | None = None

    @model_validator(mode="after")
    def _validate_source_fields(self) -> DataSourceConfig:
        if self.source_type in ("csv_upload", "xlsx_upload"):
            if not self.file_id:
                raise ValueError(f"file_id is required when source_type is '{self.source_type}'")
            if not self.filename:
                raise ValueError(f"filename is required when source_type is '{self.source_type}'")
        if self.source_type == "report_id" and self.report_id is None:
            raise ValueError("report_id is required when source_type is 'report_id'")
        if self.source_type == "template_id" and self.template_id is None:
            raise ValueError("template_id is required when source_type is 'template_id'")
        if self.source_type == "inline_json" and not self.inline_data:
            raise ValueError("inline_data is required when source_type is 'inline_json'")
        return self


# ---------------------------------------------------------------------------
# Deterministic overrides
# ---------------------------------------------------------------------------

class AgentOverrides(BaseModel):
    chart_type: str | None = None
    chart_layout: list[str | None] | None = None
    skip_insights: bool = False
    skip_viz: bool = False
    custom_sections: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

class StepMetric(BaseModel):
    step: str
    started_at: float
    ended_at: float | None = None
    duration_ms: float | None = None
    status: Literal["running", "success", "failed", "skipped"] = "running"
    error: str | None = None


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class AgentGenerateRequest(BaseModel):
    intent: str = Field(min_length=1)
    presentation_type: str = "financial"
    audience: str = "stakeholders"
    tone: str = "formal"
    mode: Literal["full", "structure_only", "ppt_only", "skeleton"] = "full"
    dry_run: bool = False
    data_source: DataSourceConfig | None = None
    overrides: AgentOverrides | None = None

    @model_validator(mode="after")
    def _validate_ppt_only_has_data_source(self) -> AgentGenerateRequest:
        if self.mode == "ppt_only" and self.data_source is None:
            raise ValueError(
                "ppt_only mode requires a 'data_source' — provide report_id, "
                "template_id, or uploaded file so the pipeline has data to render"
            )
        return self


class AgentGenerateResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    mode: str = "full"
    dry_run: bool = False
    structure: PresentationStructure | None = None
    ppt_download_url: str | None = None
    steps_completed: list[str] = []
    errors: list[dict[str, Any]] = []
    metrics: dict[str, StepMetric] = {}
    data_contracts: list[DataContract] | None = None
