"""SectionService — business logic for template sections."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundException
from app.models import TemplateSectionModel, TemplateSectionElementModel
from app.repositories.section_repository import SectionRepository
from app.schemas.template_schema import TemplateSectionUpdate

class SectionService:
    def __init__(self, session: AsyncSession):
        self._repo = SectionRepository(session)
        self._session = session

    async def get_section(self, section_id: int) -> TemplateSectionModel:
        model = await self._repo.get_with_elements(section_id)
        if not model:
            raise NotFoundException("Section", section_id)
        return model

    async def update_section(self, section_id: int, data: TemplateSectionUpdate) -> TemplateSectionModel:
        model = await self._repo.get_by_id(section_id)
        if not model:
            raise NotFoundException("Section", section_id)
        update_data = data.model_dump(exclude_none=True, exclude={"elements"})
        for key, val in update_data.items():
            setattr(model, key, val)
        if data.elements is not None:
            for old_el in model.elements:
                await self._session.delete(old_el)
            await self._session.flush()
            for el in data.elements:
                self._session.add(TemplateSectionElementModel(section_id=model.id, element_type=el.element_type, display_order=el.display_order, config=el.config))
        return model

    async def delete_section(self, section_id: int) -> bool:
        return await self._repo.delete_by_id(section_id)
