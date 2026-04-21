"""AgentJobRepository — CRUD for agent pipeline jobs.

All write methods explicitly set updated_at (onupdate is unreliable
with async SQLAlchemy).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_job_model import AgentJobModel
from app.repositories.base_repository import BaseRepository
from app.schemas.agent_schema import AgentGenerateResponse


class AgentJobRepository(BaseRepository[AgentJobModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AgentJobModel)

    async def get_by_job_id(self, job_id: str) -> AgentJobModel | None:
        stmt = select(AgentJobModel).where(AgentJobModel.job_id == job_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self, job_id: str, status: str, **fields: Any,
    ) -> None:
        job = await self.get_by_job_id(job_id)
        if job is None:
            return
        job.status = status
        job.updated_at = datetime.utcnow()
        for k, v in fields.items():
            if hasattr(job, k):
                setattr(job, k, v)
        await self._session.flush()

    async def set_result(
        self, job_id: str, response: AgentGenerateResponse,
    ) -> None:
        job = await self.get_by_job_id(job_id)
        if job is None:
            return
        job.status = response.status
        job.result_payload = response.model_dump(mode="json")
        job.errors = response.errors if response.errors else None
        job.ppt_file_path = response.ppt_download_url
        job.updated_at = datetime.utcnow()
        await self._session.flush()
