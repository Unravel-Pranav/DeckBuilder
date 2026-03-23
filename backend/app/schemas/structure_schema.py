"""Structure generation schemas."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class TemplateSuggestionInput(BaseModel):
    id: str
    name: str
    type: str
    layout: str

class SectionInput(BaseModel):
    id: str
    name: str
    description: str = ""
    suggested_templates: list[TemplateSuggestionInput] = []

class StructureGenerateRequest(BaseModel):
    intent_type: str = "financial"
    intent_tone: str = "formal"
    sections: list[SectionInput]

class GeneratedElementResponse(BaseModel):
    element_type: str
    label: Optional[str] = None
    display_order: int = 0
    config: dict = Field(default_factory=dict)

class GeneratedSectionResponse(BaseModel):
    name: str
    sectionname_alias: str
    display_order: int = 0
    elements: list[GeneratedElementResponse] = []

class StructureGenerateResponse(BaseModel):
    sections: list[GeneratedSectionResponse]
    total_elements: int = 0
