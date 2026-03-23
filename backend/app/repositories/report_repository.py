"""ReportRepository — DB queries for reports."""
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.report_model import ReportModel
from app.models.report_section_model import ReportSectionModel, ReportSectionElementModel
from app.repositories.base_repository import BaseRepository

class ReportRepository(BaseRepository[ReportModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ReportModel)

    async def get_with_sections(self, report_id: int) -> ReportModel | None:
        stmt = (
            select(ReportModel)
            .options(selectinload(ReportModel.sections).selectinload(ReportSectionModel.elements))
            .where(ReportModel.id == report_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_ordered(self, limit: int = 50) -> list[ReportModel]:
        stmt = select(ReportModel).order_by(ReportModel.updated_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
