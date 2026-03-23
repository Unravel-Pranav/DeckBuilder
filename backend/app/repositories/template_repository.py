"""TemplateRepository — DB queries for templates."""
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.template_model import TemplateModel
from app.models.template_section_model import TemplateSectionModel, TemplateSectionElementModel
from app.repositories.base_repository import BaseRepository

class TemplateRepository(BaseRepository[TemplateModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, TemplateModel)

    async def get_with_sections(self, template_id: int) -> TemplateModel | None:
        stmt = (
            select(TemplateModel)
            .options(selectinload(TemplateModel.sections).selectinload(TemplateSectionModel.elements))
            .where(TemplateModel.id == template_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_ordered(self) -> list[TemplateModel]:
        stmt = select(TemplateModel).order_by(TemplateModel.last_modified.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
