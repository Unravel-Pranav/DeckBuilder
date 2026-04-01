"""Template controller — thin router, delegates to TemplateService."""

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.core.dependencies import AsyncSessionDep
from app.core.exceptions import NotFoundException, ValidationException
from app.schemas.response import success_response
from app.schemas.template_schema import (
    TemplateCreate,
    TemplateDetailResponse,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.template_service import TemplateService

router = APIRouter()


@router.get("")
async def list_templates(session: AsyncSessionDep):
    result = await TemplateService(session).list_templates()
    return success_response(TemplateListResponse.model_validate(result).model_dump())


@router.post("", status_code=201)
async def create_template(body: TemplateCreate, session: AsyncSessionDep):
    tpl = await TemplateService(session).create_template(body)
    return success_response(TemplateResponse.model_validate(tpl).model_dump())


@router.get("/{template_id}")
async def get_template(template_id: int, session: AsyncSessionDep):
    tpl = await TemplateService(session).get_template(template_id)
    return success_response(TemplateDetailResponse.model_validate(tpl).model_dump())


@router.patch("/{template_id}")
async def update_template(template_id: int, body: TemplateUpdate, session: AsyncSessionDep):
    tpl = await TemplateService(session).update_template(template_id, body)
    return success_response(TemplateResponse.model_validate(tpl).model_dump())


@router.delete("/{template_id}")
async def delete_template(template_id: int, session: AsyncSessionDep):
    deleted = await TemplateService(session).delete_template(template_id)
    return success_response({"deleted": deleted})


@router.post("/{template_id}/ppt")
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
    return success_response(TemplateResponse.model_validate(tpl).model_dump())


@router.get("/{template_id}/slides")
async def list_template_slides(template_id: int, session: AsyncSessionDep):
    """Return metadata for each slide in the uploaded template .pptx."""
    svc = TemplateService(session)
    slides = await svc.extract_slide_metadata(template_id)
    return success_response({"template_id": template_id, "slides": slides})


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
