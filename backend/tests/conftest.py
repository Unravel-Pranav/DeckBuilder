"""Apply SQLite schema migrations before tests run."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.config import settings
from app.core.db_migrate import migrate_drafts, migrate_generated_reports


@pytest.fixture(scope="session", autouse=True)
def apply_sqlite_migrations() -> None:
    """Ensure draft/generated_reports columns exist on the configured database."""
    url = settings.database_url.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(url)
    with engine.begin() as conn:
        migrate_generated_reports(conn)
        migrate_drafts(conn)
