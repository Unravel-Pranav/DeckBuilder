"""PptService — wraps the PPT engine pipeline."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundException
from app.models import ReportModel, GeneratedReportModel
from app.repositories.report_repository import ReportRepository
from app.utils.logger import logger

class PptService:
    def __init__(self, session: AsyncSession):
        self._repo = ReportRepository(session)
        self._session = session

    async def generate_ppt(self, report_id: int) -> dict:
        report = await self._repo.get_with_sections(report_id)
        if not report:
            raise NotFoundException("Report", report_id)
        logger.info("Generating PPT for report: %s (id=%d)", report.name, report.id)
        pipeline_sections = []
        for section in report.sections:
            elements = [{"id": e.id, "element_type": e.element_type, "label": e.label, "selected": e.selected, "display_order": e.display_order, "config": e.config or {}} for e in section.elements]
            pipeline_sections.append({"id": section.id, "key": section.key, "name": section.name, "sectionname_alias": section.sectionname_alias, "display_order": section.display_order, "selected": section.selected, "layout_preference": section.layout_preference, "elements": elements})
        pipeline_input = {"report": {"id": report.id, "name": report.name, "property_type": report.property_type or "Office", "property_sub_type": report.property_sub_type or "Figures", "quarter": report.quarter or "", "division": report.division[0] if report.division else "", "publishing_group": report.publishing_group or "", "hero_fields": report.hero_fields or {}}, "sections": pipeline_sections}
        try:
            from app.ppt_engine.pptx_builder import generate_presentation
            file_info = await generate_presentation(pipeline_input)
            logger.info("PPT generated: %s", file_info.get("filename"))
            gen = GeneratedReportModel(report_id=report.id, status="Complete", file_path=file_info.get("file_path"))
            self._session.add(gen)
            report.status = "Complete"
            return {"success": True, "message": "PPT generated", **file_info}
        except Exception as e:
            logger.error("PPT generation failed: %s", e)
            return {"success": False, "message": str(e)}
