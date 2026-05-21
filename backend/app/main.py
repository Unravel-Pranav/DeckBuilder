"""Auto Deck API — FastAPI entry point with clean architecture."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from app.core.auth import verify_api_key
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
        from app.core.db_migrate import migrate_drafts, migrate_generated_reports

        await conn.run_sync(migrate_generated_reports)
        await conn.run_sync(migrate_drafts)
    logger.info("Database tables created (%d tables)", len(Base.metadata.tables))

    from app.services.generated_file_service import load_generated_file_cache

    async with async_session_factory() as session:
        loaded = await load_generated_file_cache(session)
        await session.commit()
        logger.info("Loaded %d generated file(s) into download cache", loaded)

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
from app.api.v1.ppt_templates_controller import router as ppt_templates_router  # noqa: E402
from app.api.v1.draft_controller import router as draft_router  # noqa: E402
from app.api.v1.recommendation_controller import router as recommendation_router  # noqa: E402
from app.api.v2.agent_controller import router as agent_v2_router  # noqa: E402

_protected = [Depends(verify_api_key)]

app.include_router(health_router, tags=["health"])
app.include_router(template_router, prefix="/api/v1/templates", tags=["templates"], dependencies=_protected)
app.include_router(report_router, prefix="/api/v1/reports", tags=["reports"], dependencies=_protected)
app.include_router(section_router, prefix="/api/v1/sections", tags=["sections"], dependencies=_protected)
app.include_router(ai_router, prefix="/api/v1/ai", tags=["ai"], dependencies=_protected)
app.include_router(structure_router, prefix="/api/v1/structure", tags=["structure"], dependencies=_protected)
app.include_router(generation_router, prefix="/api/v1/generation", tags=["generation"], dependencies=_protected)
app.include_router(ppt_templates_router, prefix="/api/v1/ppt-templates", tags=["ppt-templates"], dependencies=_protected)
app.include_router(draft_router, prefix="/api/v1/drafts", tags=["drafts"], dependencies=_protected)
app.include_router(recommendation_router, prefix="/api/v1/recommendations", tags=["recommendations"], dependencies=_protected)
app.include_router(agent_v2_router, prefix="/api/v2/agent", tags=["agent-v2"], dependencies=_protected)

