"""mapping_tool — column-to-chart binding and skeleton data contracts.

map_columns_to_chart:    Binds DataProfile columns to chart axes for a given chart type.
                         Produces data slices ready for the PPT engine.
generate_data_contract:  For skeleton mode — describes what data each slide
                         needs so the user can supply matching CSV later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.tool_schema import (
    ChartDataMapping,
    ColumnSpec,
    DataContract,
    DataProfile,
    FilterSpec,
)
from app.tools.base_tool import ToolResult, register_tool

_SAMPLE_ROWS = 20


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class MapColumnsInput(BaseModel):
    data_profile: DataProfile
    chart_type: str
    section_index: int = 0
    file_id: str | None = None
    filename: str | None = None
    filters: list[FilterSpec] = []


class DataContractInput(BaseModel):
    sections: list[dict[str, Any]]
    data_profile: DataProfile | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pick_axis(profile: DataProfile) -> str | None:
    for c in profile.columns:
        if c.role == "axis":
            return c.name
    for c in profile.columns:
        if c.data_type in ("temporal", "categorical"):
            return c.name
    return None


def _pick_values(profile: DataProfile, exclude: set[str]) -> list[str]:
    return [
        c.name for c in profile.columns
        if c.data_type in ("numeric", "percentage") and c.name not in exclude
    ]


def _pick_grouper(profile: DataProfile, exclude: set[str]) -> str | None:
    for c in profile.columns:
        if c.role == "grouper" and c.name not in exclude:
            return c.name
    return None


def _needs_dual_axis(chart_type: str) -> bool:
    return chart_type in ("combo", "dual_axis")


def _load_slice(
    file_id: str | None,
    filename: str | None,
    x_col: str | None,
    y_cols: list[str],
    grouper: str | None,
    filters: list[FilterSpec],
) -> list[dict[str, Any]]:
    """Load a data slice from the original file (up to _SAMPLE_ROWS)."""
    if not file_id or not filename:
        return []

    path = Path(settings.upload_dir) / file_id / filename
    if not path.exists():
        return []

    try:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(path)
        elif suffix in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        else:
            return []
    except Exception:
        return []

    for f in filters:
        if f.column in df.columns and f.value is not None:
            if f.operator == "eq":
                df = df[df[f.column] == f.value]
            elif f.operator == "ne":
                df = df[df[f.column] != f.value]
            elif f.operator == "gt":
                df = df[df[f.column] > f.value]
            elif f.operator == "lt":
                df = df[df[f.column] < f.value]

    keep = [c for c in [x_col, grouper, *y_cols] if c and c in df.columns]
    if not keep:
        return []

    return df[keep].head(_SAMPLE_ROWS).to_dict(orient="records")


# ---------------------------------------------------------------------------
# Registered tools
# ---------------------------------------------------------------------------


@register_tool(
    name="map_columns_to_chart",
    description="Bind DataProfile columns to chart axes and extract data slices",
    input_schema=MapColumnsInput,
    output_schema=ChartDataMapping,
)
async def map_columns_to_chart(
    data_profile: DataProfile,
    chart_type: str,
    section_index: int = 0,
    file_id: str | None = None,
    filename: str | None = None,
    filters: list[FilterSpec] | None = None,
) -> ToolResult:
    filters = filters or []
    warnings: list[str] = []

    x_axis = _pick_axis(data_profile)
    if not x_axis:
        warnings.append("No suitable axis column found; chart may need manual mapping")

    exclude: set[str] = set()
    if x_axis:
        exclude.add(x_axis)

    grouper = _pick_grouper(data_profile, exclude)
    if grouper:
        exclude.add(grouper)

    y_axis = _pick_values(data_profile, exclude)
    if not y_axis:
        warnings.append("No numeric columns found for Y-axis values")

    if _needs_dual_axis(chart_type) and len(y_axis) < 2:
        warnings.append(f"Chart type '{chart_type}' expects dual axis but only {len(y_axis)} value column(s) found")

    if chart_type == "pie" and grouper:
        warnings.append("Pie chart ignores grouper column; using axis categories directly")
        grouper = None

    labels = x_axis

    data_slice = _load_slice(file_id, filename, x_axis, y_axis, grouper, filters)

    mapping = ChartDataMapping(
        section_index=section_index,
        chart_type=chart_type,
        x_axis=x_axis,
        y_axis=y_axis,
        grouper=grouper,
        labels=labels,
        filters=filters,
        data_slice=data_slice,
        warnings=warnings,
    )
    return ToolResult.ok(data=mapping.model_dump())


@register_tool(
    name="generate_data_contract",
    description="Generate DataContract specs for skeleton mode — describes what data each slide needs",
    input_schema=DataContractInput,
    output_schema=DataContract,
)
async def generate_data_contract(
    sections: list[dict[str, Any]],
    data_profile: DataProfile | None = None,
) -> ToolResult:
    contracts: list[dict[str, Any]] = []

    for idx, section in enumerate(sections):
        chart_type = section.get("chart_type", "bar")
        name = section.get("name", f"Section {idx + 1}")
        element_type = section.get("element_type", "chart")

        required: list[dict[str, str]] = []
        optional: list[dict[str, str]] = []
        constraints: list[str] = []
        example_data: list[dict[str, Any]] = []

        if element_type == "commentary":
            contracts.append(
                DataContract(
                    slide_index=idx,
                    chart_type="none",
                    constraints=["Commentary-only slide — no data required"],
                ).model_dump()
            )
            continue

        if data_profile:
            axis_col = _pick_axis(data_profile)
            value_cols = _pick_values(data_profile, {axis_col} if axis_col else set())
            grouper = _pick_grouper(data_profile, {axis_col} if axis_col else set())

            if axis_col:
                col_meta = next((c for c in data_profile.columns if c.name == axis_col), None)
                required.append(ColumnSpec(
                    name=axis_col,
                    expected_type=col_meta.data_type if col_meta else "categorical",
                    role="x_axis",
                    description=f"X-axis categories for {name}",
                ).model_dump())

            for vc in value_cols[:2]:
                col_meta = next((c for c in data_profile.columns if c.name == vc), None)
                required.append(ColumnSpec(
                    name=vc,
                    expected_type="numeric",
                    role="y_axis",
                    description=f"Numeric values for {name}",
                ).model_dump())

            if grouper:
                col_meta = next((c for c in data_profile.columns if c.name == grouper), None)
                optional.append(ColumnSpec(
                    name=grouper,
                    expected_type="categorical",
                    role="grouper",
                    description=f"Series grouping for {name}",
                ).model_dump())

        else:
            required.append(ColumnSpec(
                name="category",
                expected_type="categorical",
                role="x_axis",
                description=f"Category labels for {name}",
            ).model_dump())
            required.append(ColumnSpec(
                name="value",
                expected_type="numeric",
                role="y_axis",
                description=f"Numeric values for {name}",
            ).model_dump())
            optional.append(ColumnSpec(
                name="group",
                expected_type="categorical",
                role="grouper",
                description=f"Optional series grouping for {name}",
            ).model_dump())

            example_data = [
                {"category": "Category A", "value": 100, "group": "Series 1"},
                {"category": "Category B", "value": 200, "group": "Series 1"},
                {"category": "Category A", "value": 150, "group": "Series 2"},
                {"category": "Category B", "value": 250, "group": "Series 2"},
            ]

        if chart_type == "pie":
            constraints.append("Maximum 8 categories recommended for readability")
        if chart_type in ("combo", "dual_axis"):
            constraints.append("Requires at least 2 numeric columns for dual-axis")

        contracts.append(
            DataContract(
                slide_index=idx,
                chart_type=chart_type,
                required_columns=required,
                optional_columns=optional,
                constraints=constraints,
                example_data=example_data,
            ).model_dump()
        )

    return ToolResult.ok(data=contracts)
