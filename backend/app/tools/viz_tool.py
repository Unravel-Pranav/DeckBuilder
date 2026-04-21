"""viz_tool — rule-based chart type recommendation (no DB, no LLM).

Implements the chart selection rules from the gap analysis:
  Time series, categorical, high-cardinality, scatter, KPI card, etc.
Uses DataProfile for column-level detail when available, falls back
to DataShapeInput for abstract shapes.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.tool_schema import (
    DataProfile,
    DataShapeInput,
    VizRecommendation,
)
from app.tools.base_tool import ToolResult, register_tool


class VizRecommendInput(BaseModel):
    """Provide one of data_profile or data_shape."""

    data_profile: DataProfile | None = None
    data_shape: DataShapeInput | None = None


# ---------------------------------------------------------------------------
# Profile-aware (column-level) recommendation
# ---------------------------------------------------------------------------


def _recommend_from_profile(profile: DataProfile) -> VizRecommendation:
    patterns = profile.data_patterns

    temporal_cols = [c for c in profile.columns if c.data_type == "temporal"]
    categorical_cols = [c for c in profile.columns if c.data_type == "categorical"]
    numeric_cols = [c for c in profile.columns if c.data_type in ("numeric", "percentage")]

    n_cat = len(categorical_cols)
    n_num = len(numeric_cols)
    cat_distinct_max = max(
        (c.stats.distinct_count for c in categorical_cols if c.stats),
        default=0,
    )

    if patterns.is_time_series and temporal_cols:
        if n_num == 1:
            return VizRecommendation(
                chart_type="line", confidence=0.95,
                reasoning="Time series with single metric",
            )
        if n_num == 2:
            stats_pair = [
                c.stats for c in numeric_cols
                if c.stats and c.stats.max is not None
            ]
            if len(stats_pair) == 2:
                try:
                    maxes = [float(s.max) for s in stats_pair]  # type: ignore[arg-type]
                    if min(maxes) > 0 and max(maxes) / min(maxes) > 10:
                        return VizRecommendation(
                            chart_type="combo", confidence=0.88,
                            reasoning="Time series with 2 metrics at different scales (>10x)",
                            fallback_chart_type="multi_line",
                        )
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
            return VizRecommendation(
                chart_type="multi_line", confidence=0.90,
                reasoning="Time series with 2 metrics",
            )
        if n_num >= 3:
            return VizRecommendation(
                chart_type="multi_line", confidence=0.90,
                reasoning=f"Time series with {n_num} metrics",
            )

    if n_num == 1 and n_cat == 0 and not temporal_cols:
        return VizRecommendation(
            chart_type="kpi_card", confidence=0.88,
            reasoning="Single metric with no grouping",
        )

    if n_num == 2 and n_cat == 0 and not temporal_cols:
        return VizRecommendation(
            chart_type="scatter", confidence=0.75,
            reasoning="Two numeric columns without time or categories",
        )

    if profile.column_count >= 5 and profile.row_count > 20:
        return VizRecommendation(
            chart_type="table", confidence=0.90,
            reasoning="High-cardinality data (many columns + rows)",
        )

    if n_cat >= 1:
        if cat_distinct_max > 12:
            return VizRecommendation(
                chart_type="horizontal_bar", confidence=0.85,
                reasoning=f"Categorical with high cardinality ({cat_distinct_max} values)",
            )
        if n_cat >= 2 and n_num >= 1:
            return VizRecommendation(
                chart_type="stacked_bar", confidence=0.80,
                reasoning="Two categorical dimensions with numeric values",
            )
        if n_num >= 2:
            return VizRecommendation(
                chart_type="grouped_bar", confidence=0.87,
                reasoning="Categorical with multiple numeric metrics",
            )
        if n_num == 1:
            if cat_distinct_max <= 5:
                return VizRecommendation(
                    chart_type="pie", confidence=0.82,
                    reasoning=f"Few categories ({cat_distinct_max}) with single metric",
                )
            return VizRecommendation(
                chart_type="bar", confidence=0.90,
                reasoning=f"Categorical ({cat_distinct_max} values) with single metric",
            )

    return VizRecommendation(
        chart_type="table", confidence=0.50,
        reasoning="No strong pattern detected",
    )


# ---------------------------------------------------------------------------
# Shape-only (abstract) recommendation
# ---------------------------------------------------------------------------


def _recommend_from_shape(shape: DataShapeInput) -> VizRecommendation:
    if shape.numeric_columns == 1 and not shape.has_categorical and not shape.has_temporal:
        return VizRecommendation(
            chart_type="kpi_card", confidence=0.88,
            reasoning="Single metric with no grouping",
        )

    if shape.has_temporal:
        if shape.numeric_columns == 1:
            return VizRecommendation(
                chart_type="line", confidence=0.95,
                reasoning="Time series with single metric",
            )
        if shape.numeric_columns == 2:
            return VizRecommendation(
                chart_type="combo", confidence=0.88,
                reasoning="Time series with 2 metrics (potential dual axis)",
                fallback_chart_type="multi_line",
            )
        if shape.numeric_columns >= 3:
            return VizRecommendation(
                chart_type="multi_line", confidence=0.90,
                reasoning=f"Time series with {shape.numeric_columns} metrics",
            )

    if shape.numeric_columns == 2 and not shape.has_temporal and not shape.has_categorical:
        return VizRecommendation(
            chart_type="scatter", confidence=0.75,
            reasoning="Two numeric columns without time or categories",
        )

    if shape.column_count >= 5 and shape.row_count > 20:
        return VizRecommendation(
            chart_type="table", confidence=0.90,
            reasoning="High-cardinality data",
        )

    if shape.has_categorical:
        if shape.categorical_distinct_max > 12:
            return VizRecommendation(
                chart_type="horizontal_bar", confidence=0.85,
                reasoning=f"High-cardinality categorical ({shape.categorical_distinct_max} values)",
            )
        if shape.numeric_columns >= 2:
            return VizRecommendation(
                chart_type="grouped_bar", confidence=0.87,
                reasoning="Categorical with multiple metrics",
            )
        if shape.numeric_columns == 1:
            if shape.categorical_distinct_max <= 5:
                return VizRecommendation(
                    chart_type="pie", confidence=0.82,
                    reasoning=f"Few categories ({shape.categorical_distinct_max}) with single metric",
                )
            return VizRecommendation(
                chart_type="bar", confidence=0.90,
                reasoning=f"Categorical ({shape.categorical_distinct_max} values) with single metric",
            )

    return VizRecommendation(
        chart_type="table", confidence=0.50,
        reasoning="No strong pattern detected",
    )


# ---------------------------------------------------------------------------
# Registered tool
# ---------------------------------------------------------------------------


@register_tool(
    name="recommend_chart_type",
    description="Rule-based chart type recommendation from data profile or abstract data shape",
    input_schema=VizRecommendInput,
    output_schema=VizRecommendation,
)
async def recommend_chart_type(
    data_profile: DataProfile | None = None,
    data_shape: DataShapeInput | None = None,
) -> ToolResult:
    if data_profile is not None:
        rec = _recommend_from_profile(data_profile)
    elif data_shape is not None:
        rec = _recommend_from_shape(data_shape)
    else:
        return ToolResult.fail("Either data_profile or data_shape must be provided")

    return ToolResult.ok(data=rec.model_dump())
