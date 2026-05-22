"""Optional API key authentication for deployed environments."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.core.config import settings
from app.schemas.response import ErrorCodes


async def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """
    Require ``X-API-Key`` when ``API_KEY`` is set in the environment.

    When ``API_KEY`` is empty, authentication is disabled (local development).
    """
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "error_code": ErrorCodes.UNAUTHORIZED,
                "data": None,
                "error": {"message": "Invalid or missing API key", "details": None},
            },
        )
