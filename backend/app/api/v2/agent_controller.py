"""Executable v2 agent endpoints for upload, orchestration and download."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.agents.orchestrator import run_agent_pipeline
from app.core.config import settings
from app.schemas.agent_schema import AgentGenerateRequest, AgentGenerateResponse

router = APIRouter()

_UPLOAD_ROOT = Path(settings.upload_dir)
_jobs: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename")

    suffix = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in {"csv", "xlsx"}:
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_id = str(uuid4())
    target_dir = _UPLOAD_ROOT / file_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file.filename
    target_path.write_bytes(content)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "size_bytes": len(content),
    }


async def _run_job(job_id: str, req: AgentGenerateRequest) -> None:
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["updated_at"] = _now_iso()
    try:
        result = await run_agent_pipeline(req)
        result["ppt_download_url"] = (
            f"/api/v2/agent/jobs/{job_id}/download" if result.get("ppt_file_path") else None
        )
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["result"] = result
        _jobs[job_id]["ppt_file_path"] = result.get("ppt_file_path")
        _jobs[job_id]["updated_at"] = _now_iso()
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["result"] = {
            "status": "failed",
            "errors": [str(exc)],
            "steps_completed": _jobs[job_id].get("result", {}).get("steps_completed", []),
        }
        _jobs[job_id]["updated_at"] = _now_iso()


@router.post("/generate", response_model=AgentGenerateResponse)
async def generate(payload: AgentGenerateRequest) -> AgentGenerateResponse:
    job_id = str(uuid4())
    now = _now_iso()

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "request": payload.model_dump(),
        "result": {
            "status": "pending",
            "mode": payload.mode,
            "dry_run": payload.dry_run,
            "steps_completed": [],
            "errors": [],
            "ppt_download_url": None,
        },
        "ppt_file_path": None,
    }
    asyncio.create_task(_run_job(job_id, payload))
    return AgentGenerateResponse(job_id=job_id, status="pending")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/download")
async def download_job_ppt(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    ppt_file_path = job.get("ppt_file_path")
    if not ppt_file_path:
        raise HTTPException(status_code=404, detail="No PPT artifact for this job")

    path = Path(ppt_file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PPT artifact path not found")

    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
