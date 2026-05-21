"""Draft API contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_missing_draft_returns_404() -> None:
    response = client.get("/api/v1/drafts/nonexistent-draft-id-00000000")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "NOT_FOUND"
