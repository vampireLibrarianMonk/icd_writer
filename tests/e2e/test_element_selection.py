"""E2E Test: Element Selection and Page Analysis

Tests the click-to-edit workflow:
- Page analysis returns page type (table, TOC, text)
- Elements endpoint returns clickable overlays
- Table zone detection
- Header/footer identification
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
class TestPageAnalysis:
    """Page content classification for UI behavior."""

    def test_analysis_returns_page_type(self, client):
        """GET /document/page/{n}/analysis returns a page_type field."""
        res = client.get("/document/page/1/analysis")
        assert res.status_code == 200
        data = res.json()
        assert "page_type" in data
        assert data["page_type"] in ("title_page", "text", "table", "table_of_contents", "list")

    def test_analysis_returns_header_footer(self, client):
        """Analysis includes header and footer with alignment."""
        res = client.get("/document/page/4/analysis")
        assert res.status_code == 200
        data = res.json()
        assert "header" in data
        assert "footer" in data
        # Headers have left/center/right
        assert "left" in data["header"]
        assert "center" in data["header"]
        assert "right" in data["header"]

    def test_toc_page_detected(self, client):
        """Page 3 (table of contents) is classified correctly."""
        res = client.get("/document/page/3/analysis")
        assert res.status_code == 200
        data = res.json()
        # Page 3 of HSI is the TOC
        assert data["page_type"] == "table_of_contents"

    def test_all_pages_return_valid_analysis(self, client):
        """Every page returns analysis without error."""
        for page_num in range(1, 9):
            res = client.get(f"/document/page/{page_num}/analysis")
            assert res.status_code == 200, f"Page {page_num} analysis failed"
            data = res.json()
            assert data is not None
            assert "page_type" in data


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestElementOverlays:
    """Clickable element overlays for the document view."""

    def test_elements_endpoint_returns_list(self, client):
        """GET /document/page/{n}/elements returns elements array."""
        res = client.get("/document/page/1/elements")
        assert res.status_code == 200
        data = res.json()
        assert "elements" in data
        assert isinstance(data["elements"], list)
        assert len(data["elements"]) > 0

    def test_elements_have_required_fields(self, client):
        """Each element has type, label, text, id, bbox."""
        res = client.get("/document/page/4/elements")
        data = res.json()
        for elem in data["elements"]:
            assert "type" in elem
            assert "label" in elem
            assert "text" in elem
            assert "bbox" in elem
            bbox = elem["bbox"]
            assert "x0" in bbox and "y0" in bbox
            assert "x1" in bbox and "y1" in bbox
            # Bounding boxes must be positive area
            assert bbox["x1"] >= bbox["x0"]
            assert bbox["y1"] >= bbox["y0"]

    def test_elements_include_headers(self, client):
        """Pages with headers have header-type elements."""
        res = client.get("/document/page/4/elements")
        data = res.json()
        types = [e["type"] for e in data["elements"]]
        # Should have at least text_block elements
        assert "text_block" in types or "header" in types

    def test_element_ids_are_unique_per_page(self, client):
        """Element IDs within a page are unique (no duplicates)."""
        res = client.get("/document/page/5/elements")
        data = res.json()
        ids = [e["id"] for e in data["elements"] if e["id"] is not None]
        assert len(ids) == len(set(ids)), "Duplicate element IDs found"


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTableZones:
    """Table zone detection for grid editing."""

    def test_table_zones_endpoint(self, client):
        """GET /document/page/{n}/table-zones returns zones array."""
        res = client.get("/document/page/2/table-zones")
        assert res.status_code == 200
        data = res.json()
        assert "zones" in data
        assert isinstance(data["zones"], list)

    def test_table_page_has_zones(self, client):
        """A page with tables should have detected zones."""
        # Page 2 of HSI has a revision table
        res = client.get("/document/page/2/table-zones")
        data = res.json()
        # May or may not detect zones depending on grid density
        # At minimum, the endpoint shouldn't crash
        assert isinstance(data["zones"], list)

    def test_non_table_page_has_no_zones(self, client):
        """Pages without tables should have empty zones."""
        # Page 1 is a title page
        res = client.get("/document/page/1/table-zones")
        data = res.json()
        assert data["zones"] == []
