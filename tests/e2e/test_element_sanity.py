"""E2E Test: Element Overlay Sanity

Tests that the element overlay generation produces correctly-sized
clickable regions. Guards against the two-column merge bug where
spans from different columns merge into one oversized element.

Key invariants:
- No element should span the full page height (>600pt = likely bug)
- No element should span the full page width on a multi-column page
- Two-column pages should have elements in both halves
- Each element's text should be accessible (non-empty)
- Element bounding boxes should not be zero-area
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
ALL_PDFS = list(ICDS_DIR.glob("*.pdf")) if ICDS_DIR.exists() else []


@pytest.fixture
def client():
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    return c


@pytest.mark.skipif(not ALL_PDFS, reason="No PDFs found")
class TestElementOverlaySanity:
    """Guard against element merging bugs."""

    @pytest.mark.parametrize("pdf", ALL_PDFS, ids=[p.name for p in ALL_PDFS])
    def test_no_full_page_height_elements(self, client, pdf):
        """No element should span >80% of page height (likely column merge bug)."""
        client.post(f"/document/open?pdf_path={pdf}")

        import fitz
        doc = fitz.open(str(pdf))
        total_pages = doc.page_count
        page_height = doc[0].rect.height
        doc.close()

        max_allowed_height = page_height * 0.80  # 80% of page height

        for page_num in range(1, min(total_pages + 1, 6)):  # First 5 pages
            res = client.get(f"/document/page/{page_num}/elements")
            if res.status_code != 200:
                continue
            elements = res.json().get("elements", [])

            for i, elem in enumerate(elements):
                bbox = elem["bbox"]
                height = bbox["y1"] - bbox["y0"]
                assert height < max_allowed_height, (
                    f"{pdf.name} page {page_num} element [{i}] is {height:.0f}pt tall "
                    f"(>{max_allowed_height:.0f}pt threshold). "
                    f"Text: '{elem['text'][:50]}...'. "
                    f"This may indicate a column-merge bug."
                )

    def test_two_column_page_has_separate_elements(self, client):
        """TSAFE page 2 (known two-column) should have elements in both halves."""
        tsafe = ICDS_DIR / "20130010957.pdf"
        if not tsafe.exists():
            pytest.skip("TSAFE PDF not found")

        client.post(f"/document/open?pdf_path={tsafe}")
        res = client.get("/document/page/2/elements")
        elements = res.json()["elements"]

        # Should have elements with x0 < 300 (left column)
        left_elements = [e for e in elements if e["bbox"]["x0"] < 300]
        # And elements with x0 > 300 (right column)
        right_elements = [e for e in elements if e["bbox"]["x0"] > 300]

        assert len(left_elements) > 2, "Left column should have multiple elements"
        assert len(right_elements) > 2, "Right column should have multiple elements"

    def test_two_column_elements_dont_span_both_columns(self, client):
        """On a two-column page, no element should span both columns."""
        tsafe = ICDS_DIR / "20130010957.pdf"
        if not tsafe.exists():
            pytest.skip("TSAFE PDF not found")

        client.post(f"/document/open?pdf_path={tsafe}")
        res = client.get("/document/page/2/elements")
        elements = res.json()["elements"]

        page_width = 612  # Standard US Letter

        for i, elem in enumerate(elements):
            bbox = elem["bbox"]
            width = bbox["x1"] - bbox["x0"]
            # No body element should be wider than 60% of page
            # (single column is ~50% of page width)
            if bbox["y0"] > 60:  # Skip headers
                assert width < page_width * 0.60, (
                    f"Element [{i}] spans {width:.0f}pt "
                    f"(>{page_width * 0.60:.0f}pt = both columns). "
                    f"Text: '{elem['text'][:40]}'"
                )

    @pytest.mark.parametrize("pdf", ALL_PDFS, ids=[p.name for p in ALL_PDFS])
    def test_elements_have_nonzero_area(self, client, pdf):
        """Every element must have positive width and height."""
        client.post(f"/document/open?pdf_path={pdf}")
        res = client.get("/document/page/1/elements")
        if res.status_code != 200:
            return
        elements = res.json().get("elements", [])

        for i, elem in enumerate(elements):
            bbox = elem["bbox"]
            width = bbox["x1"] - bbox["x0"]
            height = bbox["y1"] - bbox["y0"]
            assert width > 0, f"Element [{i}] has zero width"
            assert height > 0, f"Element [{i}] has zero height"

    @pytest.mark.parametrize("pdf", ALL_PDFS, ids=[p.name for p in ALL_PDFS])
    def test_elements_have_text(self, client, pdf):
        """Every element must have non-empty text content."""
        client.post(f"/document/open?pdf_path={pdf}")
        res = client.get("/document/page/1/elements")
        if res.status_code != 200:
            return
        elements = res.json().get("elements", [])

        for i, elem in enumerate(elements):
            assert elem["text"].strip(), (
                f"Element [{i}] has empty text. "
                f"Type: {elem['type']}, bbox: {elem['bbox']}"
            )

    def test_element_count_reasonable(self, client):
        """Pages should have a reasonable number of elements (not 0, not 1000)."""
        hsi = ICDS_DIR / "HSI_SYS_015G.pdf"
        if not hsi.exists():
            pytest.skip("HSI PDF not found")

        client.post(f"/document/open?pdf_path={hsi}")

        for page_num in range(1, 9):
            res = client.get(f"/document/page/{page_num}/elements")
            elements = res.json().get("elements", [])
            assert len(elements) >= 1, f"Page {page_num} has no elements"
            assert len(elements) < 200, f"Page {page_num} has too many elements ({len(elements)})"
