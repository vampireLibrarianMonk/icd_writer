"""E2E Test: Page Extension via Edit

Tests that editing a text block which causes overflow
triggers page creation through the API.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not available")
class TestPageExtensionViaEdit:
    """Editing text that overflows creates a new page."""

    def _open_doc(self, client):
        """Helper: start session and open HSI document."""
        client.post("/session/start")
        res = client.post(f"/document/open?pdf_path={HSI_PDF}")
        assert res.status_code == 200
        return res.json()

    def test_massive_edit_adds_page(self, client):
        """Expanding a block massively adds a page to the document."""
        doc_info = self._open_doc(client)
        original_pages = doc_info["pages"]

        # Get page 4 blocks
        page_res = client.get("/document/page/4")
        assert page_res.status_code == 200
        blocks = page_res.json()["blocks"]
        assert len(blocks) > 0

        # Find a body block (not header/footer)
        target_block = None
        for b in blocks:
            if b["type"] == "paragraph" and b["bbox"]["y0"] > 60:
                target_block = b
                break

        if not target_block:
            pytest.skip("No paragraph block found on page 4")

        # Massive expansion
        massive_text = "The spectrometer thermal requirement shall be verified. " * 100
        edit_res = client.put(
            f"/document/block/{target_block['id']}",
            json={"new_text": massive_text},
        )
        assert edit_res.status_code == 200
        data = edit_res.json()

        assert data["status"] == "updated"
        assert data["total_pages"] > original_pages
        assert data["reflow"]["page_added"] is True
        assert data["reflow"]["new_page_number"] is not None
        assert data["reflow"]["overflow_pt"] == 0.0  # Resolved

    def test_small_edit_no_extra_page(self, client):
        """A small edit doesn't create extra pages."""
        doc_info = self._open_doc(client)
        original_pages = doc_info["pages"]

        page_res = client.get("/document/page/1")
        blocks = page_res.json()["blocks"]

        if not blocks:
            pytest.skip("No blocks on page 1")

        edit_res = client.put(
            f"/document/block/{blocks[0]['id']}",
            json={"new_text": "Minor change."},
        )
        assert edit_res.status_code == 200
        data = edit_res.json()

        assert data["total_pages"] == original_pages
        assert data["reflow"]["page_added"] is False

    def test_new_page_is_accessible(self, client):
        """After page extension, the new page can be loaded."""
        doc_info = self._open_doc(client)
        original_pages = doc_info["pages"]

        page_res = client.get("/document/page/4")
        blocks = page_res.json()["blocks"]
        target_block = next(
            (b for b in blocks if b["type"] == "paragraph" and b["bbox"]["y0"] > 60),
            None,
        )

        if not target_block:
            pytest.skip("No paragraph block on page 4")

        # Trigger page creation
        massive_text = "Requirement text expanded significantly. " * 100
        edit_res = client.put(
            f"/document/block/{target_block['id']}",
            json={"new_text": massive_text},
        )
        data = edit_res.json()

        if not data["reflow"]["page_added"]:
            pytest.skip("Edit didn't trigger page split")

        new_page_num = data["reflow"]["new_page_number"]

        # The new page should be accessible
        new_page_res = client.get(f"/document/page/{new_page_num}")
        assert new_page_res.status_code == 200
        new_page_data = new_page_res.json()
        assert new_page_data["page_number"] == new_page_num
        assert len(new_page_data["blocks"]) > 0  # Has content
