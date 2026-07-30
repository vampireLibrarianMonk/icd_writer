"""Integration Test: Full Edit → Re-render Cycle

Tests the complete lifecycle of an edit operation:
1. Open document → verify initial state
2. Edit a block → verify edit persists in IR
3. Verify page image re-renders with the change
4. Verify elements endpoint reflects the edit
5. Verify export PDF contains the edit
6. Verify undo reverts everything
7. Verify redo restores everything

This exercises the full pipeline from the flush_out doc:
  User clicks Apply → PUT /document/block/{id} → updates state["document_ir"]
  → reflow_and_split() → Frontend refreshes → GET /elements → GET /image

Tests multiple ICD documents to ensure the cycle works across different
document structures and content types.
"""

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from tests.conftest import skip_no_weasyprint

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"
IDSS_PDF = ICDS_DIR / "IDSS_IDD_RevF.pdf"
LVC_PDF = ICDS_DIR / "20150010976.pdf"
TSAFE_PDF = ICDS_DIR / "20130010957.pdf"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _open_doc(client: TestClient, pdf_path: Path) -> dict:
    """Start session and open a document, return doc info."""
    client.post("/session/start")
    res = client.post(f"/document/open?pdf_path={pdf_path}")
    assert res.status_code == 200
    return res.json()


def _get_first_editable_block(client: TestClient, page_num: int) -> dict | None:
    """Get the first block with an ID (editable) on a page."""
    res = client.get(f"/document/page/{page_num}/elements")
    assert res.status_code == 200
    elements = res.json()["elements"]
    for elem in elements:
        if elem["id"] and elem.get("type") in ("paragraph", "heading", "caption"):
            return elem
    return None


# ─── Full edit cycle on HSI document ──────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestFullEditCycleHSI:
    """Complete edit → re-render → export cycle on HSI Spectrometer ICD."""

    @pytest.fixture
    def client(self):
        app = create_app()
        c = TestClient(app)
        _open_doc(c, HSI_PDF)
        return c

    @skip_no_weasyprint
    def test_full_cycle_page5(self, client):
        """Full edit cycle on page 5 (paragraph text)."""
        # 1. Get initial state
        block = _get_first_editable_block(client, 5)
        assert block is not None, "No editable block on page 5"
        original_text = block["text"]
        block_id = block["id"]

        # 2. Get page image before edit
        img_before = client.get("/document/page/5/image")
        assert img_before.status_code == 200
        assert img_before.content[:8] == PNG_MAGIC

        # 3. Edit the block
        new_text = "FULL_CYCLE_TEST_MARKER_ABC123"
        edit_res = client.put(
            f"/document/block/{block_id}",
            json={"new_text": new_text},
        )
        assert edit_res.status_code == 200
        edit_data = edit_res.json()
        assert edit_data["status"] == "updated"
        assert edit_data["old_text"] == original_text
        assert edit_data["new_text"] == new_text

        # 4. Verify reflow result
        reflow = edit_data["reflow"]
        assert "height_delta_pt" in reflow
        assert "blocks_shifted" in reflow
        assert "overflow_pt" in reflow

        # 5. Verify elements endpoint shows the edit
        elem_res = client.get("/document/page/5/elements")
        assert elem_res.status_code == 200
        elements = elem_res.json()["elements"]
        edited_elem = next((e for e in elements if e["id"] == block_id), None)
        assert edited_elem is not None, "Edited block not found in elements"
        assert edited_elem["text"] == new_text

        # 6. Verify page image changed
        img_after = client.get("/document/page/5/image")
        assert img_after.status_code == 200
        assert img_after.content[:8] == PNG_MAGIC
        assert img_before.content != img_after.content, "Page image didn't change after edit"

        # 7. Verify export contains the edit
        export_res = client.post("/document/export")
        assert export_res.status_code == 200
        export_path = Path(export_res.json()["path"])
        assert export_path.exists()

        doc = fitz.open(str(export_path))
        page5_text = doc[4].get_text("text")
        doc.close()
        assert new_text in page5_text, "Edit not found in exported PDF"

    def test_full_cycle_with_undo(self, client):
        """Edit → verify → undo → verify reverted."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        original_text = block["text"]
        block_id = block["id"]

        # Edit
        client.put(
            f"/document/block/{block_id}",
            json={"new_text": "UNDO_TEST_TEXT"},
        )

        # Verify edit applied
        elem_res = client.get("/document/page/5/elements")
        edited = next(e for e in elem_res.json()["elements"] if e["id"] == block_id)
        assert edited["text"] == "UNDO_TEST_TEXT"

        # Undo
        undo_res = client.post("/document/undo")
        assert undo_res.status_code == 200
        assert undo_res.json()["status"] == "undone"

        # Verify reverted
        elem_res = client.get("/document/page/5/elements")
        reverted = next(e for e in elem_res.json()["elements"] if e["id"] == block_id)
        assert reverted["text"] == original_text

    def test_full_cycle_with_undo_redo(self, client):
        """Edit → undo → redo → verify restored."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        block_id = block["id"]
        edit_text = "REDO_CYCLE_MARKER"

        # Edit
        client.put(f"/document/block/{block_id}", json={"new_text": edit_text})

        # Undo
        client.post("/document/undo")

        # Redo
        redo_res = client.post("/document/redo")
        assert redo_res.status_code == 200

        # Verify restored
        elem_res = client.get("/document/page/5/elements")
        restored = next(e for e in elem_res.json()["elements"] if e["id"] == block_id)
        assert restored["text"] == edit_text

    def test_multiple_edits_sequential(self, client):
        """Multiple sequential edits all persist correctly."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        block_id = block["id"]

        edits = ["First edit", "Second edit", "Third edit"]
        for edit_text in edits:
            client.put(f"/document/block/{block_id}", json={"new_text": edit_text})

        # Final state should be the last edit
        elem_res = client.get("/document/page/5/elements")
        final = next(e for e in elem_res.json()["elements"] if e["id"] == block_id)
        assert final["text"] == "Third edit"

        # Session should track all edits
        session_res = client.get("/session")
        assert session_res.json()["edit_count"] == 3


# ─── Edit cycle on different pages ────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEditCycleDifferentPages:
    """Test edit cycle on different page types."""

    @pytest.fixture
    def client(self):
        app = create_app()
        c = TestClient(app)
        _open_doc(c, HSI_PDF)
        return c

    def test_edit_heading_block(self, client):
        """Editing a heading block works correctly."""
        # Find a heading on any page
        for page_num in range(1, 9):
            res = client.get(f"/document/page/{page_num}/elements")
            elements = res.json()["elements"]
            heading = next(
                (e for e in elements if e["id"] and e["type"] == "heading"), None
            )
            if heading:
                new_text = "EDITED_HEADING_XYZ"
                edit_res = client.put(
                    f"/document/block/{heading['id']}",
                    json={"new_text": new_text},
                )
                assert edit_res.status_code == 200

                # Verify
                elem_res = client.get(f"/document/page/{page_num}/elements")
                edited = next(
                    e for e in elem_res.json()["elements"] if e["id"] == heading["id"]
                )
                assert edited["text"] == new_text
                return

        pytest.skip("No heading blocks found in document")

    def test_edit_different_pages_independent(self, client):
        """Edits on different pages are independent."""
        block_p4 = _get_first_editable_block(client, 4)
        block_p5 = _get_first_editable_block(client, 5)

        if not block_p4 or not block_p5:
            pytest.skip("Need editable blocks on pages 4 and 5")

        # Edit both pages
        client.put(f"/document/block/{block_p4['id']}", json={"new_text": "PAGE4_EDIT"})
        client.put(f"/document/block/{block_p5['id']}", json={"new_text": "PAGE5_EDIT"})

        # Verify both
        elem_p4 = client.get("/document/page/4/elements").json()["elements"]
        elem_p5 = client.get("/document/page/5/elements").json()["elements"]

        edited_p4 = next(e for e in elem_p4 if e["id"] == block_p4["id"])
        edited_p5 = next(e for e in elem_p5 if e["id"] == block_p5["id"])

        assert edited_p4["text"] == "PAGE4_EDIT"
        assert edited_p5["text"] == "PAGE5_EDIT"

    def test_edit_then_navigate_pages(self, client):
        """Edit persists when navigating to other pages and back."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        block_id = block["id"]

        # Edit page 5
        client.put(f"/document/block/{block_id}", json={"new_text": "PERSIST_TEST"})

        # Navigate to other pages (simulate frontend browsing)
        client.get("/document/page/1/elements")
        client.get("/document/page/3/elements")
        client.get("/document/page/7/elements")

        # Come back to page 5 — edit should still be there
        elem_res = client.get("/document/page/5/elements")
        edited = next(e for e in elem_res.json()["elements"] if e["id"] == block_id)
        assert edited["text"] == "PERSIST_TEST"


# ─── Edit cycle with reflow ───────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEditCycleWithReflow:
    """Test that edits trigger reflow and the results are visible."""

    @pytest.fixture
    def client(self):
        app = create_app()
        c = TestClient(app)
        _open_doc(c, HSI_PDF)
        return c

    def test_expansion_reports_positive_height_delta(self, client):
        """Expanding text reports a positive height_delta_pt."""
        block = _get_first_editable_block(client, 5)
        assert block is not None

        long_text = "This is significantly longer text. " * 20
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": long_text},
        )
        data = res.json()
        assert data["reflow"]["height_delta_pt"] > 0

    def test_shrink_reports_negative_height_delta(self, client):
        """Shrinking text reports a negative or zero height_delta_pt."""
        block = _get_first_editable_block(client, 5)
        assert block is not None

        # First expand, then shrink
        client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "Very long text " * 30},
        )
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "Short."},
        )
        data = res.json()
        assert data["reflow"]["height_delta_pt"] <= 0

    def test_expansion_shifts_subsequent_blocks(self, client):
        """Expanding a block shifts subsequent blocks down."""
        # Get blocks on page 5 sorted by y position
        elem_res = client.get("/document/page/5/elements")
        elements = [e for e in elem_res.json()["elements"] if e["id"]]

        if len(elements) < 3:
            pytest.skip("Need at least 3 editable blocks")

        first_block = elements[0]
        last_block = elements[-1]
        original_last_y = last_block["bbox"]["y0"]

        # Expand first block massively
        long_text = "Expanded requirement text. " * 30
        res = client.put(
            f"/document/block/{first_block['id']}",
            json={"new_text": long_text},
        )
        reflow = res.json()["reflow"]

        if reflow["blocks_shifted"] > 0:
            # Re-check last block position
            elem_res2 = client.get("/document/page/5/elements")
            elements2 = elem_res2.json()["elements"]
            last_block_after = next(
                (e for e in elements2 if e["id"] == last_block["id"]), None
            )
            if last_block_after:
                # Should have moved down
                assert last_block_after["bbox"]["y0"] > original_last_y

    def test_massive_expansion_triggers_overflow(self, client):
        """Very large expansion reports overflow."""
        block = _get_first_editable_block(client, 4)
        if not block:
            pytest.skip("No editable block on page 4")

        massive_text = "The spectrometer shall maintain requirements. " * 100
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": massive_text},
        )
        data = res.json()
        reflow = data["reflow"]

        # Should either have overflow resolved (page_added) or have overflow_pt > 0
        # after page split, overflow should be 0
        if reflow["page_added"]:
            assert reflow["overflow_pt"] == 0.0
            assert data["total_pages"] > 8  # More than original


# ─── Edit cycle on other ICD documents ────────────────────────────────


@pytest.mark.skipif(not IDSS_PDF.exists(), reason="IDSS PDF not found")
class TestEditCycleIDSS:
    """Edit cycle on the larger IDSS document."""

    @pytest.fixture
    def client(self):
        app = create_app()
        c = TestClient(app)
        _open_doc(c, IDSS_PDF)
        return c

    def test_edit_middle_page(self, client):
        """Can edit a block on a middle page of a large document."""
        block = _get_first_editable_block(client, 20)
        if not block:
            pytest.skip("No editable block on page 20")

        new_text = "IDSS_EDIT_MARKER"
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": new_text},
        )
        assert res.status_code == 200

        # Verify
        elem_res = client.get("/document/page/20/elements")
        edited = next(
            (e for e in elem_res.json()["elements"] if e["id"] == block["id"]), None
        )
        assert edited is not None
        assert edited["text"] == new_text

    def test_edit_preserves_other_pages(self, client):
        """Editing one page doesn't affect other pages' elements."""
        # Get page 10 elements before
        before = client.get("/document/page/10/elements").json()["elements"]

        # Edit page 20
        block = _get_first_editable_block(client, 20)
        if block:
            client.put(f"/document/block/{block['id']}", json={"new_text": "Changed"})

        # Page 10 should be unchanged
        after = client.get("/document/page/10/elements").json()["elements"]
        assert len(before) == len(after)
        for b, a in zip(before, after):
            assert b["text"] == a["text"]


@pytest.mark.skipif(not LVC_PDF.exists(), reason="LVC PDF not found")
class TestEditCycleLVC:
    """Edit cycle on the LVC architecture document."""

    @pytest.fixture
    def client(self):
        app = create_app()
        c = TestClient(app)
        _open_doc(c, LVC_PDF)
        return c

    def test_basic_edit_works(self, client):
        """Basic edit on LVC document works."""
        block = _get_first_editable_block(client, 3)
        if not block:
            pytest.skip("No editable block on page 3")

        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "LVC_EDIT_TEST"},
        )
        assert res.status_code == 200

    @skip_no_weasyprint
    def test_edit_and_image(self, client):
        """Edit is reflected in page image."""
        block = _get_first_editable_block(client, 3)
        if not block:
            pytest.skip("No editable block on page 3")

        before = client.get("/document/page/3/image").content
        client.put(f"/document/block/{block['id']}", json={"new_text": "CHANGED_LVC"})
        after = client.get("/document/page/3/image").content

        assert before != after


# ─── Consistency checks ───────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEditConsistency:
    """Cross-check consistency between endpoints after edits."""

    @pytest.fixture
    def client(self):
        app = create_app()
        c = TestClient(app)
        _open_doc(c, HSI_PDF)
        return c

    def test_elements_and_page_data_consistent(self, client):
        """Elements endpoint and page data endpoint agree on block text."""
        block = _get_first_editable_block(client, 5)
        assert block is not None

        client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "CONSISTENCY_CHECK"},
        )

        # Elements endpoint
        elem_res = client.get("/document/page/5/elements")
        elem_text = next(
            e["text"] for e in elem_res.json()["elements"] if e["id"] == block["id"]
        )

        # Page data endpoint (if available)
        page_res = client.get("/document/page/5")
        if page_res.status_code == 200:
            page_blocks = page_res.json().get("blocks", [])
            page_text = next(
                (b["text"] for b in page_blocks if b["id"] == block["id"]), None
            )
            if page_text:
                assert elem_text == page_text

    def test_session_edit_count_accurate(self, client):
        """Session edit count matches actual number of edits made."""
        block = _get_first_editable_block(client, 5)
        assert block is not None

        for i in range(5):
            client.put(
                f"/document/block/{block['id']}",
                json={"new_text": f"Edit number {i+1}"},
            )

        session_res = client.get("/session")
        assert session_res.json()["edit_count"] == 5

    @skip_no_weasyprint
    def test_export_after_undo_matches_original(self, client):
        """After editing then undoing, export matches original."""
        block = _get_first_editable_block(client, 5)
        assert block is not None
        original_text = block["text"]

        # Edit
        client.put(f"/document/block/{block['id']}", json={"new_text": "TO_BE_UNDONE"})

        # Undo
        client.post("/document/undo")

        # Export
        export_res = client.post("/document/export")
        export_path = Path(export_res.json()["path"])

        # The text on page 5 should match original
        doc = fitz.open(str(export_path))
        source_doc = fitz.open(str(HSI_PDF))

        # Compare page 5 text
        export_text = doc[4].get_text("text")
        source_text = source_doc[4].get_text("text")

        doc.close()
        source_doc.close()

        assert export_text == source_text
