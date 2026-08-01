"""E2E Test: Export Download Endpoint (Browser Flow)

Tests GET /document/export-download — the endpoint the browser actually
calls when the user clicks "Export" or "Download". This is distinct from
POST /document/export which only generates the file.

Critical coverage gap found: the browser uses export-download, not export.
These tests ensure the download endpoint uses the page-patching system.
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
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    c.post(f"/document/open?pdf_path={HSI_PDF}")
    return c


# ─── Basic export-download functionality ──────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportDownloadBasic:
    """Test the GET /document/export-download endpoint."""

    def test_returns_pdf_content(self, client):
        """export-download returns a valid PDF file."""
        res = client.get("/document/export-download?filename=test.pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/octet-stream"
        # PDF magic bytes
        assert res.content[:5] == b"%PDF-"

    def test_correct_page_count_no_edits(self, client):
        """Without edits, export has same page count as source."""
        res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=res.content, filetype="pdf")
        assert len(doc) == 8  # HSI has 8 pages
        doc.close()

    def test_unedited_text_matches_source(self, client):
        """Without edits, page text matches source exactly."""
        res = client.get("/document/export-download?filename=test.pdf")
        doc_export = fitz.open(stream=res.content, filetype="pdf")
        doc_source = fitz.open(str(HSI_PDF))

        for i in range(len(doc_source)):
            assert doc_export[i].get_text("text") == doc_source[i].get_text("text"), (
                f"Page {i+1} text differs without any edits"
            )

        doc_export.close()
        doc_source.close()


# ─── Export-download with paragraph edits (4.1, 4.2) ─────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportDownloadParagraphEdits:
    """Test export-download preserves paragraph edits (sections 4.1, 4.2)."""

    def test_42_tbr_replacement_in_export(self, client):
        """4.2: (TBR-UCB-102) -> 0.5 appears in downloaded PDF."""
        # Find and edit
        res = client.get("/document/page/5/elements")
        block = next(
            e for e in res.json()["elements"]
            if e["id"] and "TBR-UCB-102" in e["text"]
        )
        new_text = block["text"].replace("(TBR-UCB-102)", "0.5")
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        # Download via the browser endpoint
        res = client.get("/document/export-download?filename=test.pdf")
        assert res.status_code == 200

        doc = fitz.open(stream=res.content, filetype="pdf")
        p5_text = doc[4].get_text("text")
        doc.close()

        assert "0.5" in p5_text, "Replacement '0.5' not in exported page 5"
        assert "(TBR-UCB-102)" not in p5_text, "Old TBR still in exported page 5"

    def test_other_pages_unchanged_after_edit(self, client):
        """Pages not edited remain identical to source after export-download."""
        # Edit page 5
        res = client.get("/document/page/5/elements")
        block = next(
            e for e in res.json()["elements"]
            if e["id"] and "TBR-UCB-102" in e["text"]
        )
        new_text = block["text"].replace("(TBR-UCB-102)", "0.5")
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        # Download
        res = client.get("/document/export-download?filename=test.pdf")
        doc_export = fitz.open(stream=res.content, filetype="pdf")
        doc_source = fitz.open(str(HSI_PDF))

        # Pages 1-4, 6-8 should be identical
        for i in [0, 1, 2, 3, 5, 6, 7]:
            assert doc_export[i].get_text("text") == doc_source[i].get_text("text"), (
                f"Page {i+1} changed unexpectedly"
            )

        doc_export.close()
        doc_source.close()


# ─── Export-download with table edit (4.3) ────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportDownloadTableEdit:
    """Test export-download preserves table cell edits (section 4.3)."""

    def test_43_table_edit_in_export(self, client):
        """4.3: 30W (TBR-UCB-110) -> 25W appears in downloaded PDF."""
        res = client.get("/document/page/7/elements")
        block = next(
            e for e in res.json()["elements"]
            if e["id"] and "30W" in e["text"]
        )
        new_text = block["text"].replace("30W (TBR-UCB-110)", "25W")
        client.put(f"/document/block/{block['id']}", json={"new_text": new_text})

        # Download
        res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=res.content, filetype="pdf")
        p7_text = doc[6].get_text("text")
        doc.close()

        assert "25W" in p7_text, "25W not in exported page 7"
        assert "30W (TBR-UCB-110)" not in p7_text, "Old table value still in export"


# ─── Export-download with page overflow (4.4) ─────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestExportDownloadPageOverflow:
    """Test export-download handles page overflow from 4.4."""

    def _trigger_overflow(self, client):
        """Edit page 7 with long paste to trigger overflow."""
        res = client.get("/document/page/7/elements")
        block = next(
            e for e in res.json()["elements"]
            if e["id"] and "Cryostat" in e["text"] and "Cooler" in e["text"]
        )
        paste = (
            "The Spectrometer consists of a Cryostat that houses nine "
            "segmented high-purity Germanium detectors that provide primary "
            "science data across the energy range of 3 keV to 17 MeV. These "
            "detectors are actively cooled to liquid nitrogen temperatures "
            "(approximately 77K) by the helium-based Stirling cycle mechanical "
            "cryocooler. The cooler is electrically driven by the Cooler Power "
            "Controller (CPC), which in turn is commanded and monitored by the "
            "Instrument Data Processing Unit (IDPU). The Spectrometer assembly "
            "also includes the attenuator shutter mechanism for managing photon "
            "rates during solar flares, the Charge Sensitive Amplifiers (CSA) "
            "for signal conditioning, and the High Voltage Filters for detector "
            "biasing, all mounted externally on the Cryostat structure."
        )
        edit_res = client.put(
            f"/document/block/{block['id']}", json={"new_text": paste}
        )
        return edit_res.json()

    def test_44_overflow_adds_page(self, client):
        """4.4: Long paste triggers page overflow, export has 9 pages."""
        data = self._trigger_overflow(client)
        assert data["reflow"]["page_added"] is True

        res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=res.content, filetype="pdf")
        assert len(doc) == 9, f"Expected 9 pages, got {len(doc)}"
        doc.close()

    def test_44_paste_text_on_page_7(self, client):
        """4.4: The pasted text appears on page 7 of the export."""
        self._trigger_overflow(client)

        res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=res.content, filetype="pdf")
        p7_text = doc[6].get_text("text")
        doc.close()

        assert "Germanium" in p7_text, "Paste text not on page 7"
        assert "Cooler operation" not in p7_text, "Original text still on page 7"

    def test_44_overflow_heading_on_page_8(self, client):
        """4.4: The overflow heading (4. Electrical Interface) is on page 8."""
        self._trigger_overflow(client)

        res = client.get("/document/export-download?filename=test.pdf")
        doc = fitz.open(stream=res.content, filetype="pdf")
        p8_text = doc[7].get_text("text")
        doc.close()

        assert "Electrical Interface" in p8_text or "4." in p8_text

    def test_44_original_page8_becomes_page9(self, client):
        """4.4: Original page 8 content moves to page 9."""
        self._trigger_overflow(client)

        res = client.get("/document/export-download?filename=test.pdf")
        doc_export = fitz.open(stream=res.content, filetype="pdf")
        doc_source = fitz.open(str(HSI_PDF))

        # Original page 8 text should now be on page 9
        source_p8_text = doc_source[7].get_text("text")
        export_p9_text = doc_export[8].get_text("text")

        doc_export.close()
        doc_source.close()

        assert source_p8_text == export_p9_text, (
            "Original page 8 content not found on export page 9"
        )
