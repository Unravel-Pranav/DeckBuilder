"""PptService — wraps the PPT engine pipeline."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundException
from app.models import ReportModel
from app.repositories.report_repository import ReportRepository
from app.services.template_service import TemplateService
from app.utils.logger import logger

class PptService:
    def __init__(self, session: AsyncSession):
        self._repo = ReportRepository(session)
        self._session = session

    async def _resolve_user_deck_path(self, template_id: int | None) -> str | None:
        """Return absolute path to uploaded .pptx for a templates row, if attached."""
        if template_id is None:
            return None
        try:
            ts = TemplateService(self._session)
            tpl = await ts.get_template(int(template_id))
            path = ts.resolve_template_ppt_path(tpl)
            return str(path.resolve()) if path else None
        except (NotFoundException, ValueError, TypeError, OSError) as err:
            logger.warning("Could not resolve user deck for template_id=%s: %s", template_id, err)
            return None

    async def generate_ppt(self, report_id: int) -> dict:
        report = await self._repo.get_with_sections(report_id)
        if not report:
            raise NotFoundException("Report", report_id)
        logger.info("Generating PPT for report: %s (id=%d)", report.name, report.id)
        pipeline_sections = []
        for section in report.sections:
            elements = [{"id": e.id, "element_type": e.element_type, "label": e.label, "selected": e.selected, "display_order": e.display_order, "config": e.config or {}} for e in section.elements]
            pipeline_sections.append({"id": section.id, "key": section.key, "name": section.name, "sectionname_alias": section.sectionname_alias, "display_order": section.display_order, "selected": section.selected, "layout_preference": section.layout_preference, "elements": elements})
        pipeline_input = {
            "report": {
                "id": report.id,
                "name": report.name,
                "property_type": report.property_type or "Office",
                "property_sub_type": report.property_sub_type or "Figures",
                "quarter": report.quarter or "",
                "division": report.division[0] if report.division else "",
                "publishing_group": report.publishing_group or "",
                "hero_fields": report.hero_fields or {},
                "template_id": report.template_id,
            },
            "sections": pipeline_sections,
        }
        return await self.generate_custom_ppt(pipeline_input)

    async def generate_custom_ppt(self, json_data: dict) -> dict:
        """Generate PPT from a custom JSON payload."""
        logger.info("Generating custom PPT from JSON payload")
        raw_tid = (json_data.get("report") or {}).get("template_id")
        tid: int | None = None
        if raw_tid is not None and raw_tid != "":
            try:
                tid = int(raw_tid)
            except (TypeError, ValueError):
                tid = None
        user_deck_path = await self._resolve_user_deck_path(tid)
        try:
            from app.ppt_engine.pptx_builder import generate_presentation
            file_info = await generate_presentation(json_data, user_deck_path=user_deck_path)
            logger.info("Custom PPT generated: %s", file_info.get("filename"))
            return {"success": True, "message": "PPT generated", **file_info}
        except Exception as e:
            logger.error("Custom PPT generation failed: %s", e)
            return {"success": False, "message": str(e)}
