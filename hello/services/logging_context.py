"""
Logging context utilities for automatic email inclusion in all log messages.

This module provides context variables and structlog processors to automatically
include user email in all log messages without requiring explicit inclusion.

Usage:
    - Call set_user_email(email) at the start of request processing (middleware)
    - All subsequent logs will automatically include the email field
    - Call clear_user_email() at the end of request processing
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

# Context variable to store the current user's email for logging
_user_email_var: ContextVar[str | None] = ContextVar("user_email", default=None)
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_user_email(email: str | None) -> None:
    """Set the current user's email for logging context."""
    _user_email_var.set(email)


def get_user_email() -> str | None:
    """Get the current user's email from logging context."""
    return _user_email_var.get()


def clear_user_email() -> None:
    """Clear the user email from logging context."""
    _user_email_var.set(None)


def set_request_id(request_id: str | None) -> None:
    """Set the current request ID for logging context."""
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Get the current request ID from logging context."""
    return _request_id_var.get()


def clear_request_id() -> None:
    """Clear the request ID from logging context."""
    _request_id_var.set(None)


def add_user_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Structlog processor that adds user context to log events.
    
    This processor automatically adds:
    - user_email: The email of the current user (from context variable)
    - request_id: The current request ID (from context variable)
    """
    email = get_user_email()
    request_id = get_request_id()
    
    # Add email (use "-" for unauthenticated/missing)
    event_dict["user_email"] = email if email else "-"
    
    # Add request_id if available
    if request_id:
        event_dict["request_id"] = request_id
    
    return event_dict


def extract_email_from_request(request: "Request") -> str | None:
    """
    Extract user email from request JWT token.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        User email string or None if not available/invalid token
    """
    # Import here to avoid circular imports
    from hello.utils.auth_utils import (
        read_app_jwt_from_request,
        decode_app_jwt,
        extract_email_from_claims,
    )
    
    token = read_app_jwt_from_request(request)
    if not token:
        return None
    
    try:
        claims = decode_app_jwt(token)
        return extract_email_from_claims(claims)
    except Exception:
        # Invalid token - email will be null, request will fail auth later
        return None

