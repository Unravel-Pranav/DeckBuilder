"""TemplateService — business logic for templates."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundException
from app.models import TemplateModel, TemplateSectionModel, TemplateSectionElementModel
from app.repositories.template_repository import TemplateRepository
from app.schemas.template_schema import TemplateCreate, TemplateUpdate, TemplateResponse, TemplateListResponse
from app.utils.logger import logger

class TemplateService:
    def __init__(self, session: AsyncSession):
        self._repo = TemplateRepository(session)
        self._session = session

    async def list_templates(self) -> TemplateListResponse:
        total = await self._repo.count()
        items = await self._repo.get_all_ordered()
        return TemplateListResponse(
            total_count=total,
            items=[TemplateResponse.model_validate(t) for t in items],
        )

    async def get_template(self, template_id: int) -> TemplateModel:
        model = await self._repo.get_with_sections(template_id)
        if not model:
            raise NotFoundException("Template", template_id)
        return model

    async def create_template(self, data: TemplateCreate) -> TemplateModel:
        logger.info("Creating template: %s", data.name)
        tpl = TemplateModel(name=data.name, base_type=data.base_type, is_default=data.is_default, attended=data.attended, ppt_status="Not Attached")
        self._session.add(tpl)
        await self._session.flush()
        for sec_in in data.sections:
            sec = TemplateSectionModel(name=sec_in.name, sectionname_alias=sec_in.sectionname_alias, property_type=sec_in.property_type, property_sub_type=sec_in.property_sub_type, default_prompt=sec_in.default_prompt, slide_layout=sec_in.slide_layout, mode=sec_in.mode)
            sec.templates.append(tpl)
            self._session.add(sec)
            await self._session.flush()
            if sec_in.elements:
                for el in sec_in.elements:
                    self._session.add(TemplateSectionElementModel(section_id=sec.id, element_type=el.element_type, display_order=el.display_order, config=el.config))
        return tpl

    async def update_template(self, template_id: int, data: TemplateUpdate) -> TemplateModel:
        model = await self._repo.get_by_id(template_id)
        if not model:
            raise NotFoundException("Template", template_id)
        return await self._repo.update(model, data.model_dump(exclude_none=True))

    async def delete_template(self, template_id: int) -> bool:
        return await self._repo.delete_by_id(template_id)
