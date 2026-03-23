from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hello.ml.logger import GLOBAL_LOGGER as logger


def _is_unique_violation(err: IntegrityError) -> bool:
    # asyncpg emits UniqueViolationError; robust check via message
    msg = str(getattr(err.orig, "__class__", type("", (), {})).__name__)
    return "UniqueViolationError" in msg or "duplicate key value" in str(err.orig)


async def handle_db_error(
    session: AsyncSession,
    err: SQLAlchemyError,
    conflict_message: str | None = None,
) -> None:
    """Translate common SQLAlchemy errors into HTTP errors and roll back the tx."""
    try:
        await session.rollback()
    except Exception:
        pass

    if isinstance(err, IntegrityError) and _is_unique_violation(err):
        raise HTTPException(
            status_code=409, detail=conflict_message or "Resource already exists"
        )

    logger.exception("Database error", exc_info=err)
    raise HTTPException(status_code=500, detail="Database error")
