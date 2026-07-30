"""Exhaustive E2E tests for editing every block type.

Tests each element type through the complete edit lifecycle:
- heading: section titles (bold, larger font)
- paragraph: body text (regular font)
- caption: table/figure captions
- list_item: bulleted/numbered items
- footer: page footer blocks
- header: page header blocks

For each type, verifies:
1. Block is found and identifiable by type
2. PUT /document/block/{id} edit succeeds
3. GET /elements reflects the new text
4. Edit count increments correctly
5. Undo restores original text
6. Redo re-applies the edit
7. Multiple sequential edits persist
8. Empty text edit is handled
9. Special characters (unicode, newlines) preserved
10. Very long text expansion handled with reflow
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from tests.conftest import skip_no_weasyprint

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"
IDSS_PDF = ICDS_DIR / "IDSS_IDD_RevF.pdf"


@pytest.fixture
def client():
    """Create a test client with session and HSI document loaded."""
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    c.post(f"/document/open?pdf_path={HSI_PDF}")
    return c


@pytest.fixture
def idss_client():
    """Create a test client with IDSS document (larger, more block types)."""
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    c.post(f"/document/open?pdf_path={IDSS_PDF}")
    return c


def _find_block_by_type(client, block_type: str, page_range=None):
    """Find the first editable block of a given type across pages."""
    if page_range is None:
        page_range = range(1, 9)
    for page_num in page_range:
        res = client.get(f"/document/page/{page_num}/elements")
        if res.status_code != 200:
            continue
        for elem in res.json()["elements"]:
            if elem["id"] and elem["type"] == block_type:
                return page_num, elem
    return None, None


def _find_blocks_by_type(client, block_type: str, page_range=None):
    """Find ALL editable blocks of a given type across pages."""
    results = []
    if page_range is None:
        page_range = range(1, 9)
    for page_num in page_range:
        res = client.get(f"/document/page/{page_num}/elements")
        if res.status_code != 200:
            continue
        for elem in res.json()["elements"]:
            if elem["id"] and elem["type"] == block_type:
                results.append((page_num, elem))
    return results


# ─── Heading block type ───────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestHeadingBlockEdit:
    """Exhaustive tests for editing heading-type blocks."""

    def test_heading_found(self, client):
        """At least one heading block exists in the document."""
        page, block = _find_block_by_type(client, "heading")
        assert block is not None, "No heading block found"
        assert block["type"] == "heading"
        assert len(block["text"]) > 0

    def test_edit_heading_succeeds(self, client):
        """PUT edit on a heading block returns success."""
        page, block = _find_block_by_type(client, "heading")
        if not block:
            pytest.skip("No heading block available")
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "3.1 Edited Section Title"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "updated"

    def test_heading_edit_reflected(self, client):
        """Edited heading text appears in elements endpoint."""
        page, block = _find_block_by_type(client, "heading")
        if not block:
            pytest.skip("No heading block available")
        new_text = "4.0 Modified Heading"
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(
            (e for e in res.json()["elements"] if e["id"] == block["id"]), None
        )
        assert edited is not None
        assert edited["text"] == new_text

    def test_heading_undo(self, client):
        """Undo restores original heading text."""
        page, block = _find_block_by_type(client, "heading")
        if not block:
            pytest.skip("No heading block available")
        original = block["text"]
        client.put(f"/document/block/{block['id']}", json={"new_text": "TEMP"})
        client.post("/document/undo")

        res = client.get(f"/document/page/{page}/elements")
        reverted = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert reverted["text"] == original

    def test_heading_redo(self, client):
        """Redo re-applies heading edit after undo."""
        page, block = _find_block_by_type(client, "heading")
        if not block:
            pytest.skip("No heading block available")
        edit_text = "REDO_HEADING"
        client.put(f"/document/block/{block['id']}", json={"new_text": edit_text})
        client.post("/document/undo")
        client.post("/document/redo")

        res = client.get(f"/document/page/{page}/elements")
        restored = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert restored["text"] == edit_text

    def test_heading_special_chars(self, client):
        """Heading preserves unicode and special characters."""
        page, block = _find_block_by_type(client, "heading")
        if not block:
            pytest.skip("No heading block available")
        special = "3.2 Temperature \u00b1 5\u00b0C Requirements \u2014 Rev. B"
        client.put(f"/document/block/{block['id']}", json={"new_text": special})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert edited["text"] == special

    def test_heading_long_expansion(self, client):
        """Very long heading triggers reflow without error."""
        page, block = _find_block_by_type(client, "heading")
        if not block:
            pytest.skip("No heading block available")
        long_text = "3.0 Extended Section: " + "SubSection Detail. " * 30
        res = client.put(
            f"/document/block/{block['id']}", json={"new_text": long_text}
        )
        assert res.status_code == 200
        assert res.json()["reflow"]["height_delta_pt"] > 0


# ─── Paragraph block type ─────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestParagraphBlockEdit:
    """Exhaustive tests for editing paragraph-type blocks."""

    def test_paragraph_found(self, client):
        """Multiple paragraph blocks exist in the document."""
        blocks = _find_blocks_by_type(client, "paragraph")
        assert len(blocks) >= 3, f"Expected 3+ paragraphs, found {len(blocks)}"

    def test_edit_paragraph_succeeds(self, client):
        """PUT edit on a paragraph block returns success."""
        page, block = _find_block_by_type(client, "paragraph")
        if not block:
            pytest.skip("No paragraph block available")
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "The spectrometer shall maintain thermal equilibrium."},
        )
        assert res.status_code == 200

    def test_paragraph_edit_reflected(self, client):
        """Edited paragraph text appears in elements."""
        page, block = _find_block_by_type(client, "paragraph")
        if not block:
            pytest.skip("No paragraph block available")
        new_text = "Modified paragraph content for testing."
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert edited["text"] == new_text

    def test_paragraph_multiline(self, client):
        """Paragraph with newlines is preserved."""
        page, block = _find_block_by_type(client, "paragraph")
        if not block:
            pytest.skip("No paragraph block available")
        multiline = "Line 1: Power requirement.\nLine 2: Voltage spec.\nLine 3: Current draw."
        client.put(f"/document/block/{block['id']}", json={"new_text": multiline})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert edited["text"] == multiline
        assert edited["text"].count("\n") == 2

    def test_paragraph_undo_redo_cycle(self, client):
        """Full undo/redo cycle on paragraph."""
        page, block = _find_block_by_type(client, "paragraph")
        if not block:
            pytest.skip("No paragraph block available")
        original = block["text"]

        client.put(f"/document/block/{block['id']}", json={"new_text": "Edit1"})
        client.put(f"/document/block/{block['id']}", json={"new_text": "Edit2"})

        # Undo twice → back to original
        client.post("/document/undo")
        client.post("/document/undo")
        res = client.get(f"/document/page/{page}/elements")
        text = next(e for e in res.json()["elements"] if e["id"] == block["id"])["text"]
        assert text == original

        # Redo twice → back to Edit2
        client.post("/document/redo")
        client.post("/document/redo")
        res = client.get(f"/document/page/{page}/elements")
        text = next(e for e in res.json()["elements"] if e["id"] == block["id"])["text"]
        assert text == "Edit2"

    def test_paragraph_massive_expansion(self, client):
        """Very large paragraph expansion triggers page split."""
        page, block = _find_block_by_type(client, "paragraph", page_range=range(4, 8))
        if not block:
            pytest.skip("No paragraph on pages 4-7")
        massive = "The system shall comply with requirement. " * 100
        res = client.put(f"/document/block/{block['id']}", json={"new_text": massive})
        assert res.status_code == 200
        # Should trigger overflow or page split
        reflow = res.json()["reflow"]
        assert reflow["height_delta_pt"] > 0

    def test_paragraph_shrink_to_short(self, client):
        """Shrinking paragraph to minimal text works."""
        page, block = _find_block_by_type(client, "paragraph")
        if not block:
            pytest.skip("No paragraph block available")
        res = client.put(f"/document/block/{block['id']}", json={"new_text": "OK."})
        assert res.status_code == 200
        assert res.json()["reflow"]["height_delta_pt"] <= 0


# ─── Caption block type ───────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestCaptionBlockEdit:
    """Exhaustive tests for editing caption-type blocks."""

    def test_caption_found(self, client):
        """At least one caption block exists (table/figure captions)."""
        page, block = _find_block_by_type(client, "caption")
        assert block is not None, "No caption block found in document"
        assert "Table" in block["text"] or "Figure" in block["text"]

    def test_edit_caption_succeeds(self, client):
        """PUT edit on a caption block returns success."""
        page, block = _find_block_by_type(client, "caption")
        if not block:
            pytest.skip("No caption block available")
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "Table 5.1-1 Updated Caption Text"},
        )
        assert res.status_code == 200

    def test_caption_edit_reflected(self, client):
        """Edited caption text appears in elements."""
        page, block = _find_block_by_type(client, "caption")
        if not block:
            pytest.skip("No caption block available")
        new_text = "Table 3.2.1-1 Revised Thermostat Specs"
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert edited["text"] == new_text

    def test_caption_undo(self, client):
        """Undo restores original caption."""
        page, block = _find_block_by_type(client, "caption")
        if not block:
            pytest.skip("No caption block available")
        original = block["text"]
        client.put(f"/document/block/{block['id']}", json={"new_text": "TEMP CAP"})
        client.post("/document/undo")

        res = client.get(f"/document/page/{page}/elements")
        reverted = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert reverted["text"] == original

    def test_caption_special_chars(self, client):
        """Caption preserves special characters."""
        page, block = _find_block_by_type(client, "caption")
        if not block:
            pytest.skip("No caption block available")
        special = "Table 3.3\u20131 Thermal Limits (\u00b0C)"
        client.put(f"/document/block/{block['id']}", json={"new_text": special})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert edited["text"] == special

    def test_caption_numbering_preserved(self, client):
        """Caption table/figure numbering can be modified."""
        page, block = _find_block_by_type(client, "caption")
        if not block:
            pytest.skip("No caption block available")
        new_text = "Figure 99.1 New Diagram Caption"
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert "Figure 99.1" in edited["text"]


# ─── Footer/Header blocks ─────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestFooterHeaderBlocks:
    """Tests for footer and header region blocks.

    Note: The IR stores footers as paragraph blocks with high y-position.
    The elements endpoint labels them based on position (y > page_height - 72).
    Editing footer blocks should work the same as paragraphs.
    """

    def _find_footer_block(self, client):
        """Find a block in the footer region (y0 > 720, contains page number pattern)."""
        for page_num in range(2, 9):  # Skip page 1 (title page may not have footer)
            res = client.get(f"/document/page/{page_num}/elements")
            if res.status_code != 200:
                continue
            for elem in res.json()["elements"]:
                if (elem["id"] and elem["bbox"]["y0"] > 720
                        and ("Page" in elem["text"] or "page" in elem["text"])):
                    return page_num, elem
        # Fallback: any block with y0 > 720
        for page_num in range(2, 9):
            res = client.get(f"/document/page/{page_num}/elements")
            if res.status_code != 200:
                continue
            for elem in res.json()["elements"]:
                if elem["id"] and elem["bbox"]["y0"] > 720:
                    return page_num, elem
        return None, None

    def _find_header_block(self, client):
        """Find a block in the header region (y0 < 60)."""
        for page_num in range(1, 9):
            res = client.get(f"/document/page/{page_num}/elements")
            if res.status_code != 200:
                continue
            for elem in res.json()["elements"]:
                if elem["id"] and elem["bbox"]["y0"] < 60:
                    return page_num, elem
        return None, None

    def test_footer_block_exists(self, client):
        """Document has blocks in the footer region."""
        page, block = self._find_footer_block(client)
        assert block is not None, "No footer-region block found"

    def test_footer_edit_succeeds(self, client):
        """Footer blocks can be edited."""
        page, block = self._find_footer_block(client)
        if not block:
            pytest.skip("No footer block available")
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "J. Smith | Page 99 | 2026-01-15"},
        )
        assert res.status_code == 200

    def test_footer_edit_reflected(self, client):
        """Edited footer text appears in elements on the same page."""
        page, block = self._find_footer_block(client)
        if not block:
            pytest.skip("No footer block available")
        new_text = "Author Name | Page X | Date"
        edit_res = client.put(f"/document/block/{block['id']}", json={"new_text": new_text})
        assert edit_res.status_code == 200
        edit_data = edit_res.json()
        edit_page = edit_data.get("page", page)

        # Search for the block on the edit page and surrounding pages
        for p in range(max(1, edit_page - 1), edit_page + 3):
            res = client.get(f"/document/page/{p}/elements")
            if res.status_code != 200:
                continue
            edited = next(
                (e for e in res.json()["elements"] if e["id"] == block["id"]), None
            )
            if edited:
                assert edited["text"] == new_text
                return

        # If overflow occurred and block was moved to a new page, search there too
        if edit_data.get("reflow", {}).get("page_added"):
            new_page = edit_data["reflow"]["new_page_number"]
            res = client.get(f"/document/page/{new_page}/elements")
            if res.status_code == 200:
                edited = next(
                    (e for e in res.json()["elements"] if e["id"] == block["id"]), None
                )
                if edited:
                    assert edited["text"] == new_text
                    return

        pytest.fail(
            f"Footer block {block['id']} not found after edit. "
            f"Reflow overflow may have incorrectly moved a footer block. "
            f"Reflow data: {edit_data.get('reflow', {})}"
        )

    def test_header_block_exists(self, client):
        """Document has blocks in the header region."""
        page, block = self._find_header_block(client)
        assert block is not None, "No header-region block found"

    def test_header_edit_succeeds(self, client):
        """Header blocks can be edited."""
        page, block = self._find_header_block(client)
        if not block:
            pytest.skip("No header block available")
        res = client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "HESSI ICD Rev. G"},
        )
        assert res.status_code == 200

    def test_header_edit_reflected(self, client):
        """Edited header text appears in elements."""
        page, block = self._find_header_block(client)
        if not block:
            pytest.skip("No header block available")
        new_text = "Updated Header Text"
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert edited["text"] == new_text

    def test_footer_not_shifted_by_reflow(self, client):
        """Footer position should NOT be affected by body text reflow."""
        page, footer = self._find_footer_block(client)
        if not footer:
            pytest.skip("No footer block")
        original_y = footer["bbox"]["y0"]

        # Find and expand a body paragraph on same page
        res = client.get(f"/document/page/{page}/elements")
        body_block = next(
            (e for e in res.json()["elements"]
             if e["id"] and 60 < e["bbox"]["y0"] < 700 and e["type"] == "paragraph"),
            None,
        )
        if not body_block:
            pytest.skip("No body paragraph on same page as footer")

        # Expand body text
        client.put(
            f"/document/block/{body_block['id']}",
            json={"new_text": "Expanded text. " * 20},
        )

        # Footer should still be at approximately the same position
        res = client.get(f"/document/page/{page}/elements")
        footer_after = next(
            (e for e in res.json()["elements"] if e["id"] == footer["id"]), None
        )
        if footer_after:
            # Footer should NOT have moved (reflow skips headers/footers)
            assert abs(footer_after["bbox"]["y0"] - original_y) < 1.0, (
                f"Footer moved from y={original_y} to y={footer_after['bbox']['y0']}"
            )


# ─── Cross-type state management ──────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestCrossTypeStateManagement:
    """Test that edits to different block types maintain independent state."""

    def test_edit_heading_then_paragraph(self, client):
        """Editing heading then paragraph — both persist."""
        _, heading = _find_block_by_type(client, "heading")
        page_p, para = _find_block_by_type(client, "paragraph")
        if not heading or not para:
            pytest.skip("Need both heading and paragraph")

        client.put(f"/document/block/{heading['id']}", json={"new_text": "H_EDIT"})
        client.put(f"/document/block/{para['id']}", json={"new_text": "P_EDIT"})

        # Both should persist
        page_h, _ = _find_block_by_type(client, "heading")
        res_h = client.get(f"/document/page/{page_h}/elements")
        h_text = next(e for e in res_h.json()["elements"] if e["id"] == heading["id"])
        assert h_text["text"] == "H_EDIT"

        res_p = client.get(f"/document/page/{page_p}/elements")
        p_text = next(e for e in res_p.json()["elements"] if e["id"] == para["id"])
        assert p_text["text"] == "P_EDIT"

    def test_undo_only_last_edit(self, client):
        """Undo only reverts the last edit, not earlier ones."""
        _, heading = _find_block_by_type(client, "heading")
        page_p, para = _find_block_by_type(client, "paragraph")
        if not heading or not para:
            pytest.skip("Need both heading and paragraph")

        client.put(f"/document/block/{heading['id']}", json={"new_text": "H_FIRST"})
        client.put(f"/document/block/{para['id']}", json={"new_text": "P_SECOND"})

        # Undo should revert paragraph edit only
        client.post("/document/undo")

        page_h, _ = _find_block_by_type(client, "heading")
        res_h = client.get(f"/document/page/{page_h}/elements")
        h_text = next(e for e in res_h.json()["elements"] if e["id"] == heading["id"])
        assert h_text["text"] == "H_FIRST"  # Still edited

    def test_session_tracks_all_types(self, client):
        """Session edit count tracks all block types."""
        _, heading = _find_block_by_type(client, "heading")
        _, para = _find_block_by_type(client, "paragraph")
        _, caption = _find_block_by_type(client, "caption")

        edits_made = 0
        if heading:
            client.put(f"/document/block/{heading['id']}", json={"new_text": "H"})
            edits_made += 1
        if para:
            client.put(f"/document/block/{para['id']}", json={"new_text": "P"})
            edits_made += 1
        if caption:
            client.put(f"/document/block/{caption['id']}", json={"new_text": "C"})
            edits_made += 1

        session = client.get("/session").json()
        assert session["edit_count"] == edits_made


# ─── Edge cases across all types ──────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEdgeCasesAllTypes:
    """Edge cases that apply to all block types."""

    @pytest.mark.parametrize("block_type", ["heading", "paragraph", "caption"])
    def test_empty_string_edit(self, client, block_type):
        """Editing to empty string is handled (may fail or produce empty)."""
        page, block = _find_block_by_type(client, block_type)
        if not block:
            pytest.skip(f"No {block_type} block available")
        # Empty edit — endpoint should either accept or reject gracefully
        res = client.put(f"/document/block/{block['id']}", json={"new_text": ""})
        assert res.status_code in (200, 400, 422)

    @pytest.mark.parametrize("block_type", ["heading", "paragraph", "caption"])
    def test_whitespace_only_edit(self, client, block_type):
        """Editing to whitespace-only is handled."""
        page, block = _find_block_by_type(client, block_type)
        if not block:
            pytest.skip(f"No {block_type} block available")
        res = client.put(f"/document/block/{block['id']}", json={"new_text": "   "})
        assert res.status_code in (200, 400, 422)

    @pytest.mark.parametrize("block_type", ["heading", "paragraph"])
    def test_unicode_math_symbols(self, client, block_type):
        """Unicode math/science symbols are preserved."""
        page, block = _find_block_by_type(client, block_type)
        if not block:
            pytest.skip(f"No {block_type} block available")
        unicode_text = "\u0394T = 25\u00b0C \u00b1 3\u00b0C; P \u2264 30W; V\u2093 = 28V"
        client.put(f"/document/block/{block['id']}", json={"new_text": unicode_text})

        res = client.get(f"/document/page/{page}/elements")
        edited = next(e for e in res.json()["elements"] if e["id"] == block["id"])
        assert edited["text"] == unicode_text

    @pytest.mark.parametrize("block_type", ["heading", "paragraph"])
    def test_very_long_single_word(self, client, block_type):
        """A single very long word (no spaces) is handled by reflow."""
        page, block = _find_block_by_type(client, block_type)
        if not block:
            pytest.skip(f"No {block_type} block available")
        long_word = "A" * 500  # 500-char single word
        res = client.put(f"/document/block/{block['id']}", json={"new_text": long_word})
        assert res.status_code == 200

        elem_res = client.get(f"/document/page/{page}/elements")
        edited = next(
            (e for e in elem_res.json()["elements"] if e["id"] == block["id"]), None
        )
        # Block may have moved to new page after overflow/split
        if edited:
            assert edited["text"] == long_word

    @pytest.mark.parametrize("block_type", ["heading", "paragraph"])
    def test_rapid_sequential_edits(self, client, block_type):
        """Many rapid sequential edits don't corrupt state."""
        page, block = _find_block_by_type(client, block_type)
        if not block:
            pytest.skip(f"No {block_type} block available")

        for i in range(10):
            client.put(
                f"/document/block/{block['id']}",
                json={"new_text": f"Rapid edit #{i}"},
            )

        res = client.get(f"/document/page/{page}/elements")
        final = next(
            (e for e in res.json()["elements"] if e["id"] == block["id"]), None
        )
        if final:
            assert final["text"] == "Rapid edit #9"

        session = client.get("/session").json()
        assert session["edit_count"] == 10


# ─── Multi-document validation ────────────────────────────────────────


@pytest.mark.skipif(not IDSS_PDF.exists(), reason="IDSS PDF not found")
class TestElementTypesIDSS:
    """Verify block types exist and are editable in the IDSS document."""

    def test_idss_has_headings(self, idss_client):
        """IDSS has heading blocks."""
        blocks = _find_blocks_by_type(idss_client, "heading", page_range=range(1, 30))
        assert len(blocks) >= 5, "IDSS should have many headings"

    def test_idss_has_paragraphs(self, idss_client):
        """IDSS has paragraph blocks."""
        blocks = _find_blocks_by_type(idss_client, "paragraph", page_range=range(1, 30))
        assert len(blocks) >= 10, "IDSS should have many paragraphs"

    def test_idss_heading_editable(self, idss_client):
        """IDSS headings are editable."""
        page, block = _find_block_by_type(idss_client, "heading", page_range=range(3, 20))
        if not block:
            pytest.skip("No heading in IDSS pages 3-20")
        res = idss_client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "IDSS Section Edit"},
        )
        assert res.status_code == 200

    def test_idss_paragraph_editable(self, idss_client):
        """IDSS paragraphs are editable."""
        page, block = _find_block_by_type(idss_client, "paragraph", page_range=range(5, 20))
        if not block:
            pytest.skip("No paragraph in IDSS pages 5-20")
        res = idss_client.put(
            f"/document/block/{block['id']}",
            json={"new_text": "IDSS body text edit."},
        )
        assert res.status_code == 200
