from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict

from hello.services.logging_context import get_request_id, get_user_email

_STANDARD_LOG_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}

_CONTROL_CHAR_MAP = {
    ord("\n"): "\\n",
    ord("\r"): "\\r",
    ord("\t"): "\\t",
}


def _get_user_context_fields() -> Dict[str, Any]:
    """Return logging context fields derived from request-scoped context vars."""
    email = get_user_email()
    request_id = get_request_id()
    context: Dict[str, Any] = {"user_email": email or "-"}
    if request_id:
        context["request_id"] = request_id
    return context


def render_json(payload: Any, *, default=None, **json_kwargs) -> str:
    if "separators" not in json_kwargs:
        json_kwargs["separators"] = (",", ":")
    return json.dumps(payload, default=default, **json_kwargs)


def _sanitize_str(value: str) -> str:
    return value.translate(_CONTROL_CHAR_MAP)


def _serialize_value(value: Any) -> Any:
    """Best-effort serialization for arbitrary logging extras."""
    if value is None:
        return value

    if isinstance(value, str):
        return _sanitize_str(value)

    if isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(v) for v in value]

    return repr(value)


def _format_stack(stack: str | list[str]) -> list[str]:
    if isinstance(stack, str):
        lines = stack.splitlines()
    else:
        lines = stack
    return [_sanitize_str(line.rstrip("\r\n")) for line in lines if line]


def format_exception_dict(exc_info: tuple[Any, Any, Any] | bool | None) -> Dict[str, Any] | None:
    if not exc_info:
        return None
    if exc_info is True:
        exc_info = sys.exc_info()
    if not isinstance(exc_info, tuple) or len(exc_info) != 3:
        return None
    exc_type, exc_value, exc_tb = exc_info
    formatted = traceback.format_exception(exc_type, exc_value, exc_tb)
    stack_lines = _format_stack(formatted)
    return {
        "type": exc_type.__name__ if exc_type else None,
        "message": _sanitize_str(str(exc_value)) if exc_value else None,
        "stack": stack_lines,
    }


def structlog_exception_formatter(logger: Any, method_name: str, event_dict: Dict[str, Any]):
    exc_info = event_dict.pop("exc_info", None)
    exc_payload = format_exception_dict(exc_info)
    if exc_payload:
        event_dict["exception"] = exc_payload

    stack = event_dict.pop("stack_info", None)
    if stack:
        event_dict["stack"] = _format_stack(stack)
    return event_dict


def sanitize_event_dict(logger: Any, method_name: str, event_dict: Dict[str, Any]):
    for key, value in list(event_dict.items()):
        event_dict[key] = _serialize_value(value)
    return event_dict


class JsonFormatter(logging.Formatter):
    """Formatter that emits structured JSON for every log record."""

    def __init__(self, *, extra_fields: Dict[str, Any] | None = None) -> None:
        super().__init__()
        self.extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        message = _sanitize_str(record.message) if isinstance(record.message, str) else record.message
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "pathname": record.pathname,
            "lineno": record.lineno,
            "func": record.funcName,
            **self.extra_fields,
        }
        payload.update(_get_user_context_fields())

        exc_payload = format_exception_dict(record.exc_info)
        if exc_payload:
            payload["exception"] = exc_payload
        elif record.exc_text:
            payload["exception"] = _sanitize_str(record.exc_text)

        if record.stack_info:
            payload["stack"] = _format_stack(record.stack_info)

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_FIELDS:
                continue
            payload[key] = _serialize_value(value)

        return render_json(payload)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802 - override signature
        ct = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return ct.strftime(datefmt)
        ts = ct.isoformat(timespec="milliseconds")
        if ts.endswith("+00:00"):
            ts = ts[:-6] + "Z"
        return ts

    # formatException intentionally unused; format_exception_dict handles data assembly
