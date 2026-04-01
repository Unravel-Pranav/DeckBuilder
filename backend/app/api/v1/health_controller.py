"""Health check endpoint."""
from fastapi import APIRouter

from app.core.config import settings
from app.schemas.response import success_response

router = APIRouter()


@router.get("/health")
async def health_check():
    return success_response({"status": "ok", "version": settings.app_version})
