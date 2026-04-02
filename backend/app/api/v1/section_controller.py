"""Section controller — thin router for template sections."""
from fastapi import APIRouter

from app.core.dependencies import AsyncSessionDep
from app.schemas.response import success_response
from app.schemas.template_schema import TemplateSectionResponse, TemplateSectionUpdate
from app.services.section_service import SectionService

router = APIRouter()


@router.get("/{section_id}")
async def get_section(section_id: int, session: AsyncSessionDep):
    sec = await SectionService(session).get_section(section_id)
    return success_response(TemplateSectionResponse.model_validate(sec).model_dump())


@router.patch("/{section_id}")
async def update_section(section_id: int, body: TemplateSectionUpdate, session: AsyncSessionDep):
    sec = await SectionService(session).update_section(section_id, body)
    return success_response(TemplateSectionResponse.model_validate(sec).model_dump())


@router.delete("/{section_id}")
async def delete_section(section_id: int, session: AsyncSessionDep):
    deleted = await SectionService(session).delete_section(section_id)
    return success_response({"deleted": deleted})
