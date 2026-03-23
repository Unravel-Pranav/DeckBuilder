"""Template Pydantic schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class TemplateSectionElementCreate(BaseModel):
    element_type: Literal["chart", "table", "commentary"]
    display_order: int = 0
    config: dict = Field(default_factory=dict)

class TemplateSectionElementResponse(BaseModel):
    id: int
    section_id: int
    element_type: str
    display_order: int
    config: dict = Field(default_factory=dict)
    created_at: datetime
    class Config:
        from_attributes = True

class TemplateSectionCreate(BaseModel):
    name: str
    sectionname_alias: str
    label: Optional[str] = None
    property_type: str
    property_sub_type: Optional[str] = None
    default_prompt: Optional[str] = None
    chart_config: Optional[dict] = None
    table_config: Optional[dict] = None
    slide_layout: Optional[str] = None
    mode: Optional[str] = None
    elements: Optional[list[TemplateSectionElementCreate]] = None

class TemplateSectionResponse(BaseModel):
    id: int
    name: str
    sectionname_alias: str
    label: Optional[str] = None
    property_type: str
    property_sub_type: Optional[str] = None
    default_prompt: Optional[str] = None
    chart_config: Optional[dict] = None
    table_config: Optional[dict] = None
    slide_layout: Optional[str] = None
    mode: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    template_ids: list[int] = Field(default_factory=list)
    elements: list[TemplateSectionElementResponse] = Field(default_factory=list)
    class Config:
        from_attributes = True

class TemplateSectionUpdate(BaseModel):
    name: Optional[str] = None
    sectionname_alias: Optional[str] = None
    label: Optional[str] = None
    property_type: Optional[str] = None
    property_sub_type: Optional[str] = None
    default_prompt: Optional[str] = None
    chart_config: Optional[dict] = None
    table_config: Optional[dict] = None
    slide_layout: Optional[str] = None
    mode: Optional[str] = None
    elements: Optional[list[TemplateSectionElementCreate]] = None

class TemplateCreate(BaseModel):
    name: str
    base_type: str
    is_default: bool = False
    attended: bool = True
    sections: list[TemplateSectionCreate] = Field(default_factory=list)

class TemplateResponse(BaseModel):
    id: int
    name: str
    base_type: str
    is_default: bool
    attended: bool
    ppt_status: str
    ppt_attached_time: datetime | None = None
    ppt_url: Optional[str] = None
    created_at: datetime
    last_modified: datetime
    class Config:
        from_attributes = True

class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    base_type: Optional[str] = None
    is_default: Optional[bool] = None
    attended: Optional[bool] = None

class TemplateDetailResponse(TemplateResponse):
    sections: list[TemplateSectionResponse] = Field(default_factory=list)

class TemplateListResponse(BaseModel):
    total_count: int
    items: list[TemplateResponse] = Field(default_factory=list)
