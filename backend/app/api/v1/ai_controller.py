"""AI controller — recommendations + commentary."""
from fastapi import APIRouter
from app.schemas.ai_schema import RecommendationRequest, AiRecommendationResponse, CommentaryRequest, CommentaryResponse
from app.services.ai_service import AiService

router = APIRouter()

@router.post("/recommendations", response_model=AiRecommendationResponse)
async def generate_recommendations(body: RecommendationRequest):
    return await AiService().generate_recommendations(body)

@router.post("/commentary", response_model=CommentaryResponse)
async def generate_commentary(body: CommentaryRequest):
    text = await AiService().generate_commentary(body)
    return CommentaryResponse(commentary=text)
