"""Lightweight SQLite migrations when Alembic is not configured."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


def migrate_generated_reports(connection: Connection) -> None:
    """Ensure generated_reports has columns required for durable downloads."""
    inspector = inspect(connection)
    if "generated_reports" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("generated_reports")}

    if "file_id" not in columns:
        connection.execute(
            text("ALTER TABLE generated_reports ADD COLUMN file_id VARCHAR(36)")
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_generated_reports_file_id "
                "ON generated_reports (file_id)"
            )
        )
    if "filename" not in columns:
        connection.execute(
            text(
                "ALTER TABLE generated_reports ADD COLUMN filename VARCHAR(512) "
                "DEFAULT 'presentation.pptx'"
            )
        )
    if "presentation_name" not in columns:
        connection.execute(
            text("ALTER TABLE generated_reports ADD COLUMN presentation_name VARCHAR(255)")
        )
    if "expires_at" not in columns:
        connection.execute(
            text("ALTER TABLE generated_reports ADD COLUMN expires_at DATETIME")
        )

    if "file_path" in columns:
        row = connection.execute(
            text(
                "SELECT COUNT(*) FROM generated_reports "
                "WHERE file_id IS NULL AND file_path IS NOT NULL"
            )
        ).scalar()
        if row and row > 0:
            connection.execute(
                text(
                    "UPDATE generated_reports SET file_id = CAST(id AS TEXT) "
                    "WHERE file_id IS NULL"
                )
            )


def migrate_drafts(connection: Connection) -> None:
    """Ensure drafts table has status and generated_file_id columns."""
    inspector = inspect(connection)
    if "drafts" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("drafts")}
    if "status" not in columns:
        connection.execute(
            text("ALTER TABLE drafts ADD COLUMN status VARCHAR(32) DEFAULT 'draft'")
        )
    if "generated_file_id" not in columns:
        connection.execute(
            text("ALTER TABLE drafts ADD COLUMN generated_file_id VARCHAR(36)")
        )
