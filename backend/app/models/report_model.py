"""ReportModel — a concrete presentation instance."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any, TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.template_model import TemplateModel
    from app.models.report_section_model import ReportSectionModel


class ReportModel(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    template_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    report_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="Draft")
    division: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    publishing_group: Mapped[str] = mapped_column(String(128), default="")
    property_type: Mapped[str] = mapped_column(String(64), default="")
    property_sub_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    automation_mode: Mapped[str] = mapped_column(String(32), default="Attended")
    quarter: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    defined_markets: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    hero_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    ppt_url: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template: Mapped[Optional[TemplateModel]] = relationship("TemplateModel", lazy="joined", back_populates="reports")
    sections: Mapped[list[ReportSectionModel]] = relationship(
        "ReportSectionModel", back_populates="report",
        cascade="all, delete-orphan", order_by="ReportSectionModel.display_order", lazy="joined",
    )
