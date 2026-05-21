"""Generation request validation tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_generate_custom_rejects_empty_body() -> None:
    response = client.post("/api/v1/generation/generate-custom", json={})
    assert response.status_code == 422
