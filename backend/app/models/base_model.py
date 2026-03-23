"""Base model + SQLite/Postgres array compatibility type."""

from __future__ import annotations

import json

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import TEXT as PG_TEXT, ARRAY

from app.core.database import Base


class ArrayOfText(TypeDecorator):
    """Store lists as Postgres ARRAYs or JSON strings on SQLite."""

    impl = ARRAY(PG_TEXT)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "sqlite":
            return Text()
        return ARRAY(PG_TEXT)

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "sqlite":
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return [] if dialect.name == "sqlite" else value
        if dialect.name == "sqlite":
            try:
                return json.loads(value)
            except Exception:
                return []
        return value


__all__ = ["Base", "ArrayOfText"]
