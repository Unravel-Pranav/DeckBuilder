"""Report Pydantic schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class ReportSectionElementCreate(BaseModel):
    element_type: str
    label: Optional[str] = None
    selected: bool = True
    display_order: int = 0
    config: Optional[dict] = None

class ReportSectionElementResponse(BaseModel):
    id: int
    element_type: str
    label: Optional[str] = None
    selected: bool
    display_order: int
    config: dict = Field(default_factory=dict)
    section_commentary: Optional[str] = None
    class Config:
        from_attributes = True

class ReportSectionCreate(BaseModel):
    key: str
    name: str
    sectionname_alias: Optional[str] = None
    display_order: int = 0
    selected: bool = True
    layout_preference: Optional[str] = None
    elements: list[ReportSectionElementCreate] = Field(default_factory=list)

class ReportSectionResponse(BaseModel):
    id: int
    key: str
    name: str
    sectionname_alias: str
    display_order: int
    selected: bool
    layout_preference: Optional[str] = None
    elements: list[ReportSectionElementResponse] = Field(default_factory=list)
    class Config:
        from_attributes = True

class ReportCreate(BaseModel):
    name: str
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    report_type: Optional[str] = None
    status: Optional[str] = "Draft"
    division: list[str] | str = Field(default_factory=list)
    publishing_group: str = ""
    property_type: str = ""
    property_sub_type: Optional[str] = None
    automation_mode: str = "Attended"
    quarter: Optional[str] = None
    defined_markets: list[str] = Field(default_factory=list)
    sections: list[ReportSectionCreate] = Field(default_factory=list)

class ReportUpdate(BaseModel):
    name: Optional[str] = None
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    report_type: Optional[str] = None
    status: Optional[str] = None
    division: Optional[list[str] | str] = None
    publishing_group: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    automation_mode: Optional[str] = None
    quarter: Optional[str] = None
    defined_markets: Optional[list[str]] = None
    sections: Optional[list[ReportSectionCreate]] = None

class ReportResponse(BaseModel):
    id: int
    name: str
    status: str
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    report_type: Optional[str] = None
    division: list[str] = Field(default_factory=list)
    publishing_group: str
    property_type: str
    property_sub_type: Optional[str] = None
    automation_mode: str
    quarter: Optional[str] = None
    defined_markets: Optional[list[str]] = None
    hero_fields: Optional[dict[str, Any]] = None
    ppt_url: Optional[list[dict]] = None
    created_at: datetime
    updated_at: datetime
    sections: list[ReportSectionResponse] = Field(default_factory=list)
    class Config:
        from_attributes = True

class ReportListResponse(BaseModel):
    total_count: int
    items: list[ReportResponse] = Field(default_factory=list)
