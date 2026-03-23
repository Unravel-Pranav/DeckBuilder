"""Template controller — thin router, delegates to TemplateService."""
from fastapi import APIRouter
from app.core.dependencies import AsyncSessionDep
from app.schemas.template_schema import TemplateCreate, TemplateResponse, TemplateDetailResponse, TemplateUpdate, TemplateListResponse, TemplateSectionCreate, TemplateSectionResponse
from app.services.template_service import TemplateService

router = APIRouter()

@router.get("", response_model=TemplateListResponse)
async def list_templates(session: AsyncSessionDep):
    return await TemplateService(session).list_templates()

@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(body: TemplateCreate, session: AsyncSessionDep):
    tpl = await TemplateService(session).create_template(body)
    return TemplateResponse.model_validate(tpl)

@router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template(template_id: int, session: AsyncSessionDep):
    tpl = await TemplateService(session).get_template(template_id)
    return TemplateDetailResponse.model_validate(tpl)

@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: int, body: TemplateUpdate, session: AsyncSessionDep):
    tpl = await TemplateService(session).update_template(template_id, body)
    return TemplateResponse.model_validate(tpl)

@router.delete("/{template_id}")
async def delete_template(template_id: int, session: AsyncSessionDep):
    return {"deleted": await TemplateService(session).delete_template(template_id)}
