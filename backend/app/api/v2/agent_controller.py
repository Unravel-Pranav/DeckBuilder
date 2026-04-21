"""V2 Agent controller — async pipeline execution, file upload, job polling."""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.agents.orchestrator import run_agent_pipeline
from app.core.config import settings
from app.core.database import async_session_factory
from app.models.agent_job_model import AgentJobModel
from app.repositories.agent_job_repository import AgentJobRepository
from app.schemas.agent_schema import AgentGenerateRequest, AgentGenerateResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_job(
    job_id: str,
    request: AgentGenerateRequest,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Execute the agent pipeline in the background.

    Uses three independent short-lived sessions:
      1. Set status → "running"
      2. run_agent_pipeline (creates its own sessions via factory)
      3. Store result or failure
    """
    # Session 1: mark running
    try:
        async with session_factory() as session:
            repo = AgentJobRepository(session)
            await repo.update_status(job_id, "running")
            await session.commit()
    except Exception:
        logger.exception("Failed to mark job %s as running", job_id)

    # Pipeline execution
    response: AgentGenerateResponse | None = None
    try:
        response = await run_agent_pipeline(request, session_factory)
        response.job_id = job_id
    except Exception:
        logger.exception("Pipeline failed for job %s", job_id)

    # Session 2: persist result or failure
    try:
        async with session_factory() as session:
            repo = AgentJobRepository(session)
            if response is not None:
                await repo.set_result(job_id, response)
            else:
                await repo.update_status(
                    job_id,
                    "failed",
                    errors=[{"step": "pipeline", "message": "Unhandled pipeline exception", "timestamp": time.time()}],
                )
            await session.commit()
    except Exception:
        logger.exception("Failed to persist result for job %s", job_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate(
    request: AgentGenerateRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    job_id = uuid.uuid4().hex

    async with async_session_factory() as session:
        job = AgentJobModel(
            job_id=job_id,
            status="pending",
            mode=request.mode,
            intent=request.intent,
            dry_run=request.dry_run,
            request_payload=request.model_dump(mode="json"),
        )
        session.add(job)
        await session.commit()

    background_tasks.add_task(_run_job, job_id, request, async_session_factory)
    return {"job_id": job_id, "status": "pending"}


@router.post("/upload")
async def upload_file(file: UploadFile) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(422, "Filename is required")

    ext = Path(file.filename).suffix.lower()
    content_type_ok = file.content_type in _ALLOWED_CONTENT_TYPES
    extension_ok = ext in _ALLOWED_EXTENSIONS

    if not content_type_ok and not extension_ok:
        raise HTTPException(
            422,
            f"Invalid file type '{file.content_type}' / extension '{ext}'. "
            f"Allowed: CSV, XLSX",
        )

    if file.size is not None and file.size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_size_mb} MB limit")

    file_id = uuid.uuid4().hex
    upload_dir = Path(settings.upload_dir) / file_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / file.filename
    contents = await file.read()

    if len(contents) > settings.max_upload_size_mb * 1024 * 1024:
        upload_dir.rmdir()
        raise HTTPException(413, f"File exceeds {settings.max_upload_size_mb} MB limit")

    dest.write_bytes(contents)

    return {"file_id": file_id, "filename": file.filename}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    async with async_session_factory() as session:
        repo = AgentJobRepository(session)
        job = await repo.get_by_job_id(job_id)

    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "mode": job.mode,
        "dry_run": job.dry_run,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "errors": job.errors,
        "result": job.result_payload,
        "ppt_file_path": job.ppt_file_path,
    }


@router.get("/jobs/{job_id}/download")
async def download_ppt(job_id: str) -> FileResponse:
    async with async_session_factory() as session:
        repo = AgentJobRepository(session)
        job = await repo.get_by_job_id(job_id)

    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.status != "completed":
        raise HTTPException(409, f"Job is '{job.status}', not completed")

    if not job.ppt_file_path or not os.path.isfile(job.ppt_file_path):
        raise HTTPException(404, "PPT file not found on disk")

    return FileResponse(
        path=job.ppt_file_path,
        filename=f"autodeck_{job_id}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
