"""Auto Deck API — FastAPI entry point with clean architecture."""

from __future__ import annotations

import asyncio
import shutil
import time as _time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

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

    # --- Zombie job cleanup (mark stale "running" jobs as "failed") ---
    upload_cleanup_task: asyncio.Task[None] | None = None
    if settings.agent_mode_enabled:
        from app.models.agent_job_model import AgentJobModel

        async with async_session_factory() as session:
            stmt = (
                update(AgentJobModel)
                .where(AgentJobModel.status == "running")
                .values(
                    status="failed",
                    updated_at=datetime.utcnow(),
                    errors=[{
                        "step": "startup",
                        "message": "Marked as failed: server restarted",
                        "timestamp": _time.time(),
                    }],
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount:
                logger.warning("Zombie cleanup: marked %d stale jobs as failed", result.rowcount)

        # --- Upload TTL cleanup (periodic background task) ---
        async def _cleanup_uploads() -> None:
            upload_root = Path(settings.upload_dir)
            interval = max(settings.upload_ttl_seconds, 300)
            while True:
                try:
                    await asyncio.sleep(interval)
                    if not upload_root.exists():
                        continue
                    cutoff = _time.time() - settings.upload_ttl_seconds
                    for entry in upload_root.iterdir():
                        try:
                            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                                shutil.rmtree(entry)
                                logger.debug("Cleaned expired upload: %s", entry.name)
                        except Exception:
                            logger.exception("Failed to clean upload dir %s", entry.name)
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("Upload cleanup cycle failed")

        upload_cleanup_task = asyncio.create_task(_cleanup_uploads())
        logger.info("Upload cleanup task started (interval=%ds)", max(settings.upload_ttl_seconds, 300))

    # --- MCP session manager lifecycle ---
    if _mcp_session_manager is not None:
        async with _mcp_session_manager.run():
            logger.info("MCP session manager started")
            yield
    else:
        yield

    # --- Shutdown ---
    if upload_cleanup_task is not None:
        upload_cleanup_task.cancel()
        try:
            await upload_cleanup_task
        except asyncio.CancelledError:
            pass

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

app.include_router(health_router, tags=["health"])
app.include_router(template_router, prefix="/api/v1/templates", tags=["templates"])
app.include_router(report_router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(section_router, prefix="/api/v1/sections", tags=["sections"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(structure_router, prefix="/api/v1/structure", tags=["structure"])
app.include_router(generation_router, prefix="/api/v1/generation", tags=["generation"])
app.include_router(ppt_templates_router, prefix="/api/v1/ppt-templates", tags=["ppt-templates"])
app.include_router(draft_router, prefix="/api/v1/drafts", tags=["drafts"])

# ─── V2 Agent router (behind feature flag) ───

if settings.agent_mode_enabled:
    from app.api.v2.agent_controller import router as agent_router  # noqa: E402

    app.include_router(agent_router, prefix="/api/v2/agent", tags=["agent-v2"])

# ─── MCP server (behind feature flag) ───

_mcp_session_manager = None
if settings.mcp_enabled:
    from app.mcp.server import mcp_server, register_all_tools  # noqa: E402

    register_all_tools()
    _mcp_app = mcp_server.streamable_http_app()
    _mcp_session_manager = mcp_server.session_manager
    app.mount("/mcp", _mcp_app)
    logger.info("MCP server mounted at /mcp")

