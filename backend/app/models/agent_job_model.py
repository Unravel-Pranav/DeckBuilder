"""AgentJobModel — tracks async agent pipeline jobs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentJobModel(Base):
    __tablename__ = "agent_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    mode: Mapped[str] = mapped_column(String(32), default="full")
    intent: Mapped[str] = mapped_column(Text, default="")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)

    request_payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    result_payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    errors: Mapped[list | None] = mapped_column(JSON, default=None)

    ppt_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # updated_at uses server_default only — repository methods explicitly
    # set it on every write (onupdate is unreliable with async SQLAlchemy)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
