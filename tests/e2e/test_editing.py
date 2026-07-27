"""E2E Test: Text Editing Workflow

Tests the complete edit cycle:
- Select a block
- Edit its text
- Verify the edit is reflected
- Undo the edit
- Redo the edit
- Session tracks edits correctly
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
HSI_PDF = ICDS_DIR / "digital" / "HSI_SYS_015G.pdf"


@pytest.fixture
def client():
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    c.post(f"/document/open?pdf_path={HSI_PDF}")
    return c


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEditBlock:
    """Editing text blocks via the API."""

    def _get_first_block_id(self, client) -> str:
        """Helper to get the first block ID on page 1."""
        res = client.get("/document/page/1")
        data = res.json()
        blocks = data["blocks"]
        assert len(blocks) > 0, "No blocks on page 1"
        return blocks[0]["id"]

    def test_edit_block_succeeds(self, client):
        """PUT /document/block/{id} modifies the block text."""
        block_id = self._get_first_block_id(client)
        res = client.put(
            f"/document/block/{block_id}",
            json={"new_text": "Edited text content"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("edited", "updated")

    def test_edit_reflected_in_page_data(self, client):
        """After editing, GET /document/page shows the new text."""
        block_id = self._get_first_block_id(client)
        new_text = "Modified by test"

        client.put(f"/document/block/{block_id}", json={"new_text": new_text})

        res = client.get("/document/page/1")
        data = res.json()
        edited_block = next((b for b in data["blocks"] if b["id"] == block_id), None)
        assert edited_block is not None
        assert edited_block["text"] == new_text

    def test_edit_increments_count(self, client):
        """Each edit increments the session edit count."""
        block_id = self._get_first_block_id(client)

        client.put(f"/document/block/{block_id}", json={"new_text": "Edit 1"})
        client.put(f"/document/block/{block_id}", json={"new_text": "Edit 2"})

        res = client.get("/session")
        data = res.json()
        assert data["edit_count"] == 2

    def test_edit_nonexistent_block(self, client):
        """Editing a non-existent block ID returns an error."""
        res = client.put(
            "/document/block/nonexistent-id-999",
            json={"new_text": "Should fail"},
        )
        assert res.status_code in (404, 400)


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestUndoRedo:
    """Undo and redo operations."""

    def _edit_block(self, client, text: str):
        """Helper: edit the first block on page 1."""
        res = client.get("/document/page/1")
        block_id = res.json()["blocks"][0]["id"]
        client.put(f"/document/block/{block_id}", json={"new_text": text})
        return block_id

    def test_undo_reverts_edit(self, client):
        """POST /document/undo restores previous text."""
        res = client.get("/document/page/1")
        original_text = res.json()["blocks"][0]["text"]
        block_id = res.json()["blocks"][0]["id"]

        # Edit
        client.put(f"/document/block/{block_id}", json={"new_text": "Changed"})

        # Undo
        res = client.post("/document/undo")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "undone"

        # Verify reverted
        res = client.get("/document/page/1")
        current_text = next(
            b["text"] for b in res.json()["blocks"] if b["id"] == block_id
        )
        assert current_text == original_text

    def test_redo_restores_edit(self, client):
        """POST /document/redo re-applies an undone edit."""
        block_id = self._edit_block(client, "Redo test value")

        # Undo
        client.post("/document/undo")

        # Redo
        res = client.post("/document/redo")
        assert res.status_code == 200

        # Verify restored
        res = client.get("/document/page/1")
        current_text = next(
            b["text"] for b in res.json()["blocks"] if b["id"] == block_id
        )
        assert current_text == "Redo test value"

    def test_undo_with_nothing_to_undo(self, client):
        """Undo with no edits returns appropriate status."""
        res = client.post("/document/undo")
        # Should not crash — returns nothing_to_undo or similar
        assert res.status_code in (200, 400)

    def test_undo_redo_state_reported(self, client):
        """Actions endpoint reports undo/redo availability."""
        block_id = self._edit_block(client, "State test")

        res = client.get("/session/actions")
        data = res.json()
        assert data["undo_available"] is True
        assert data["redo_available"] is False

        client.post("/document/undo")
        res = client.get("/session/actions")
        data = res.json()
        assert data["undo_available"] is False
        assert data["redo_available"] is True
