"""ReportSectionModel + ReportSectionElementModel."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.report_model import ReportModel


class ReportSectionModel(Base):
    __tablename__ = "report_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    sectionname_alias: Mapped[str] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    layout_preference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    report: Mapped[ReportModel] = relationship(back_populates="sections")
    elements: Mapped[list[ReportSectionElementModel]] = relationship(
        "ReportSectionElementModel", back_populates="section",
        cascade="all, delete-orphan", order_by="ReportSectionElementModel.display_order", lazy="joined",
    )


class ReportSectionElementModel(Base):
    __tablename__ = "report_section_elements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_section_id: Mapped[int] = mapped_column(ForeignKey("report_sections.id", ondelete="CASCADE"), index=True)
    element_type: Mapped[str] = mapped_column(String(32))
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    section_commentary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    section: Mapped[ReportSectionModel] = relationship(back_populates="elements")
