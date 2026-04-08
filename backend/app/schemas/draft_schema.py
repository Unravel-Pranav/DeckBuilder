"""Draft Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DraftSave(BaseModel):
    """Payload sent from the frontend to save/update a draft."""

    id: str = Field(..., min_length=1, max_length=36)
    name: str = "Untitled Presentation"
    current_step: str = "create"
    state: dict[str, Any] = Field(
        ...,
        description="Opaque JSON blob containing presentation, slides, ai, and ui store snapshots",
    )


class DraftResponse(BaseModel):
    id: str
    name: str
    current_step: str
    state: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DraftListItem(BaseModel):
    id: str
    name: str
    current_step: str
    updated_at: datetime

    class Config:
        from_attributes = True


class DraftListResponse(BaseModel):
    total_count: int
    items: list[DraftListItem] = Field(default_factory=list)
