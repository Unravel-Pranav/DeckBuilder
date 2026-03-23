"""TemplateModel — a reusable presentation structure."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, Boolean, DateTime, Table, Column, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.template_section_model import TemplateSectionModel
    from app.models.report_model import ReportModel

template_section_association = Table(
    "template_section_templates",
    Base.metadata,
    Column("template_id", ForeignKey("templates.id", ondelete="CASCADE"), primary_key=True),
    Column("section_id", ForeignKey("template_sections.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
)


class TemplateModel(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    base_type: Mapped[str] = mapped_column(String(64))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    attended: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now())
    ppt_status: Mapped[str] = mapped_column(String(32), default="Not Attached")
    ppt_s3_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ppt_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    ppt_attached_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sections: Mapped[list[TemplateSectionModel]] = relationship(
        "TemplateSectionModel", secondary=template_section_association,
        back_populates="templates", order_by="TemplateSectionModel.created_at",
    )
    reports: Mapped[list[ReportModel]] = relationship(
        "ReportModel", back_populates="template", passive_deletes=True, cascade="save-update, merge",
    )
