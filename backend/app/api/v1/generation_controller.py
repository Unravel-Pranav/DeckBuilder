"""Generation controller — PPT generation."""

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.dependencies import AsyncSessionDep
from app.schemas.generation_schema import GenerateCustomRequest
from app.schemas.response import success_response
from app.services.generated_file_service import resolve_file_info
from app.services.ppt_service import PptService

router = APIRouter()


@router.post("/generate")
async def generate_ppt(report_id: int, session: AsyncSessionDep):
    result = await PptService(session).generate_ppt(report_id)
    return success_response(result)


@router.post("/generate-custom")
async def generate_custom_ppt(body: GenerateCustomRequest, session: AsyncSessionDep):
    """Generate PPT from a custom JSON payload sent from the frontend."""
    result = await PptService(session).generate_custom_ppt(body.model_dump())
    return success_response(result)


@router.get("/download/{file_id}")
async def download_ppt(file_id: str, session: AsyncSessionDep):
    """Download a generated PPT file by its ID."""
    file_info = await resolve_file_info(session, file_id)
    file_path = file_info["file_path"]
    filename = file_info["filename"]

    if not os.path.exists(file_path):
        from app.core.exceptions import NotFoundException

        raise NotFoundException("Physical file", file_id)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
