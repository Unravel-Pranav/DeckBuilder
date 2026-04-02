"""AI controller — recommendations + commentary."""
from fastapi import APIRouter

from app.schemas.ai_schema import CommentaryRequest, RecommendationRequest
from app.schemas.response import success_response
from app.services.ai_service import AiService

router = APIRouter()


@router.post("/recommendations")
async def generate_recommendations(body: RecommendationRequest):
    result = await AiService().generate_recommendations(body)
    return success_response(result.model_dump())


@router.post("/commentary")
async def generate_commentary(body: CommentaryRequest):
    text = await AiService().generate_commentary(body)
    return success_response({"commentary": text})
