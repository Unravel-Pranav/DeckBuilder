"""Schemas for PPT generation endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class GenerateReportMeta(BaseModel):
    id: Optional[str | int] = None
    name: str = "Presentation"
    template_id: Optional[int] = None
    property_type: str = "Office"
    property_sub_type: str = "figures"
    quarter: str = ""


class GenerateSectionElement(BaseModel):
    id: Optional[str | int] = None
    element_type: str
    label: Optional[str] = None
    display_order: int = 0
    slide_group: Optional[int] = None
    config: dict[str, Any] = Field(default_factory=dict)


class GenerateSection(BaseModel):
    id: Optional[str | int] = None
    name: str
    display_order: int = 0
    layout_preference: str = "Content (2x2 Grid)"
    elements: list[GenerateSectionElement] = Field(default_factory=list)


class GenerateCustomRequest(BaseModel):
    report: GenerateReportMeta
    sections: list[GenerateSection] = Field(default_factory=list)
