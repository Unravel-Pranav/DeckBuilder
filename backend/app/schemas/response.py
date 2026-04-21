"""Standardized API response schemas."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error details for failed responses."""

    message: str
    details: list[str] | None = None


class ApiResponse(BaseModel, Generic[T]):
    """
    Standardized API response wrapper.

    Success response:
    {
        "success": true,
        "error_code": null,
        "data": { ... },
        "error": null
    }

    Error response:
    {
        "success": false,
        "error_code": "VALIDATION_FAILED",
        "data": null,
        "error": {
            "message": "Invalid input parameters.",
            "details": ["Field 'email' is required"]
        }
    }
    """

    success: bool
    error_code: str | None = None
    data: T | None = None
    error: ErrorDetail | None = None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        """Create a success response."""
        return cls(success=True, error_code=None, data=data, error=None)

    @classmethod
    def fail(
        cls,
        error_code: str,
        message: str,
        details: list[str] | None = None,
    ) -> "ApiResponse[None]":
        """Create an error response."""
        return cls(
            success=False,
            error_code=error_code,
            data=None,
            error=ErrorDetail(message=message, details=details),
        )


class ErrorCodes:
    """Standard error codes used across the API."""

    VALIDATION_FAILED = "VALIDATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    GENERATION_FAILED = "GENERATION_FAILED"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    BAD_REQUEST = "BAD_REQUEST"
    AGENT_ORCHESTRATION_FAILED = "AGENT_ORCHESTRATION_FAILED"
    DATA_INGESTION_FAILED = "DATA_INGESTION_FAILED"


def success_response(data: Any) -> dict:
    """Helper to create a success response dict."""
    return {
        "success": True,
        "error_code": None,
        "data": data,
        "error": None,
    }


def error_response(
    error_code: str,
    message: str,
    details: list[str] | None = None,
) -> dict:
    """Helper to create an error response dict."""
    return {
        "success": False,
        "error_code": error_code,
        "data": None,
        "error": {
            "message": message,
            "details": details,
        },
    }
