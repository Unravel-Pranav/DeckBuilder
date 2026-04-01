"""Structure controller — auto-generate report structure."""
from fastapi import APIRouter

from app.schemas.response import success_response
from app.schemas.structure_schema import StructureGenerateRequest, StructureGenerateResponse
from app.services.structure_service import StructureService

router = APIRouter()


@router.post("/generate")
async def generate_structure(body: StructureGenerateRequest):
    result = await StructureService().generate_structure(body)
    return success_response(StructureGenerateResponse.model_validate(result).model_dump())
