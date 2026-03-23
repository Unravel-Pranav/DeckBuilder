from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

def get_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if not rid:
        rid = uuid.uuid4().hex
        try:
            request.state.request_id = rid
        except Exception:
            pass
    return str(rid)


def error_payload(message: str, *, code: str, request_id: str, details: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def json_error(request: Request, status: int, message: str, *, code: str, details: Any | None = None) -> JSONResponse:
    rid = get_request_id(request)
    body = error_payload(message, code=code, request_id=rid, details=details)
    return JSONResponse(status_code=status, content=body)
