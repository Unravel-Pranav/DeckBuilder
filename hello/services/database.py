from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from hello.services.config import settings
import os

# database_url_safe: str = settings.database_url.replace('%', '%%')


connect_args = {
    "server_settings": {
        "search_path": settings.app_schema,
        "application_name": "market-reports",
    }
}


if os.getenv("ENV") != "test":
    connect_args["ssl"] = "require"
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args=connect_args
)


async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    # No-op for Alembic-managed migrations. Left for potential future hooks.
    return None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
