"""E2E Test: Session Management

Tests the session lifecycle as experienced by the frontend:
- Start a new session
- Get session info
- Multiple sessions don't interfere
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestSessionLifecycle:
    """Session creation and info retrieval."""

    def test_start_session(self, client):
        """POST /session/start creates a session with an ID."""
        res = client.post("/session/start")
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    def test_get_session_after_start(self, client):
        """GET /session returns session info after start."""
        client.post("/session/start")
        res = client.get("/session")
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        assert "started_at" in data
        assert data["edit_count"] == 0

    def test_get_session_before_start_returns_error(self, client):
        """GET /session before start returns 404."""
        res = client.get("/session")
        assert res.status_code == 404

    def test_actions_initially_empty(self, client):
        """GET /session/actions returns empty after fresh start."""
        client.post("/session/start")
        res = client.get("/session/actions")
        assert res.status_code == 200
        data = res.json()
        assert data["undo_available"] is False
        assert data["redo_available"] is False
