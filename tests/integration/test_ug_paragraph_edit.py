"""User Guide Regression: Basic Paragraph Edit (Section 4.1 + 4.2)

Validates the core editing workflow described in the User Guide:
- Click block -> edit text -> apply -> view updates
- Undo reverts the edit
- Redo reapplies the edit
- Edit count increments after each apply
- Page image changes after edit
- Resolving a TBR by editing a block (Section 4.2)

Tests use HSI_SYS_015G.pdf page 5, which has editable paragraphs and TBR markers.
"""

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _fresh_client(pdf_path: Path) -> TestClient:
    """Create a test client with an isolated copy of the PDF."""
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    test_copy = output_dir / f".test_edit_{uuid.uuid4().hex[:8]}_{pdf_path.name}"
    shutil.copy2(str(pdf_path), str(test_copy))

    app = create_app()
    client = TestClient(app)
    client.post("/session/start")
    res = client.post(f"/document/open?pdf_path={test_copy}")
    assert res.status_code == 200
    return client


def _get_first_editable_block(client: TestClient, page_num: int) -> dict | None:
    """Get the first editable block (paragraph/heading/caption) on a page."""
    res = client.get(f"/document/page/{page_num}/elements")
    assert res.status_code == 200
    elements = res.json()["elements"]
    for elem in elements:
        if elem["id"] and elem.get("type") in ("paragraph", "heading", "caption"):
            return elem
    return None


def _get_block_by_id(client: TestClient, page_num: int, block_id: str) -> dict | None:
    """Find a specific block by ID in page elements."""
    res = client.get(f"/document/page/{page_num}/elements")
    assert res.status_code == 200
    elements = res.json()["elements"]
    for elem in elements:
        if elem["id"] == block_id:
            return elem
    return None


# ─── Document Shows Elements ──────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestOpenDocumentShowsElements:
    """Verify that opening a document exposes clickable/editable blocks."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_open_document_shows_elements(self, client):
        """Page elements endpoint returns blocks that can be clicked/edited."""
        res = client.get("/document/page/5/elements")
        assert res.status_code == 200
        data = res.json()
        assert "elements" in data
        assert len(data["elements"]) > 0

    def test_elements_have_required_fields(self, client):
        """Each element has id, text, type, and bbox."""
        res = client.get("/document/page/5/elements")
        elements = res.json()["elements"]
        for elem in elements:
            assert "id" in elem
            assert "text" in elem
            assert "type" in elem
            assert "bbox" in elem

    def test_at_least_one_editable_block(self, client):
        """Page 5 has at least one editable paragraph or heading."""
        block = _get_first_editable_block(client, 5)
        assert block is not None, "No editable block found on page 5"


# ─── Edit Block Changes Text ──────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEditBlockChangesText:
    """Verify that editing a block updates its text content."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_edit_block_changes_text(self, client):
        """PUT /document/block/{id} with new_text succeeds and returns expected fields."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        block_id = block["id"]
        original_text = block["text"]

        new_text = "REGRESSION_TEST_EDIT_MARKER_001"
        res = client.put(
            f"/document/block/{block_id}",
            json={"new_text": new_text},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "updated"
        assert data["old_text"] == original_text
        assert data["new_text"] == new_text

    def test_edited_text_in_page_elements(self, client):
        """After edit, GET elements shows the new text for the edited block."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        block_id = block["id"]

        new_text = "VERIFY_ELEMENT_UPDATE_XYZ"
        client.put(
            f"/document/block/{block_id}",
            json={"new_text": new_text},
        )

        # Re-read elements and verify the block text changed
        updated_block = _get_block_by_id(client, 5, block_id)
        assert updated_block is not None, "Edited block not found after edit"
        assert updated_block["text"] == new_text


# ─── Page Image Changes After Edit ────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPageImageChangesAfterEdit:
    """Verify that the page image updates after an edit is applied."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_page_image_changes_after_edit(self, client):
        """GET page image returns different bytes after an edit."""
        # Get image before
        img_before = client.get("/document/page/5/image")
        assert img_before.status_code == 200
        assert img_before.content[:8] == PNG_MAGIC

        # Edit a block
        block = _get_first_editable_block(client, 5)
        assert block is not None
        client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "IMAGE_CHANGE_TEST_MARKER"},
        )

        # Get image after
        img_after = client.get("/document/page/5/image")
        assert img_after.status_code == 200
        assert img_after.content[:8] == PNG_MAGIC

        assert img_before.content != img_after.content, (
            "Page image did not change after block edit"
        )


# ─── Undo Reverts Edit ────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestUndoRevertsEdit:
    """Verify that undo restores the original text."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_undo_reverts_edit(self, client):
        """POST /document/undo restores original text after an edit."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        block_id = block["id"]
        original_text = block["text"]

        # Edit the block
        client.put(
            f"/document/block/{block_id}",
            json={"new_text": "UNDO_TEST_TEXT"},
        )

        # Undo
        undo_res = client.post("/document/undo")
        assert undo_res.status_code == 200
        assert undo_res.json()["status"] == "undone"

        # Verify text reverted
        restored_block = _get_block_by_id(client, 5, block_id)
        assert restored_block is not None
        assert restored_block["text"] == original_text


# ─── Redo Reapplies Edit ──────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestRedoReappliesEdit:
    """Verify that redo brings back a previously undone edit."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_redo_reapplies_edit(self, client):
        """POST /document/redo brings back the edit after undo."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        block_id = block["id"]

        edit_text = "REDO_TEST_TEXT_999"
        client.put(
            f"/document/block/{block_id}",
            json={"new_text": edit_text},
        )

        # Undo, then redo
        client.post("/document/undo")
        redo_res = client.post("/document/redo")
        assert redo_res.status_code == 200
        assert redo_res.json()["status"] == "redone"

        # Verify text is the edited version again
        block_after = _get_block_by_id(client, 5, block_id)
        assert block_after is not None
        assert block_after["text"] == edit_text


# ─── Edit Count Increments ────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEditCountIncrements:
    """Verify that session edit_count increases with each edit."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_edit_count_increments(self, client):
        """Session edit_count increases after each apply."""
        # Check initial count
        session_res = client.get("/session")
        assert session_res.status_code == 200
        initial_count = session_res.json()["edit_count"]

        # Make first edit
        block = _get_first_editable_block(client, 5)
        assert block is not None
        client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "COUNT_TEST_1"},
        )

        session_res = client.get("/session")
        count_after_1 = session_res.json()["edit_count"]
        assert count_after_1 == initial_count + 1

        # Make second edit
        client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "COUNT_TEST_2"},
        )

        session_res = client.get("/session")
        count_after_2 = session_res.json()["edit_count"]
        assert count_after_2 == initial_count + 2


# ─── Resolve TBR by Editing Block (Section 4.2) ──────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestResolveTBRByEditing:
    """Verify that editing a block to remove a TBR marker resolves it."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def _find_tbr_block(self, client: TestClient) -> tuple[int, dict] | None:
        """Find a block containing a TBR marker across pages."""
        for page_num in range(1, 9):  # HSI has 8 pages
            res = client.get(f"/document/page/{page_num}/elements")
            if res.status_code != 200:
                continue
            elements = res.json()["elements"]
            for elem in elements:
                if elem["id"] and "TBR" in elem.get("text", ""):
                    return (page_num, elem)
        return None

    def test_resolve_tbr_by_editing_block(self, client):
        """Replace TBR marker text with a resolved value."""
        result = self._find_tbr_block(client)
        if result is None:
            pytest.skip("No TBR marker found in HSI document")

        page_num, block = result
        block_id = block["id"]
        original_text = block["text"]

        # Replace TBR with a resolved value
        resolved_text = original_text.replace("TBR", "0.5")
        res = client.put(
            f"/document/block/{block_id}",
            json={"new_text": resolved_text},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "updated"

        # Verify the block no longer contains "TBR"
        updated_block = _get_block_by_id(client, page_num, block_id)
        assert updated_block is not None
        assert "TBR" not in updated_block["text"], (
            f"TBR still present after resolution: {updated_block['text'][:80]}"
        )

    def test_resolved_tbr_removed_from_tbd_scan(self, client):
        """After editing away a TBR, a fresh IR scan doesn't find that TBR."""
        result = self._find_tbr_block(client)
        if result is None:
            pytest.skip("No TBR marker found in HSI document")

        page_num, block = result
        block_id = block["id"]
        original_text = block["text"]

        # Find the specific TBR ID (e.g., "TBR-UCB-102")
        import re
        tbr_match = re.search(r"(TBR-\w+-\d+)", original_text)
        if not tbr_match:
            pytest.skip("No structured TBR ID found in block text")
        tbr_id = tbr_match.group(1)

        # Resolve it
        resolved_text = original_text.replace(tbr_id, "0.5")
        client.put(
            f"/document/block/{block_id}",
            json={"new_text": resolved_text},
        )

        # Scan all blocks for the TBR ID — it should be gone
        found = False
        for pg in range(1, 9):
            res = client.get(f"/document/page/{pg}/elements")
            if res.status_code != 200:
                continue
            for elem in res.json()["elements"]:
                if tbr_id in elem.get("text", ""):
                    found = True
                    break
            if found:
                break

        assert not found, f"TBR '{tbr_id}' still found in document after resolution"
