"""FastAPI dependency injection."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session

AsyncSessionDep = Annotated[AsyncSession, Depends(get_session)]
