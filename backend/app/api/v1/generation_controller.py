"""Generation controller — PPT generation."""
from fastapi import APIRouter
from app.core.dependencies import AsyncSessionDep
from app.services.ppt_service import PptService

router = APIRouter()

@router.post("/generate")
async def generate_ppt(report_id: int, session: AsyncSessionDep):
    return await PptService(session).generate_ppt(report_id)
