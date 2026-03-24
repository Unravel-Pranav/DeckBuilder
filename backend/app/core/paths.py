"""Resolved filesystem paths relative to the backend app root (`backend/`)."""

from __future__ import annotations

from pathlib import Path


def backend_root() -> Path:
    """Directory containing `deckbuilder.db`, `data/`, and the `app` package."""
    return Path(__file__).resolve().parent.parent
