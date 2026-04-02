"""Generation controller — PPT generation."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.dependencies import AsyncSessionDep
from app.core.exceptions import NotFoundException
from app.schemas.response import success_response
from app.services.ppt_service import PptService

router = APIRouter()


@router.post("/generate")
async def generate_ppt(report_id: int, session: AsyncSessionDep):
    result = await PptService(session).generate_ppt(report_id)
    return success_response(result)


@router.post("/generate-custom")
async def generate_custom_ppt(json_data: dict, session: AsyncSessionDep):
    """Generate PPT from a custom JSON payload sent from the frontend."""
    result = await PptService(session).generate_custom_ppt(json_data)
    return success_response(result)


@router.get("/download/{file_id}")
async def download_ppt(file_id: str):
    """Download a generated PPT file by its ID."""
    from app.ppt_engine.pptx_builder import generated_files

    if file_id not in generated_files:
        raise NotFoundException("Generated file", file_id)

    file_info = generated_files[file_id]
    file_path = file_info["file_path"]
    filename = file_info["filename"]

    if not os.path.exists(file_path):
        raise NotFoundException("Physical file", file_id)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
