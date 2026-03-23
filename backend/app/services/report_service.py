"""ReportService — business logic for reports."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.exceptions import NotFoundException
from app.models import ReportModel, ReportSectionModel, ReportSectionElementModel
from app.repositories.report_repository import ReportRepository
from app.schemas.report_schema import ReportCreate, ReportUpdate, ReportResponse, ReportListResponse
from app.utils.logger import logger

class ReportService:
    def __init__(self, session: AsyncSession):
        self._repo = ReportRepository(session)
        self._session = session

    async def list_reports(self) -> ReportListResponse:
        total = await self._repo.count()
        items = await self._repo.get_all_ordered()
        return ReportListResponse(total_count=total, items=[ReportResponse.model_validate(r) for r in items])

    async def get_report(self, report_id: int) -> ReportModel:
        model = await self._repo.get_with_sections(report_id)
        if not model:
            raise NotFoundException("Report", report_id)
        return model

    async def create_report(self, data: ReportCreate) -> ReportModel:
        logger.info("Creating report: %s", data.name)
        division = data.division if isinstance(data.division, list) else [data.division] if data.division else []
        report = ReportModel(name=data.name, template_id=data.template_id, template_name=data.template_name, report_type=data.report_type, status=data.status or "Draft", division=division, publishing_group=data.publishing_group, property_type=data.property_type, property_sub_type=data.property_sub_type, automation_mode=data.automation_mode, quarter=data.quarter, defined_markets=data.defined_markets)
        self._session.add(report)
        await self._session.flush()
        for sec_in in data.sections:
            sec = ReportSectionModel(report_id=report.id, key=sec_in.key, name=sec_in.name, sectionname_alias=sec_in.sectionname_alias or sec_in.name, display_order=sec_in.display_order, selected=sec_in.selected, layout_preference=sec_in.layout_preference)
            self._session.add(sec)
            await self._session.flush()
            for el_in in sec_in.elements:
                self._session.add(ReportSectionElementModel(report_section_id=sec.id, element_type=el_in.element_type, label=el_in.label, selected=el_in.selected, display_order=el_in.display_order, config=el_in.config or {}))
        result = await self._session.execute(select(ReportModel).options(selectinload(ReportModel.sections).selectinload(ReportSectionModel.elements)).where(ReportModel.id == report.id))
        return result.scalar_one()

    async def update_report(self, report_id: int, data: ReportUpdate) -> ReportModel:
        report = await self._repo.get_by_id(report_id)
        if not report:
            raise NotFoundException("Report", report_id)
        update_data = data.model_dump(exclude_none=True, exclude={"sections"})
        if "division" in update_data:
            d = update_data["division"]
            update_data["division"] = d if isinstance(d, list) else [d] if d else []
        for key, val in update_data.items():
            setattr(report, key, val)
        if data.sections is not None:
            for old in report.sections:
                await self._session.delete(old)
            await self._session.flush()
            for sec_in in data.sections:
                sec = ReportSectionModel(report_id=report.id, key=sec_in.key, name=sec_in.name, sectionname_alias=sec_in.sectionname_alias or sec_in.name, display_order=sec_in.display_order, selected=sec_in.selected, layout_preference=sec_in.layout_preference)
                self._session.add(sec)
                await self._session.flush()
                for el_in in sec_in.elements:
                    self._session.add(ReportSectionElementModel(report_section_id=sec.id, element_type=el_in.element_type, label=el_in.label, selected=el_in.selected, display_order=el_in.display_order, config=el_in.config or {}))
        result = await self._session.execute(select(ReportModel).options(selectinload(ReportModel.sections).selectinload(ReportSectionModel.elements)).where(ReportModel.id == report.id))
        return result.scalar_one()

    async def delete_report(self, report_id: int) -> bool:
        return await self._repo.delete_by_id(report_id)
