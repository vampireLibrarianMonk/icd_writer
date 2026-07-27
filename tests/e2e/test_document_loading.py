"""E2E Test: Document Loading and Page Navigation

Tests opening documents and navigating pages:
- Open a PDF by path
- Verify page count
- Navigate to specific pages
- Get page images
- Get page data (text blocks)
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
HSI_PDF = ICDS_DIR / "digital" / "HSI_SYS_015G.pdf"
LVC_PDF = ICDS_DIR / "digital" / "20150010976.pdf"


@pytest.fixture
def client():
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    return c


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestDocumentOpen:
    """Opening documents via the API."""

    def test_open_document_success(self, client):
        """POST /document/open loads a PDF and returns page count."""
        res = client.post(f"/document/open?pdf_path={HSI_PDF}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["pages"] == 8
        assert "method" in data

    def test_open_nonexistent_returns_404(self, client):
        """POST /document/open with bad path returns 404."""
        res = client.post("/document/open?pdf_path=/tmp/does_not_exist.pdf")
        assert res.status_code == 404

    def test_open_records_in_session(self, client):
        """Opening a document records the path in the session."""
        client.post(f"/document/open?pdf_path={HSI_PDF}")
        res = client.get("/session")
        assert res.status_code == 200
        data = res.json()
        assert "HSI_SYS_015G" in data["document"]


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPageNavigation:
    """Getting page data and images."""

    @pytest.fixture(autouse=True)
    def _open_doc(self, client):
        client.post(f"/document/open?pdf_path={HSI_PDF}")

    def test_get_page_data(self, client):
        """GET /document/page/{n} returns blocks for that page."""
        res = client.get("/document/page/1")
        assert res.status_code == 200
        data = res.json()
        assert data["page_number"] == 1
        assert "blocks" in data
        assert len(data["blocks"]) > 0

    def test_get_page_blocks_have_required_fields(self, client):
        """Each block has id, text, bbox, type."""
        res = client.get("/document/page/1")
        data = res.json()
        for block in data["blocks"]:
            assert "id" in block
            assert "text" in block
            assert "bbox" in block
            assert "x0" in block["bbox"]
            assert "y0" in block["bbox"]
            assert "x1" in block["bbox"]
            assert "y1" in block["bbox"]

    def test_get_page_image_returns_png(self, client):
        """GET /document/page/{n}/image returns a PNG image."""
        res = client.get("/document/page/1/image")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert len(res.content) > 1000  # Non-trivial image

    def test_all_pages_accessible(self, client):
        """Every page from 1 to N returns valid data."""
        for page_num in range(1, 9):  # HSI has 8 pages
            res = client.get(f"/document/page/{page_num}")
            assert res.status_code == 200, f"Page {page_num} failed"
            data = res.json()
            assert data["page_number"] == page_num

    def test_invalid_page_number(self, client):
        """Pages beyond the document range return an error."""
        res = client.get("/document/page/99")
        assert res.status_code in (400, 404, 422)


@pytest.mark.skipif(not LVC_PDF.exists(), reason="LVC PDF not found")
class TestLargerDocument:
    """Test with the larger LVC ICD (35 pages)."""

    def test_open_lvc(self, client):
        """LVC ICD loads successfully with correct page count."""
        res = client.post(f"/document/open?pdf_path={LVC_PDF}")
        assert res.status_code == 200
        data = res.json()
        assert data["pages"] == 35

    def test_lvc_page_15_has_content(self, client):
        """Middle pages of a large document have extractable content."""
        client.post(f"/document/open?pdf_path={LVC_PDF}")
        res = client.get("/document/page/15")
        assert res.status_code == 200
        data = res.json()
        assert len(data["blocks"]) > 0
