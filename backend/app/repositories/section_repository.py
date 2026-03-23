"""SectionRepository — DB queries for template sections."""
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.template_section_model import TemplateSectionModel, TemplateSectionElementModel
from app.repositories.base_repository import BaseRepository

class SectionRepository(BaseRepository[TemplateSectionModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, TemplateSectionModel)

    async def get_with_elements(self, section_id: int) -> TemplateSectionModel | None:
        stmt = (
            select(TemplateSectionModel)
            .options(selectinload(TemplateSectionModel.elements))
            .where(TemplateSectionModel.id == section_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
