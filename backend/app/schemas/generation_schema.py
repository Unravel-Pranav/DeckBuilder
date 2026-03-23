"""PPT generation schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class GeneratedReportResponse(BaseModel):
    id: int
    report_id: Optional[int] = None
    status: str
    file_path: Optional[str] = None
    duration_seconds: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True
