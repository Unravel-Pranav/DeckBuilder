"""TemplateService — business logic for templates."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.paths import backend_root
from app.models import TemplateModel, TemplateSectionModel, TemplateSectionElementModel
from app.repositories.template_repository import TemplateRepository
from app.schemas.template_schema import (
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.template_ppt_validation import (
    TemplatePptValidationError,
    validate_template_deck_bytes,
)
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

    async def attach_template_ppt(
        self, template_id: int, *, filename: str, content: bytes
    ) -> TemplateModel:
        """Validate deck bytes, write to disk, update template row."""
        suffix = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
        if suffix != "pptx":
            raise ValidationException(
                "Only .pptx files are supported for template decks."
            )
        try:
            validate_template_deck_bytes(content, suffix=suffix)
        except TemplatePptValidationError as err:
            raise ValidationException(str(err)) from err

        model = await self._repo.get_by_id(template_id)
        if not model:
            raise NotFoundException("Template", template_id)

        deck_dir = backend_root() / settings.template_decks_dir
        deck_dir.mkdir(parents=True, exist_ok=True)
        dest = deck_dir / f"{template_id}.pptx"
        dest.write_bytes(content)

        rel_key = f"{settings.template_decks_dir}/{template_id}.pptx".replace("\\", "/")
        model.ppt_status = "Attached"
        model.ppt_s3_key = rel_key
        model.ppt_url = f"/api/v1/templates/{template_id}/ppt/download"
        model.ppt_attached_time = datetime.utcnow()
        model.last_modified = datetime.utcnow()
        await self._session.flush()
        await self._session.refresh(model)
        logger.info("Attached template pptx template_id=%s path=%s", template_id, dest)
        return model

    def resolve_template_ppt_path(self, template: TemplateModel) -> Path | None:
        """Return absolute path to stored .pptx if marked attached and file exists."""
        if not template.ppt_s3_key or template.ppt_status != "Attached":
            return None
        path = (backend_root() / Path(template.ppt_s3_key.replace("\\", "/"))).resolve()
        if not path.is_file():
            return None
        return path
