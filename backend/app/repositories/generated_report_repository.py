"""GeneratedReportRepository — DB queries for generated PPT records."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.generated_report_model import GeneratedReportModel
from app.repositories.base_repository import BaseRepository

class GeneratedReportRepository(BaseRepository[GeneratedReportModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, GeneratedReportModel)

    async def get_by_report_id(self, report_id: int) -> list[GeneratedReportModel]:
        stmt = select(GeneratedReportModel).where(GeneratedReportModel.report_id == report_id).order_by(GeneratedReportModel.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
