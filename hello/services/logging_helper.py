from __future__ import annotations

import logging

from hello.services.config import settings

class _NoDebugFilter(logging.Filter):
    """Filter that drops DEBUG records to keep telemetry lean."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - match logging API
        return record.levelno > logging.DEBUG



def _apply_formatter(
    logger: logging.Logger,
    formatter: logging.Formatter,
    *,
    set_level: int | None = None,
) -> None:
    """Ensure every handler on the logger uses the provided formatter."""
    if logger.handlers:
        for handler in logger.handlers:
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    if set_level is not None:
        logger.setLevel(set_level)


def setup_logging(level: int | str = logging.INFO) -> None:
    """Ensure root and framework loggers emit plain, human-readable logs."""
    root = logging.getLogger()
    try:
        lvl = (
            logging._nameToLevel.get(str(level).upper(), logging.INFO)
            if isinstance(level, str)
            else int(level)
        )  # type: ignore[attr-defined]
    except Exception:
        lvl = logging.INFO

    formatter = logging.Formatter(settings.LOG_FORMAT)
    debug_filter = _NoDebugFilter() if settings.DISABLE_DEBUG_LOGS else None
    _apply_formatter(root, formatter, set_level=lvl)
    # Silence Datadog SDK noise unless it is critical
    logging.getLogger("ddtrace").setLevel(logging.CRITICAL)
    if debug_filter:
        for handler in root.handlers:
            handler.addFilter(debug_filter)
    
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        framework_logger = logging.getLogger(logger_name)
        _apply_formatter(framework_logger, formatter)
        if debug_filter:
            for handler in framework_logger.handlers:
                handler.addFilter(debug_filter)
