"""GeneratedReportModel — versioned PPT outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.report_model import ReportModel


class GeneratedReportModel(Base):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(512), default="presentation.pptx")
    presentation_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="complete")
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    report: Mapped[Optional["ReportModel"]] = relationship("ReportModel")
