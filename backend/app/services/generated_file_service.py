"""Persist and restore generated PPT file metadata."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.generated_report_model import GeneratedReportModel
from app.ppt_engine import pptx_builder


async def persist_generated_file(
    session: AsyncSession,
    file_info: dict[str, Any],
) -> GeneratedReportModel:
    """Store file metadata in DB and warm the in-memory cache."""
    expires_at = datetime.utcnow() + timedelta(days=7)
    row = GeneratedReportModel(
        file_id=file_info["file_id"],
        filename=file_info.get("filename", "presentation.pptx"),
        presentation_name=file_info.get("title"),
        file_path=file_info["file_path"],
        status="complete",
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    pptx_builder.generated_files[file_info["file_id"]] = file_info
    return row


async def load_generated_file_cache(session: AsyncSession) -> int:
    """Populate in-memory cache from DB rows whose files still exist on disk."""
    result = await session.execute(select(GeneratedReportModel))
    rows = result.scalars().all()
    loaded = 0
    for row in rows:
        if row.file_path and os.path.exists(row.file_path):
            pptx_builder.generated_files[row.file_id] = {
                "file_id": row.file_id,
                "file_path": row.file_path,
                "filename": row.filename,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "title": row.presentation_name or "",
                "author": "",
                "sections_count": 0,
            }
            loaded += 1
    return loaded


async def resolve_file_info(session: AsyncSession, file_id: str) -> dict[str, Any]:
    """Resolve download metadata from memory or database."""
    if file_id in pptx_builder.generated_files:
        return pptx_builder.generated_files[file_id]

    result = await session.execute(
        select(GeneratedReportModel).where(GeneratedReportModel.file_id == file_id)
    )
    row = result.scalar_one_or_none()
    if not row or not row.file_path or not os.path.exists(row.file_path):
        raise NotFoundException("Generated file", file_id)

    info = {
        "file_id": row.file_id,
        "file_path": row.file_path,
        "filename": row.filename,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "title": row.presentation_name or "",
        "author": "",
        "sections_count": 0,
    }
    pptx_builder.generated_files[file_id] = info
    return info
