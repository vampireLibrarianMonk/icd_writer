"""E2E Test: PDF Export Endpoint

Tests POST /document/export which produces the final PDF:
- Unedited documents export as a copy of the source (pixel-perfect)
- Edited pages are re-rendered from Document IR via WeasyPrint
- Unedited pages are copied directly from source PDF
- New pages (from page split) render entirely from IR
- Export produces a downloadable file
- Edit text appears in the exported PDF
- Page count matches after edits and page splits
"""

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from tests.conftest import skip_no_weasyprint

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"


@pytest.fixture
def client():
    """Create a test client with session and document loaded."""
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    c.post(f"/document/open?pdf_path={HSI_PDF}")
    return c


@pytest.fixture
def fresh_client():
    """Create a test client without a loaded document."""
    app = create_app()
    return TestClient(app)


# ─── Basic export functionality ───────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportBasic:
    """Basic export endpoint functionality."""

    def test_export_succeeds(self, client):
        """POST /document/export returns success status."""
        res = client.post("/document/export")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "exported"
        assert "path" in data

    def test_export_produces_file(self, client):
        """Export creates an actual PDF file on disk."""
        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])
        assert exported_path.exists(), f"Export file not found: {exported_path}"
        assert exported_path.stat().st_size > 0

    def test_exported_file_is_valid_pdf(self, client):
        """The exported file is a valid PDF that can be opened."""
        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        doc = fitz.open(str(exported_path))
        assert len(doc) > 0
        doc.close()

    def test_exported_page_count_matches_source(self, client):
        """Without edits, export has same page count as source."""
        source_doc = fitz.open(str(HSI_PDF))
        source_pages = len(source_doc)
        source_doc.close()

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        export_doc = fitz.open(str(exported_path))
        assert len(export_doc) == source_pages
        export_doc.close()

    def test_export_without_document_fails(self, fresh_client):
        """Exporting without a loaded document returns an error."""
        fresh_client.post("/session/start")
        res = fresh_client.post("/document/export")
        assert res.status_code == 404


# ─── Export with edits ────────────────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportWithEdits:
    """Export after editing text blocks."""

    def _edit_block(self, client, page_num: int, new_text: str) -> str:
        """Helper: edit the first editable block on a page."""
        res = client.get(f"/document/page/{page_num}/elements")
        elements = res.json()["elements"]
        target = next((e for e in elements if e["id"]), None)
        assert target is not None, f"No editable block on page {page_num}"

        edit_res = client.put(
            f"/document/block/{target['id']}",
            json={"new_text": new_text},
        )
        assert edit_res.status_code == 200
        return target["id"]

    def test_edit_appears_in_export(self, client):
        """Edited text appears in the exported PDF."""
        unique_text = "EXPORT_UNIQUE_MARKER_12345"
        self._edit_block(client, 5, unique_text)

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        doc = fitz.open(str(exported_path))
        page5_text = doc[4].get_text("text")
        doc.close()

        assert unique_text in page5_text

    def test_unedited_pages_preserve_text(self, client):
        """Unedited pages in export preserve original source text."""
        # Edit only page 5
        self._edit_block(client, 5, "Only page 5 edited")

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        # Compare page 1 text between source and export
        source_doc = fitz.open(str(HSI_PDF))
        source_p1_text = source_doc[0].get_text("text")
        source_doc.close()

        export_doc = fitz.open(str(exported_path))
        export_p1_text = export_doc[0].get_text("text")
        export_doc.close()

        assert source_p1_text == export_p1_text

    def test_multiple_page_edits(self, client):
        """Editing multiple pages all appear in export."""
        marker_p4 = "MARKER_PAGE4_EDIT"
        marker_p5 = "MARKER_PAGE5_EDIT"

        self._edit_block(client, 4, marker_p4)
        self._edit_block(client, 5, marker_p5)

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        doc = fitz.open(str(exported_path))
        p4_text = doc[3].get_text("text")
        p5_text = doc[4].get_text("text")
        doc.close()

        assert marker_p4 in p4_text
        assert marker_p5 in p5_text

    def test_edit_preserves_page_count(self, client):
        """A small edit doesn't change the page count."""
        source_doc = fitz.open(str(HSI_PDF))
        source_pages = len(source_doc)
        source_doc.close()

        self._edit_block(client, 5, "Small edit")

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        export_doc = fitz.open(str(exported_path))
        assert len(export_doc) == source_pages
        export_doc.close()


# ─── Export with page split ───────────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportWithPageSplit:
    """Export after an edit triggers page overflow and split."""

    def _trigger_page_split(self, client) -> dict:
        """Helper: make a massive edit that triggers page split."""
        res = client.get("/document/page/4/elements")
        elements = res.json()["elements"]
        target = next(
            (e for e in elements if e["id"] and e["bbox"]["y0"] > 60),
            None,
        )
        if not target:
            pytest.skip("No body block on page 4")

        massive_text = "The spectrometer thermal requirement shall be verified. " * 100
        edit_res = client.put(
            f"/document/block/{target['id']}",
            json={"new_text": massive_text},
        )
        assert edit_res.status_code == 200
        return edit_res.json()

    def test_page_split_increases_page_count(self, client):
        """After page split, export has more pages than source."""
        source_doc = fitz.open(str(HSI_PDF))
        source_pages = len(source_doc)
        source_doc.close()

        edit_data = self._trigger_page_split(client)
        if not edit_data.get("reflow", {}).get("page_added"):
            pytest.skip("Edit didn't trigger page split")

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        export_doc = fitz.open(str(exported_path))
        assert len(export_doc) > source_pages
        export_doc.close()

    def test_split_page_has_content(self, client):
        """The new page created by split has text content."""
        edit_data = self._trigger_page_split(client)
        if not edit_data.get("reflow", {}).get("page_added"):
            pytest.skip("Edit didn't trigger page split")

        new_page_num = edit_data["reflow"]["new_page_number"]

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        export_doc = fitz.open(str(exported_path))
        # New page should have text (blocks moved from overflow)
        new_page_text = export_doc[new_page_num - 1].get_text("text")
        export_doc.close()

        assert len(new_page_text.strip()) > 0

    def test_massive_edit_text_in_export(self, client):
        """The massive edit text appears somewhere in the export."""
        edit_data = self._trigger_page_split(client)
        if not edit_data.get("reflow", {}).get("page_added"):
            pytest.skip("Edit didn't trigger page split")

        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        export_doc = fitz.open(str(exported_path))
        all_text = ""
        for page in export_doc:
            all_text += page.get_text("text")
        export_doc.close()

        # The massive edit text should be present
        assert "spectrometer thermal requirement" in all_text


# ─── Export file download ─────────────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportDownload:
    """Test that exported files can be downloaded via /document/download."""

    def test_download_exported_file(self, client):
        """Exported file is downloadable via the download endpoint."""
        export_res = client.post("/document/export")
        data = export_res.json()
        exported_path = data["path"]

        download_res = client.get(f"/document/download?path={exported_path}")
        assert download_res.status_code == 200
        assert len(download_res.content) > 0
        # Should be a PDF
        assert download_res.content[:4] == b"%PDF"

    def test_download_nonexistent_file_fails(self, client):
        """Downloading a non-existent file returns 404."""
        res = client.get("/document/download?path=/nonexistent/file.pdf")
        assert res.status_code == 404


# ─── Export session tracking ──────────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportSessionTracking:
    """Test that export is tracked in the session journal."""

    def test_export_recorded_in_session(self, client):
        """Export action appears in session actions."""
        client.post("/document/export")

        res = client.get("/session/actions")
        data = res.json()
        actions = data["actions"]

        # Should have at least one DOCUMENT_EXPORTED action
        export_actions = [a for a in actions if a.get("action_type") == "document_exported"]
        assert len(export_actions) >= 1

    def test_multiple_exports_tracked(self, client):
        """Multiple exports are all tracked."""
        client.post("/document/export")
        client.post("/document/export")

        res = client.get("/session/actions")
        data = res.json()
        actions = data["actions"]

        export_actions = [a for a in actions if a.get("action_type") == "document_exported"]
        assert len(export_actions) >= 2


# ─── Export content integrity ─────────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportContentIntegrity:
    """Verify the exported PDF content integrity."""

    def test_export_page_dimensions_match_source(self, client):
        """Exported pages have same dimensions as source."""
        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        source_doc = fitz.open(str(HSI_PDF))
        export_doc = fitz.open(str(exported_path))

        for i in range(min(len(source_doc), len(export_doc))):
            src_rect = source_doc[i].rect
            exp_rect = export_doc[i].rect
            # Allow small tolerance for re-rendered pages
            assert abs(src_rect.width - exp_rect.width) < 5, f"Page {i+1} width mismatch"
            assert abs(src_rect.height - exp_rect.height) < 5, f"Page {i+1} height mismatch"

        source_doc.close()
        export_doc.close()

    def test_unedited_export_text_matches_source(self, client):
        """Full text of unedited export matches source document."""
        res = client.post("/document/export")
        data = res.json()
        exported_path = Path(data["path"])

        source_doc = fitz.open(str(HSI_PDF))
        export_doc = fitz.open(str(exported_path))

        for i in range(len(source_doc)):
            src_text = source_doc[i].get_text("text")
            exp_text = export_doc[i].get_text("text")
            assert src_text == exp_text, f"Page {i+1} text differs (unedited)"

        source_doc.close()
        export_doc.close()
