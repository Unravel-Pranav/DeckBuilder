"""AI recommendation + commentary schemas."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class RecommendationRequest(BaseModel):
    type: str = "financial"
    audience: str = ""
    tone: str = "formal"

class TemplateRecommendationResponse(BaseModel):
    id: str
    name: str
    type: str
    layout: str
    preview_description: str = ""

class SectionRecommendationResponse(BaseModel):
    id: str
    name: str
    description: str
    suggested_templates: list[TemplateRecommendationResponse]
    accepted: bool = True

class AiRecommendationResponse(BaseModel):
    sections: list[SectionRecommendationResponse]
    suggested_style: str
    suggested_chart_types: list[str]

class CommentaryRequest(BaseModel):
    component_type: str = "default"
    section_name: Optional[str] = None
    intent_type: Optional[str] = None
    intent_tone: Optional[str] = None
    prompt: Optional[str] = None

class CommentaryResponse(BaseModel):
    commentary: str
