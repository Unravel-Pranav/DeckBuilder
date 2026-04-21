"""ingest_tool — CSV/Excel parsing + automatic data profiling.

parse_file:   reads the uploaded file, returns metadata (ParsedDataMeta).
profile_data: analyses a DataFrame in-memory, returns a DataProfile with
              column types, roles, stats, detected patterns, and suggested
              groupings.  Wide CSVs (>15 cols) are truncated by relevance.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.core.config import settings
from app.schemas.tool_schema import (
    ColumnProfile,
    ColumnStats,
    DataGrouping,
    DataPatterns,
    DataProfile,
    ParsedDataMeta,
)
from app.tools.base_tool import ToolResult, register_tool
from app.utils.logger import logger

_MAX_PROFILE_COLUMNS = 15
_TEMPORAL_KEYWORDS = {"date", "time", "year", "month", "quarter", "period", "day", "week"}


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class ParseFileInput(BaseModel):
    file_id: str
    filename: str


class ProfileDataInput(BaseModel):
    file_id: str
    filename: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_file_path(file_id: str, filename: str) -> Path:
    return Path(settings.upload_dir) / file_id / filename


def _read_dataframe(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _infer_column_type(series: pd.Series, col_name: str) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "temporal"

    lowered = col_name.lower().strip()
    if any(kw in lowered for kw in _TEMPORAL_KEYWORDS):
        try:
            pd.to_datetime(series.dropna().head(20), infer_datetime_format=True)
            return "temporal"
        except (ValueError, TypeError):
            pass

    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    if pd.api.types.is_numeric_dtype(series):
        str_vals = series.dropna().astype(str)
        if str_vals.str.contains("%").mean() > 0.5:
            return "percentage"
        return "numeric"

    nunique = series.nunique()
    ratio = nunique / max(len(series), 1)
    if nunique <= 10 or (nunique <= 30 and ratio < 0.5):
        return "categorical"

    return "text"


def _infer_role(col_type: str, col_name: str, is_first_non_numeric: bool) -> str:
    if col_type == "temporal":
        return "axis"
    if col_type in ("numeric", "percentage"):
        return "value"
    if col_type == "categorical":
        return "grouper" if not is_first_non_numeric else "axis"
    if col_type == "text":
        return "label"
    return "unknown"


def _compute_stats(series: pd.Series, col_type: str) -> ColumnStats:
    null_count = int(series.isna().sum())
    distinct_count = int(series.nunique())
    if col_type in ("numeric", "percentage"):
        numeric = pd.to_numeric(series, errors="coerce")
        return ColumnStats(
            min=float(numeric.min()) if not numeric.isna().all() else None,
            max=float(numeric.max()) if not numeric.isna().all() else None,
            mean=float(numeric.mean()) if not numeric.isna().all() else None,
            median=float(numeric.median()) if not numeric.isna().all() else None,
            std_dev=float(numeric.std()) if not numeric.isna().all() else None,
            null_count=null_count,
            distinct_count=distinct_count,
        )
    if col_type == "temporal":
        return ColumnStats(
            min=str(series.dropna().min()) if not series.isna().all() else None,
            max=str(series.dropna().max()) if not series.isna().all() else None,
            null_count=null_count,
            distinct_count=distinct_count,
        )
    return ColumnStats(null_count=null_count, distinct_count=distinct_count)


def _detect_patterns(columns: list[ColumnProfile]) -> DataPatterns:
    types = {c.data_type for c in columns}
    cat_cols = [c for c in columns if c.data_type == "categorical"]

    is_time_series = "temporal" in types and any(c.data_type in ("numeric", "percentage") for c in columns)
    has_hierarchy = len(cat_cols) >= 2
    num_cols = [c for c in columns if c.data_type in ("numeric", "percentage")]
    is_comparison = (
        len(num_cols) >= 2
        and any("actual" in c.name.lower() or "budget" in c.name.lower() for c in num_cols)
    )
    is_distribution = any(
        c.data_type == "categorical" and c.stats and c.stats.distinct_count > 5
        for c in columns
    ) and len(num_cols) == 1

    if is_time_series:
        dominant = "time_series"
    elif is_comparison:
        dominant = "comparison"
    elif is_distribution:
        dominant = "distribution"
    elif has_hierarchy:
        dominant = "hierarchy"
    else:
        dominant = "unknown"

    return DataPatterns(
        is_time_series=is_time_series,
        has_hierarchy=has_hierarchy,
        is_comparison=is_comparison,
        is_distribution=is_distribution,
        dominant_pattern=dominant,
    )


def _suggest_groupings(
    columns: list[ColumnProfile],
    df: pd.DataFrame,
) -> list[DataGrouping]:
    axis_cols = [c for c in columns if c.role == "axis"]
    value_cols = [c for c in columns if c.role == "value"]
    grouper_cols = [c for c in columns if c.role == "grouper"]

    if not axis_cols or not value_cols:
        return []

    groupings: list[DataGrouping] = []
    for axis in axis_cols:
        for grouper in [None, *grouper_cols]:
            values = [v.name for v in value_cols]
            n_categories = axis.stats.distinct_count if axis.stats else 0
            if n_categories <= 5:
                chart = "pie" if len(values) == 1 and not grouper else "bar"
            elif n_categories <= 12:
                chart = "grouped_bar" if len(values) > 1 or grouper else "bar"
            else:
                chart = "horizontal_bar"

            if axis.data_type == "temporal":
                chart = "line" if not grouper else "multi_line"

            confidence = 0.85 if grouper else 0.90
            groupings.append(
                DataGrouping(
                    axis=axis.name,
                    grouper=grouper.name if grouper else None,
                    values=values,
                    recommended_chart=chart,
                    confidence=confidence,
                )
            )
    return groupings[:5]


def _profile_dataframe(df: pd.DataFrame) -> DataProfile:
    truncated = False
    truncation_note = ""

    if df.shape[1] > _MAX_PROFILE_COLUMNS:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        other_cols = [c for c in df.columns if c not in numeric_cols]
        keep = other_cols[:5] + numeric_cols[: _MAX_PROFILE_COLUMNS - min(len(other_cols), 5)]
        df = df[keep]
        truncated = True
        truncation_note = f"Truncated from {df.shape[1]} to {len(keep)} columns by relevance"

    first_non_numeric_seen = False
    columns: list[ColumnProfile] = []
    for col in df.columns:
        series = df[col]
        col_type = _infer_column_type(series, str(col))

        is_first_non_numeric = False
        if col_type in ("categorical", "text") and not first_non_numeric_seen:
            is_first_non_numeric = True
            first_non_numeric_seen = True

        role = _infer_role(col_type, str(col), is_first_non_numeric)
        stats = _compute_stats(series, col_type)
        null_ratio = float(series.isna().mean())
        sample_values = [str(v) for v in series.dropna().head(5).tolist()]

        columns.append(
            ColumnProfile(
                name=str(col),
                data_type=col_type,
                role=role,
                stats=stats,
                null_ratio=null_ratio,
                sample_values=sample_values,
            )
        )

    patterns = _detect_patterns(columns)
    groupings = _suggest_groupings(columns, df)

    return DataProfile(
        row_count=len(df),
        column_count=len(columns),
        columns=columns,
        suggested_groupings=groupings,
        data_patterns=patterns,
        truncated=truncated,
        truncation_note=truncation_note,
    )


# ---------------------------------------------------------------------------
# Registered tools
# ---------------------------------------------------------------------------


@register_tool(
    name="parse_file",
    description="Parse a CSV or Excel file from the uploads directory and return metadata",
    input_schema=ParseFileInput,
    output_schema=ParsedDataMeta,
)
async def parse_file(file_id: str, filename: str) -> ToolResult:
    path = _resolve_file_path(file_id, filename)
    if not path.exists():
        return ToolResult.fail(f"File not found: {path}")

    try:
        df = _read_dataframe(path)
    except Exception as exc:
        return ToolResult.fail(f"Failed to parse {filename}: {exc}")

    warnings: list[str] = []
    null_pct = df.isna().mean().mean() * 100
    if null_pct > 20:
        warnings.append(f"High null ratio: {null_pct:.1f}% of cells are empty")
    if df.shape[0] == 0:
        warnings.append("File contains no data rows")

    meta = ParsedDataMeta(
        file_id=file_id,
        filename=filename,
        row_count=len(df),
        column_count=len(df.columns),
        columns=list(df.columns.astype(str)),
        parse_warnings=warnings,
    )
    return ToolResult.ok(data=meta.model_dump())


@register_tool(
    name="profile_data",
    description="Profile a parsed CSV/Excel file — detect column types, roles, stats, patterns, and suggested groupings",
    input_schema=ProfileDataInput,
    output_schema=DataProfile,
)
async def profile_data(file_id: str, filename: str) -> ToolResult:
    path = _resolve_file_path(file_id, filename)
    if not path.exists():
        return ToolResult.fail(f"File not found: {path}")

    try:
        df = _read_dataframe(path)
    except Exception as exc:
        return ToolResult.fail(f"Failed to read {filename}: {exc}")

    if df.empty:
        return ToolResult.fail(f"File {filename} contains no data rows")

    profile = _profile_dataframe(df)
    return ToolResult.ok(data=profile.model_dump())
