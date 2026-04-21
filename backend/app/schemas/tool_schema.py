"""Pydantic I/O models for every tool in app/tools/."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# data_tool I/O
# ---------------------------------------------------------------------------

class ReportDataOutput(BaseModel):
    report_id: int
    report_name: str
    property_type: str = "Office"
    property_sub_type: str = "Figures"
    quarter: str = ""
    division: str = ""
    sections: list[SectionData] = []


class SectionData(BaseModel):
    id: int
    key: str
    name: str
    sectionname_alias: str = ""
    display_order: int = 0
    selected: bool = True
    layout_preference: str | None = None
    elements: list[dict[str, Any]] = []


class TemplateSummary(BaseModel):
    id: int
    name: str
    description: str = ""
    property_type: str = ""


# ---------------------------------------------------------------------------
# viz_tool I/O
# ---------------------------------------------------------------------------

class DataShapeInput(BaseModel):
    """Abstract data shape for chart recommendation when no DataProfile exists."""
    column_count: int = 0
    row_count: int = 0
    has_temporal: bool = False
    has_categorical: bool = False
    numeric_columns: int = 0
    categorical_distinct_max: int = 0


class VizRecommendation(BaseModel):
    chart_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    fallback_chart_type: str = "table"


class LayoutMapping(BaseModel):
    section_index: int
    chart_type: str
    x_axis: str | None = None
    y_axis: list[str] = []
    grouper: str | None = None
    dual_axis: bool = False


# ---------------------------------------------------------------------------
# insight_tool I/O
# ---------------------------------------------------------------------------

class InsightContext(BaseModel):
    section_name: str
    intent_type: str = "business"
    tone: str = "formal"
    element_type: str = "chart"
    element_data: dict[str, Any] | None = None
    data_summary: str = ""


class InsightOutput(BaseModel):
    section_name: str
    commentary: str


# ---------------------------------------------------------------------------
# structure_tool I/O
# ---------------------------------------------------------------------------

class IntentInput(BaseModel):
    intent: str
    presentation_type: str = "financial"
    audience: str = "stakeholders"
    tone: str = "formal"
    data_profile_summary: str = ""


class SectionDef(BaseModel):
    name: str
    description: str = ""
    chart_type: str | None = None
    layout: str = "chart-commentary"
    element_type: str = "chart"


class PresentationStructure(BaseModel):
    sections: list[SectionDef] = []
    suggested_style: str = ""
    suggested_chart_types: list[str] = []


# ---------------------------------------------------------------------------
# ppt_tool I/O
# ---------------------------------------------------------------------------

class PptPayload(BaseModel):
    report: dict[str, Any]
    sections: list[dict[str, Any]]


class PptOutput(BaseModel):
    file_id: str
    filename: str
    file_path: str
    file_size: int = 0


# ---------------------------------------------------------------------------
# ingest_tool I/O — data profiling
# ---------------------------------------------------------------------------

class ColumnStats(BaseModel):
    min: float | str | None = None
    max: float | str | None = None
    mean: float | None = None
    median: float | None = None
    std_dev: float | None = None
    null_count: int = 0
    distinct_count: int = 0


class ColumnProfile(BaseModel):
    name: str
    data_type: Literal[
        "numeric", "categorical", "temporal", "text",
        "percentage", "boolean",
    ]
    role: Literal[
        "axis", "value", "grouper", "label", "identifier", "unknown",
    ] = "unknown"
    stats: ColumnStats | None = None
    null_ratio: float = 0.0
    sample_values: list[str] = Field(default_factory=list, max_length=5)


class DataGrouping(BaseModel):
    """A plausible (axis, grouper, value) combination detected from the data."""
    axis: str
    grouper: str | None = None
    values: list[str]
    recommended_chart: str
    confidence: float = Field(ge=0.0, le=1.0)


class DataPatterns(BaseModel):
    is_time_series: bool = False
    has_hierarchy: bool = False
    is_comparison: bool = False
    is_distribution: bool = False
    dominant_pattern: str = "unknown"


class DataProfile(BaseModel):
    """Output of ingest_tool.profile_data.

    Includes column metadata only (not raw rows) to stay within the
    ~2 000-token budget when sent to the LLM.  For CSVs with >15 columns
    the profiler truncates to the top 15 by relevance.
    """
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    suggested_groupings: list[DataGrouping] = []
    data_patterns: DataPatterns = Field(default_factory=DataPatterns)
    truncated: bool = False
    truncation_note: str = ""


class ParsedDataMeta(BaseModel):
    file_id: str
    filename: str
    row_count: int
    column_count: int
    columns: list[str]
    parse_warnings: list[str] = []


# ---------------------------------------------------------------------------
# mapping_tool I/O — column-to-chart binding
# ---------------------------------------------------------------------------

class FilterSpec(BaseModel):
    column: str
    operator: str = "eq"
    value: Any = None


class ChartDataMapping(BaseModel):
    section_index: int
    chart_type: str
    x_axis: str | None = None
    y_axis: list[str] = []
    grouper: str | None = None
    labels: str | None = None
    filters: list[FilterSpec] = []
    data_slice: list[dict[str, Any]] = []
    warnings: list[str] = []


class ColumnSpec(BaseModel):
    name: str
    expected_type: str
    role: str
    description: str = ""


class DataContract(BaseModel):
    """Describes what data a single slide/chart needs (skeleton mode output)."""
    slide_index: int
    chart_type: str
    required_columns: list[ColumnSpec] = []
    optional_columns: list[ColumnSpec] = []
    constraints: list[str] = []
    example_data: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Forward-ref rebuild (SectionData inside ReportDataOutput)
# ---------------------------------------------------------------------------

ReportDataOutput.model_rebuild()
