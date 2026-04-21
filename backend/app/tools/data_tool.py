"""data_tool — DB-backed report and template data retrieval.

Wraps existing ReportRepository and TemplateRepository.
All functions require an AsyncSession (requires_session=True).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.report_repository import ReportRepository
from app.repositories.template_repository import TemplateRepository
from app.schemas.tool_schema import ReportDataOutput, SectionData, TemplateSummary
from app.tools.base_tool import ToolResult, register_tool


# ---------------------------------------------------------------------------
# Input schemas (session is injected, not part of the schema)
# ---------------------------------------------------------------------------


class FetchReportInput(BaseModel):
    report_id: int


class FetchTemplateInput(BaseModel):
    template_id: int


class ListTemplatesInput(BaseModel):
    limit: int = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model_to_report_output(report: Any) -> dict:
    """Convert a ReportModel (with eager-loaded sections) to ReportDataOutput dict."""
    sections = []
    for sec in report.sections:
        elements = [
            {
                "id": e.id,
                "element_type": e.element_type,
                "label": e.label,
                "selected": e.selected,
                "display_order": e.display_order,
                "config": e.config or {},
            }
            for e in sec.elements
        ]
        sections.append(
            SectionData(
                id=sec.id,
                key=sec.key,
                name=sec.name,
                sectionname_alias=sec.sectionname_alias,
                display_order=sec.display_order,
                selected=sec.selected,
                layout_preference=sec.layout_preference,
                elements=elements,
            ).model_dump()
        )
    return ReportDataOutput(
        report_id=report.id,
        report_name=report.name,
        property_type=report.property_type or "Office",
        property_sub_type=report.property_sub_type or "Figures",
        quarter=report.quarter or "",
        division=report.division[0] if report.division else "",
        sections=sections,
    ).model_dump()


# ---------------------------------------------------------------------------
# Registered tools
# ---------------------------------------------------------------------------


@register_tool(
    name="fetch_report_data",
    description="Fetch a report with all sections and elements from the database",
    input_schema=FetchReportInput,
    output_schema=ReportDataOutput,
    requires_session=True,
)
async def fetch_report_data(session: AsyncSession, report_id: int) -> ToolResult:
    repo = ReportRepository(session)
    report = await repo.get_with_sections(report_id)
    if report is None:
        return ToolResult.fail(f"Report {report_id} not found")
    return ToolResult.ok(data=_model_to_report_output(report))


@register_tool(
    name="fetch_template_summary",
    description="Fetch a template with section metadata from the database",
    input_schema=FetchTemplateInput,
    output_schema=TemplateSummary,
    requires_session=True,
)
async def fetch_template_summary(
    session: AsyncSession,
    template_id: int,
) -> ToolResult:
    repo = TemplateRepository(session)
    tpl = await repo.get_with_sections(template_id)
    if tpl is None:
        return ToolResult.fail(f"Template {template_id} not found")
    return ToolResult.ok(
        data=TemplateSummary(
            id=tpl.id,
            name=tpl.name,
            description=tpl.base_type,
            property_type=tpl.base_type,
        ).model_dump()
    )


@register_tool(
    name="list_templates",
    description="List available templates ordered by last modified",
    input_schema=ListTemplatesInput,
    output_schema=TemplateSummary,
    requires_session=True,
)
async def list_templates(session: AsyncSession, limit: int = 50) -> ToolResult:
    repo = TemplateRepository(session)
    templates = await repo.get_all_ordered()
    results = [
        TemplateSummary(
            id=t.id,
            name=t.name,
            description=t.base_type,
            property_type=t.base_type,
        ).model_dump()
        for t in templates[:limit]
    ]
    return ToolResult.ok(data=results)
