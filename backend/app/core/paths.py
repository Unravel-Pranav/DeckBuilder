"""Resolved filesystem paths relative to the backend app root (`backend/`)."""

from __future__ import annotations

from pathlib import Path


def backend_root() -> Path:
    """Directory containing `autodeck.db`, `data/`, and the `app` package."""
    return Path(__file__).resolve().parent.parent


def resolve_data_dir(relative: str) -> Path:
    """Resolve a config-relative data path under the backend root."""
    path = Path(relative)
    if path.is_absolute():
        return path
    return backend_root() / path


def uploads_dir() -> Path:
    """Absolute path to uploaded agent CSV/XLSX files."""
    from app.core.config import settings

    return resolve_data_dir(settings.upload_dir)
