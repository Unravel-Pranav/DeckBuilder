"""Structure controller — auto-generate report structure."""
from fastapi import APIRouter
from app.schemas.structure_schema import StructureGenerateRequest, StructureGenerateResponse
from app.services.structure_service import StructureService

router = APIRouter()

@router.post("/generate", response_model=StructureGenerateResponse)
async def generate_structure(body: StructureGenerateRequest):
    return await StructureService().generate_structure(body)
