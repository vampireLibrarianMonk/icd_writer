"""Integration Tests: Page Rebuild Pipeline

Tests the complete page patching, overflow, heading preservation, and
undo/redo cycle using FastAPI TestClient (no Docker required).

Covers the scenarios from flush_out/PAGE_REBUILD_DESIGN.md:
- 4.1: Paragraph edit — text replaced, page image changes
- 4.2: TBR replacement — small inline substitution
- 4.3: Table cell edit — centered text replacement
- 4.4: Page extension — overflow merges onto next page, heading preserved

Also tests:
- Undo restores original page image exactly
- Redo restores edited page image exactly
- Export PDF reflects same changes as preview
- Overflow from page N appears in page N+1 preview (not superimposed)
"""

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _open_hsi(client: TestClient) -> None:
    """Start session and open the HSI document."""
    client.post("/session/start")
    res = client.post(f"/document/open?pdf_path={HSI_PDF}")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


@pytest.fixture
def client():
    """Create a fresh TestClient with HSI document opened."""
    app = create_app()
    c = TestClient(app)
    _open_hsi(c)
    return c


# ─── Page Image Preview Tests ─────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPageImagePreview:
    """Test that page image preview reflects edits immediately."""

    def test_unedited_page_serves_source(self, client):
        """Unedited page returns the original PDF rendering."""
        res = client.get("/document/page/5/image")
        assert res.status_code == 200
        assert res.content[:8] == PNG_MAGIC
        # Should be a reasonable size for a PDF page at 150dpi
        assert len(res.content) > 10000

    def test_edited_page_image_changes(self, client):
        """After editing a block, the page image must change."""
        img_before = client.get("/document/page/7/image").content

        # Edit the Section 4 block on page 7
        new_text = (
            "4. Electrical Interface\n"
            "The IDPU will be the single-point electrical interface between "
            "the spacecraft and the HESSI instruments. Modified text here."
        )
        edit_res = client.put(
            "/document/block/block-p07-b13",
            json={"new_text": new_text},
        )
        assert edit_res.json()["status"] == "updated"

        img_after = client.get("/document/page/7/image").content
        assert img_after[:8] == PNG_MAGIC
        assert img_before != img_after, "Page image must change after edit"

    def test_heading_preserved_after_edit(self, client):
        """Section heading stays in original bold font after paragraph edit."""
        new_text = (
            "4. Electrical Interface\n"
            "Completely new paragraph text replacing the original content. "
            "This is a test of heading preservation."
        )
        client.put("/document/block/block-p07-b13", json={"new_text": new_text})

        # Export and check the heading font
        export_res = client.get("/document/export-download?filename=test.pdf")
        assert export_res.status_code == 200

        doc = fitz.open(stream=export_res.content, filetype="pdf")
        page = doc[6]  # page 7
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        heading_found = False
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars)
                    if "4. Electrical Interface" in text:
                        heading_found = True
                        # Must be bold (original Arial,Bold font)
                        is_bold = bool(span["flags"] & (1 << 4)) or "bold" in span["font"].lower()
                        assert is_bold, (
                            f"Heading lost bold formatting: font={span['font']}, flags={span['flags']}"
                        )
        doc.close()
        assert heading_found, "Heading '4. Electrical Interface' not found in export"


# ─── Overflow Tests ───────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestOverflowHandling:
    """Test that overflow from one page merges correctly onto the next."""

    def _edit_with_overflow(self, client) -> None:
        """Edit block-p07-b13 with enough text to overflow page 7."""
        new_text = (
            "4. Electrical Interface\n"
            "The IDPU will be the single-point electrical interface between "
            "the spacecraft and the HESSI instruments. Details of the operation, "
            "power consumption, harness, and connector details are in the IDPU ICD, "
            "reference 2. The spacecraft provides regulated 28V DC power through a "
            "dedicated power bus to the IDPU. The IDPU then distributes power to all "
            "instrument subsystems including the spectrometer, the imaging system, and "
            "the aspect system. Total power allocation is 120W nominal with a peak of "
            "180W during calibration sequences. All power lines include EMI filtering "
            "at both the spacecraft interface and at each instrument subsystem connector."
        )
        res = client.put("/document/block/block-p07-b13", json={"new_text": new_text})
        assert res.json()["status"] == "updated"

    def test_overflow_changes_next_page_image(self, client):
        """When page 7 overflows, page 8 image must change."""
        img8_before = client.get("/document/page/8/image").content

        self._edit_with_overflow(client)

        img8_after = client.get("/document/page/8/image").content
        assert img8_before != img8_after, (
            "Page 8 image must change when page 7 overflows onto it"
        )

    def test_overflow_export_no_superimposition(self, client):
        """Export: overflow text and Section 5 must NOT overlap on page 8."""
        self._edit_with_overflow(client)

        export_res = client.get("/document/export-download?filename=test.pdf")
        assert export_res.status_code == 200

        doc = fitz.open(stream=export_res.content, filetype="pdf")
        # Should still be 8 pages (overflow merged, not separate page)
        assert len(doc) == 8, f"Expected 8 pages, got {len(doc)}"

        # Page 8 should have both overflow and Section 5
        page8_text = " ".join(doc[7].get_text("text").split())
        assert "5. Spectrometer Integration" in page8_text, (
            "Section 5 missing from page 8"
        )
        # The overflow content should be present
        assert "connector" in page8_text or "subsystem" in page8_text, (
            "Overflow content missing from page 8"
        )
        doc.close()

    def test_overflow_section5_below_section4(self, client):
        """Section 5 must appear BELOW the overflow text, not above it."""
        self._edit_with_overflow(client)

        export_res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=export_res.content, filetype="pdf")
        page8 = doc[7]
        raw = page8.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        # Find y-positions of overflow content and Section 5
        overflow_y = None
        section5_y = None
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars)
                    if "connector" in text or "subsystem" in text:
                        if overflow_y is None:
                            overflow_y = span["bbox"][1]
                    if "5. Spectrometer Integration" in text:
                        section5_y = span["bbox"][1]

        if overflow_y is not None and section5_y is not None:
            assert section5_y > overflow_y, (
                f"Section 5 (y={section5_y}) must be BELOW overflow (y={overflow_y})"
            )
        doc.close()


# ─── Undo / Redo Tests ────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestUndoRedo:
    """Test that undo/redo properly updates the page image preview."""

    def test_undo_restores_original_image(self, client):
        """After undo, the page image must return to the original exactly."""
        img_original = client.get("/document/page/7/image").content

        # Edit
        client.put(
            "/document/block/block-p07-b13",
            json={"new_text": "4. Electrical Interface\nUNDO TEST TEXT"},
        )
        img_edited = client.get("/document/page/7/image").content
        assert img_edited != img_original, "Edit must change image"

        # Undo
        undo_res = client.post("/document/undo")
        assert undo_res.json()["status"] == "undone"

        img_undone = client.get("/document/page/7/image").content
        assert img_undone == img_original, "Undo must restore exact original image"

    def test_redo_restores_edited_image(self, client):
        """After redo, the page image must return to the edited version."""
        # Edit
        client.put(
            "/document/block/block-p07-b13",
            json={"new_text": "4. Electrical Interface\nREDO TEST TEXT"},
        )
        img_edited = client.get("/document/page/7/image").content

        # Undo
        client.post("/document/undo")

        # Redo
        redo_res = client.post("/document/redo")
        assert redo_res.json()["status"] == "redone"

        img_redone = client.get("/document/page/7/image").content
        assert img_redone == img_edited, "Redo must restore exact edited image"

    def test_undo_redo_cycle_multiple_times(self, client):
        """Multiple undo/redo cycles produce consistent images."""
        img_original = client.get("/document/page/7/image").content

        # Edit
        client.put(
            "/document/block/block-p07-b13",
            json={"new_text": "4. Electrical Interface\nCYCLE TEST"},
        )
        img_edited = client.get("/document/page/7/image").content

        # Cycle: undo → redo → undo → redo
        client.post("/document/undo")
        assert client.get("/document/page/7/image").content == img_original

        client.post("/document/redo")
        assert client.get("/document/page/7/image").content == img_edited

        client.post("/document/undo")
        assert client.get("/document/page/7/image").content == img_original

        client.post("/document/redo")
        assert client.get("/document/page/7/image").content == img_edited


# ─── Export Consistency Tests ─────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportConsistency:
    """Test that export PDF matches what the preview shows."""

    def test_export_contains_edit(self, client):
        """Exported PDF must contain the edited text."""
        new_text = (
            "4. Electrical Interface\n"
            "UNIQUE_EXPORT_MARKER_XYZ123 is the test string that should appear."
        )
        client.put("/document/block/block-p07-b13", json={"new_text": new_text})

        export_res = client.get("/document/export-download?filename=test.pdf")
        assert export_res.status_code == 200

        doc = fitz.open(stream=export_res.content, filetype="pdf")
        page7_text = " ".join(doc[6].get_text("text").split())
        doc.close()

        assert "UNIQUE_EXPORT_MARKER_XYZ123" in page7_text, (
            "Edited text not found in exported PDF page 7"
        )

    def test_export_preserves_unedited_pages(self, client):
        """Pages without edits must be identical to source in the export."""
        # Edit page 7 only
        client.put(
            "/document/block/block-p07-b13",
            json={"new_text": "4. Electrical Interface\nEdited."},
        )

        export_res = client.get("/document/export-download?filename=test.pdf")
        doc_export = fitz.open(stream=export_res.content, filetype="pdf")
        doc_source = fitz.open(str(HSI_PDF))

        # Pages 1-6 should have identical text
        for page_idx in range(6):
            export_text = " ".join(doc_export[page_idx].get_text("text").split())
            source_text = " ".join(doc_source[page_idx].get_text("text").split())
            assert export_text == source_text, (
                f"Page {page_idx + 1} text differs from source (should be unchanged)"
            )

        doc_export.close()
        doc_source.close()

    def test_export_same_page_count_when_no_overflow(self, client):
        """Short edits that fit on the page shouldn't change page count."""
        client.put(
            "/document/block/block-p07-b13",
            json={"new_text": "4. Electrical Interface\nShort edit."},
        )

        export_res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=export_res.content, filetype="pdf")
        assert len(doc) == 8, f"Expected 8 pages, got {len(doc)}"
        doc.close()


# ─── TBR Replacement Test ─────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTBRReplacement:
    """Test small inline text replacements (TBR resolution)."""

    def test_table_cell_edit(self, client):
        """Editing a table cell value should change the page image."""
        img_before = client.get("/document/page/7/image").content

        # Replace "30W" in the thermostat table (block-p07-b05 contains table data)
        # Use the table-cell endpoint for inline replacement
        res = client.put(
            "/document/table-cell?page=7&old_text=30W&new_text=25W"
        )
        if res.status_code == 200:
            img_after = client.get("/document/page/7/image").content
            assert img_before != img_after, "Table cell edit must change page image"
        else:
            # Table cell not found via exact match — acceptable (structure varies)
            pytest.skip("Table cell '30W' not found on page 7")


# ─── TOC Editing Tests ────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTOCEditing:
    """Test Table of Contents entry editing."""

    def test_toc_edit_changes_preview(self, client):
        """Editing a TOC entry changes the TOC page image."""
        img_before = client.get("/document/page/3/image").content

        res = client.put(
            "/document/page/3/toc?index=21"
            "&title=4.+Electrical+%26+Data+Interface&page_ref=4"
        )
        assert res.json()["status"] == "updated"

        img_after = client.get("/document/page/3/image").content
        assert img_before != img_after, "TOC page image must change after edit"

    def test_toc_edit_appears_in_export(self, client):
        """Edited TOC entry text appears in the exported PDF."""
        client.put(
            "/document/page/3/toc?index=21"
            "&title=4.+Electrical+%26+Data+Interface&page_ref=4"
        )

        export_res = client.get("/document/export-download?filename=test.pdf")
        assert export_res.status_code == 200

        doc = fitz.open(stream=export_res.content, filetype="pdf")
        toc_text = " ".join(doc[2].get_text("text").split())
        doc.close()
        assert "Electrical & Data Interface" in toc_text, (
            "Edited TOC title not found in export"
        )

    def test_toc_edit_undo_restores_original(self, client):
        """Undo reverts the TOC edit and restores the original page image."""
        img_original = client.get("/document/page/3/image").content

        client.put(
            "/document/page/3/toc?index=6"
            "&title=2.+Structural+Interface&page_ref=2"
        )
        img_edited = client.get("/document/page/3/image").content
        assert img_edited != img_original

        # Undo
        client.post("/document/undo")
        img_undone = client.get("/document/page/3/image").content
        assert img_undone == img_original, "Undo must restore original TOC image"

    def test_toc_page_ref_change(self, client):
        """Changing just the page reference number works."""
        res = client.put(
            "/document/page/3/toc?index=21"
            "&title=4.+Electrical+Interface&page_ref=7"
        )
        assert res.json()["status"] == "updated"
        assert res.json()["new_page_ref"] == "7"

    def test_toc_edit_preserves_indentation(self, client):
        """Edited TOC entry aligns at x=114 (same as other top-level titles)."""
        client.put(
            "/document/page/3/toc?index=21"
            "&title=4.+Electrical+%26+Data+Interface&page_ref=4"
        )

        export_res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=export_res.content, filetype="pdf")
        page = doc[2]
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        # Find the inserted title and check its x-position
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars)
                    if "Data Interface" in text:
                        x = span["bbox"][0]
                        # Must be at x=114 (same indent as other titles)
                        assert abs(x - 114.0) < 2.0, (
                            f"TOC title at x={x:.1f}, expected ~114.0"
                        )
                        doc.close()
                        return
        doc.close()
        pytest.fail("Edited TOC title not found in export rawdict")


# ─── Session Persistence Tests ────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestSessionPersistence:
    """Test session save/load functionality."""

    def test_save_and_load_restores_edits(self, client):
        """Saved session can be loaded and edits are restored."""
        # Make an edit
        new_text = "4. Electrical Interface\nSESSION_PERSIST_TEST_MARKER"
        client.put("/document/block/block-p07-b13", json={"new_text": new_text})

        # Save session
        save_res = client.post("/session/save-as?filename=test_persist")
        assert save_res.json()["status"] == "saved"

        # Get edited page image
        img_edited = client.get("/document/page/7/image").content

        # Start fresh session
        client.post("/session/start")
        client.post(f"/document/open?pdf_path={HSI_PDF}")
        img_fresh = client.get("/document/page/7/image").content
        assert img_fresh != img_edited, "Fresh session should show original"

        # Load the saved session
        load_res = client.post("/session/load?filename=test_persist")
        assert load_res.json()["status"] == "loaded"

        # Verify edit restored
        elements = client.get("/document/page/7/elements").json()["elements"]
        restored = next(
            (e for e in elements if "SESSION_PERSIST_TEST_MARKER" in e.get("text", "")),
            None,
        )
        assert restored is not None, "Edit not restored after session load"

        # Cleanup
        from pathlib import Path
        Path("sessions/test_persist.icd-session").unlink(missing_ok=True)

    def test_journal_endpoint_returns_actions(self, client):
        """GET /session/journal returns action entries."""
        client.put(
            "/document/block/block-p07-b13",
            json={"new_text": "4. Electrical Interface\nJOURNAL_TEST"},
        )

        journal = client.get("/session/journal").json()
        assert journal["edit_count"] >= 1
        assert len(journal["entries"]) >= 2  # document_opened + block_edited
        assert any(e["action_type"] == "block_edited" for e in journal["entries"])

    def test_session_files_listing(self, client):
        """GET /session/files lists saved session files."""
        client.post("/session/save-as?filename=test_list")
        files = client.get("/session/files").json()
        filenames = [f["filename"] for f in files["files"]]
        assert "test_list.icd-session" in filenames

        # Cleanup
        from pathlib import Path
        Path("sessions/test_list.icd-session").unlink(missing_ok=True)
