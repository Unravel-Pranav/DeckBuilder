from __future__ import annotations

import logging
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

import structlog
from hello.services.config import settings
from hello.services.json_logging import sanitize_event_dict, structlog_exception_formatter
from hello.services.logging_context import add_user_context


class _MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level
    

class _NoDebugFilter(logging.Filter):
    """Filter that drops DEBUG records to reduce noisy ingestion."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        return record.levelno > logging.DEBUG



class CustomLogger:
    _configured = False
    _configured_date: str | None = None
    _structlog_configured = False
    _structlog_fields: dict[str, str] = {}

    def __init__(self) -> None:
        self.base_dir_env = settings.BASE_DIR_ENV
        self.archive_dir_env = settings.ARCHIVE_DIR_ENV
        self.max_bytes = settings.MAX_BYTES
        self.backup_count = settings.BACKUP_COUNT
        self.console_level = settings.CONSOLE_LEVEL
        self.info_filename = settings.INFO_FILENAME
        self.error_filename = settings.ERROR_FILENAME
        self.current_date = settings.CURRENT_DATE
        self.log_extra_fields = {
            "service": "cbre-reports-api",
            "env": settings.env,
        }
        CustomLogger._structlog_fields = self.log_extra_fields

        if self.base_dir_env:
            base_dir_path = Path(self.base_dir_env).expanduser().resolve()
            self.base_dir = base_dir_path
            self.base_dir.mkdir(parents=True, exist_ok=True)

            if self.archive_dir_env:
                self.archive_dir = Path(self.archive_dir_env).expanduser().resolve()
            else:
                self.archive_dir = self.base_dir / "archives"
            self.archive_dir.mkdir(parents=True, exist_ok=True)

            self.current_dir = self.base_dir / self.current_date
            self.current_dir.mkdir(parents=True, exist_ok=True)

            self.info_file = (self.current_dir / self.info_filename).resolve()
            self.error_file = (self.current_dir / self.error_filename).resolve()
            self.file_logging_enabled = True
        else:
            self.base_dir = None
            self.archive_dir = None
            self.current_dir = None
            self.info_file = None
            self.error_file = None
            self.file_logging_enabled = False

    def _remove_handlers(self, handlers: Iterable[logging.Handler]) -> None:
        for handler in handlers:
            try:
                handler.flush()
            except Exception:
                pass
            try:
                handler.close()
            except Exception:
                pass

    def _archive_old_logs(self) -> None:
        if (
            not self.file_logging_enabled
            or not self.base_dir
            or not self.archive_dir
            or not self.base_dir.exists()
            or not self.archive_dir.exists()
        ):
            return
        for path in self.base_dir.iterdir():
            if not path.is_dir() or path.name == self.current_date:
                continue
            archive_base = self.archive_dir / path.name
            archive_path = archive_base.with_suffix(".zip")
            try:
                if not archive_path.exists():
                    shutil.make_archive(str(archive_base), "zip", root_dir=str(path))
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                continue

    @staticmethod
    def _add_structlog_fields(logger, method_name, event_dict):  # type: ignore[no-untyped-def]
        if CustomLogger._structlog_fields:
            event_dict.update(CustomLogger._structlog_fields)
        return event_dict

    def _configure_structlog(self) -> None:
        if CustomLogger._structlog_configured:
            return
        structlog.configure(
            processors=[
                add_user_context,  # Add user email and request_id from context
                CustomLogger._add_structlog_fields,
                structlog_exception_formatter,
                sanitize_event_dict,
                structlog.dev.ConsoleRenderer(colors=False),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        CustomLogger._structlog_configured = True

    def _configure_framework_loggers(self, formatter: logging.Formatter) -> None:
        for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uv_logger = logging.getLogger(logger_name)
            if not uv_logger.handlers:
                continue
            self._remove_handlers(uv_logger.handlers)
            uv_logger.handlers.clear()
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            uv_logger.addHandler(handler)

    def _configure_logging(self) -> None:
        self._archive_old_logs()
        root = logging.getLogger()
        self._remove_handlers(root.handlers)
        root.handlers.clear()
        # Silence Datadog SDK logs unless critical
        logging.getLogger('ddtrace').setLevel(logging.CRITICAL)

        formatter = logging.Formatter(settings.LOG_FORMAT)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.console_level, logging.INFO))
        console_handler.setFormatter(formatter)
        if settings.DISABLE_DEBUG_LOGS:
            console_handler.addFilter(_NoDebugFilter())
        root.addHandler(console_handler)

        if self.file_logging_enabled and self.info_file and self.error_file:
            info_handler = RotatingFileHandler(
                self.info_file,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
            )
            info_handler.setLevel(logging.INFO)
            info_handler.setFormatter(formatter)
            info_handler.addFilter(_MaxLevelFilter(logging.WARNING))
            if settings.DISABLE_DEBUG_LOGS:
                info_handler.addFilter(_NoDebugFilter())
            root.addHandler(info_handler)

            error_handler = RotatingFileHandler(
                self.error_file,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            if settings.DISABLE_DEBUG_LOGS:
                error_handler.addFilter(_NoDebugFilter())
            root.addHandler(error_handler)

        root.setLevel(logging.INFO)
        self._configure_framework_loggers(formatter)
        CustomLogger._configured = True
        CustomLogger._configured_date = self.current_date

    def get_logger(self, name: str = __file__):
        if (
            not CustomLogger._configured
            or CustomLogger._configured_date != self.current_date
        ):
            self._configure_logging()
        self._configure_structlog()
        logger_name = Path(name).stem
        return structlog.get_logger(logger_name)
