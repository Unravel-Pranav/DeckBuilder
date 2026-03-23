"""TemplateSectionModel + TemplateSectionElementModel."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.template_model import TemplateModel

from app.models.template_model import template_section_association


class TemplateSectionModel(Base):
    __tablename__ = "template_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    sectionname_alias: Mapped[str] = mapped_column(String(255))
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    property_type: Mapped[str] = mapped_column(String(64))
    property_sub_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    slide_layout: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    default_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chart_config: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    table_config: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    templates: Mapped[list[TemplateModel]] = relationship(
        "TemplateModel", secondary=template_section_association, back_populates="sections",
    )
    elements: Mapped[list[TemplateSectionElementModel]] = relationship(
        "TemplateSectionElementModel", back_populates="section",
        cascade="all, delete-orphan", order_by="TemplateSectionElementModel.display_order",
    )

    @property
    def template_ids(self) -> list[int]:
        return [tpl.id for tpl in self.templates]


class TemplateSectionElementModel(Base):
    __tablename__ = "template_section_elements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("template_sections.id", ondelete="CASCADE"), index=True)
    element_type: Mapped[str] = mapped_column(String(32))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    section: Mapped[TemplateSectionModel] = relationship(back_populates="elements")
