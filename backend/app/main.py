"""DeckBuilder API — FastAPI entry point with clean architecture."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine, async_session_factory
from app.core.exceptions import AppException, app_exception_handler, unhandled_exception_handler
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    # Import models to register on Base.metadata
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (%d tables)", len(Base.metadata.tables))

    # Seed demo data
    from app.services.seed_service import SeedService

    async with async_session_factory() as session:
        seed = SeedService(session)
        result = await seed.seed_if_empty()
        logger.info("Seed: %s", result)

    yield

    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)

# ─── Mount controllers ───

from app.api.v1.health_controller import router as health_router  # noqa: E402
from app.api.v1.template_controller import router as template_router  # noqa: E402
from app.api.v1.report_controller import router as report_router  # noqa: E402
from app.api.v1.section_controller import router as section_router  # noqa: E402
from app.api.v1.ai_controller import router as ai_router  # noqa: E402
from app.api.v1.structure_controller import router as structure_router  # noqa: E402
from app.api.v1.generation_controller import router as generation_router  # noqa: E402

app.include_router(health_router, tags=["health"])
app.include_router(template_router, prefix="/api/v1/templates", tags=["templates"])
app.include_router(report_router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(section_router, prefix="/api/v1/sections", tags=["sections"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(structure_router, prefix="/api/v1/structure", tags=["structure"])
app.include_router(generation_router, prefix="/api/v1/generation", tags=["generation"])
