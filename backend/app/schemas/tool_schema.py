"""Schemas shared across v2 tools and agent pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    data_type: str
    role: str
    stats: ColumnStats | None = None
    null_ratio: float = 0.0
    sample_values: list[str] = Field(default_factory=list)


class DataGrouping(BaseModel):
    axis: str
    grouper: str | None = None
    values: list[str] = Field(default_factory=list)
    recommended_chart: str
    confidence: float = 0.0


class DataPatterns(BaseModel):
    is_time_series: bool = False
    has_hierarchy: bool = False
    is_comparison: bool = False
    is_distribution: bool = False
    dominant_pattern: str = "unknown"


class DataProfile(BaseModel):
    row_count: int
    column_count: int
    columns: list[ColumnProfile] = Field(default_factory=list)
    suggested_groupings: list[DataGrouping] = Field(default_factory=list)
    data_patterns: DataPatterns
    truncated: bool = False
    truncation_note: str = ""


class ParsedDataMeta(BaseModel):
    file_id: str
    filename: str
    row_count: int
    column_count: int
    columns: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)


class DataShapeInput(BaseModel):
    row_count: int
    column_count: int
    numeric_columns: int
    has_categorical: bool
    has_temporal: bool
    categorical_distinct_max: int = 0


class VizRecommendation(BaseModel):
    chart_type: str
    confidence: float
    reasoning: str
    fallback_chart_type: str | None = None


class DataContractColumn(BaseModel):
    name: str
    role: Literal["x_axis", "y_axis", "group", "label"] = "label"
    data_type: str | None = None


class DataContract(BaseModel):
    slide_index: int
    section_name: str = ""
    chart_type: str = "bar"
    required_columns: list[DataContractColumn] = Field(default_factory=list)
    example_data: list[dict[str, Any]] = Field(default_factory=list)
