"""Template controller — thin router, delegates to TemplateService."""

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.core.dependencies import AsyncSessionDep
from app.core.exceptions import NotFoundException, ValidationException
from app.schemas.template_schema import (
    TemplateCreate,
    TemplateDetailResponse,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
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


@router.post("/{template_id}/ppt", response_model=TemplateResponse)
async def upload_template_ppt(
    template_id: int,
    session: AsyncSessionDep,
    file: UploadFile = File(...),
):
    """Validate .pptx with python-pptx, then save under `data/template_decks/`."""
    content = await file.read()
    if not content:
        raise ValidationException("Uploaded file is empty")
    svc = TemplateService(session)
    tpl = await svc.attach_template_ppt(
        template_id,
        filename=file.filename or "template.pptx",
        content=content,
    )
    return TemplateResponse.model_validate(tpl)


@router.get("/{template_id}/ppt/download")
async def download_template_ppt(template_id: int, session: AsyncSessionDep):
    """Download the stored template deck (if any)."""
    svc = TemplateService(session)
    tpl = await svc.get_template(template_id)
    path = svc.resolve_template_ppt_path(tpl)
    if not path:
        raise NotFoundException("Attached template PPT", template_id)
    return FileResponse(
        path,
        filename=f"template-{template_id}.pptx",
        media_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
    )
