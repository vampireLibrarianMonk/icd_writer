"""E2E Test: Page Image Endpoint

Tests GET /document/page/{N}/image which is the core preview mechanism:
- Unedited pages serve the original PDF page directly (fast path)
- Edited pages re-render from Document IR via WeasyPrint (slow path)
- Returns valid PNG image data
- Cache-Control headers prevent stale images
- Invalid page numbers return appropriate errors
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from tests.conftest import skip_no_weasyprint

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


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


# ─── Unedited page rendering (fast path) ──────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestUnEditedPageImage:
    """Test page images for pages that have NOT been edited."""

    def test_returns_png_image(self, client):
        """Unedited page returns a valid PNG image."""
        res = client.get("/document/page/1/image")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert res.content[:8] == PNG_MAGIC

    def test_image_has_substantial_size(self, client):
        """Page image has reasonable size (not empty or trivial)."""
        res = client.get("/document/page/1/image")
        # A real page at 150 DPI should be at least 10KB
        assert len(res.content) > 10_000

    def test_cache_control_no_store(self, client):
        """Response includes no-cache headers to prevent stale previews."""
        res = client.get("/document/page/1/image")
        cache_header = res.headers.get("cache-control", "")
        assert "no-store" in cache_header or "no-cache" in cache_header

    def test_all_pages_render(self, client):
        """Every page in the document returns a valid image."""
        # HSI has 8 pages
        for page_num in range(1, 9):
            res = client.get(f"/document/page/{page_num}/image")
            assert res.status_code == 200, f"Page {page_num} failed"
            assert res.content[:8] == PNG_MAGIC, f"Page {page_num} not PNG"

    def test_different_pages_produce_different_images(self, client):
        """Different pages produce different image data."""
        res1 = client.get("/document/page/1/image")
        res4 = client.get("/document/page/4/image")
        # Different pages should produce different images
        assert res1.content != res4.content

    def test_repeated_requests_consistent(self, client):
        """Same page returns consistent image on repeated requests."""
        res1 = client.get("/document/page/3/image")
        res2 = client.get("/document/page/3/image")
        # Should be byte-identical (same source, no edits)
        assert res1.content == res2.content


# ─── Edited page rendering (IR re-render path) ────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestEditedPageImage:
    """Test page images for pages that HAVE been edited."""

    def _edit_page5_block(self, client, new_text: str) -> str:
        """Helper: edit the first block on page 5."""
        res = client.get("/document/page/5/elements")
        elements = res.json()["elements"]
        # Find first block with an ID (from Document IR)
        target = next((e for e in elements if e["id"]), None)
        assert target is not None, "No editable block found on page 5"

        edit_res = client.put(
            f"/document/block/{target['id']}",
            json={"new_text": new_text},
        )
        assert edit_res.status_code == 200
        return target["id"]

    def test_edited_page_still_returns_png(self, client):
        """After editing, the page image is still a valid PNG."""
        self._edit_page5_block(client, "Edited text for image test")
        res = client.get("/document/page/5/image")
        assert res.status_code == 200
        assert res.content[:8] == PNG_MAGIC

    def test_edited_page_image_differs_from_original(self, client):
        """The page image changes after an edit."""
        # Get image before edit
        before = client.get("/document/page/5/image")
        assert before.status_code == 200

        # Edit the page
        self._edit_page5_block(client, "COMPLETELY_UNIQUE_EDIT_TEXT_XYZ")

        # Get image after edit
        after = client.get("/document/page/5/image")
        assert after.status_code == 200

        # Images should differ (text changed)
        assert before.content != after.content

    def test_unedited_page_unchanged_after_other_edit(self, client):
        """Editing page 5 doesn't affect page 1's image."""
        # Get page 1 image before any edits
        before = client.get("/document/page/1/image")

        # Edit page 5
        self._edit_page5_block(client, "Only page 5 changes")

        # Page 1 image should be identical
        after = client.get("/document/page/1/image")
        assert before.content == after.content

    def test_multiple_edits_reflected(self, client):
        """Multiple edits to the same block update the preview each time."""
        self._edit_page5_block(client, "First edit version")
        img1 = client.get("/document/page/5/image").content

        self._edit_page5_block(client, "Second completely different edit")
        img2 = client.get("/document/page/5/image").content

        # Each edit should produce a different image
        assert img1 != img2

    def test_edited_page_has_reasonable_size(self, client):
        """Re-rendered page image has reasonable file size."""
        self._edit_page5_block(client, "Test content for size check")
        res = client.get("/document/page/5/image")
        # IR-rendered pages should still produce substantial PNGs
        # (at least 5KB — text-only pages are smaller than original)
        assert len(res.content) > 5_000


# ─── Error handling ───────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPageImageErrors:
    """Test error cases for the page image endpoint."""

    def test_page_zero_invalid(self, client):
        """Page 0 is invalid (1-based indexing)."""
        res = client.get("/document/page/0/image")
        assert res.status_code == 400

    def test_negative_page_invalid(self, client):
        """Negative page numbers are invalid."""
        res = client.get("/document/page/-1/image")
        # FastAPI may return 422 for invalid path param or 400
        assert res.status_code in (400, 422)

    def test_page_beyond_document_invalid(self, client):
        """Page number beyond document length returns error."""
        res = client.get("/document/page/999/image")
        assert res.status_code == 400

    def test_no_document_loaded(self, fresh_client):
        """Requesting image without loading a document returns 404."""
        fresh_client.post("/session/start")
        res = fresh_client.get("/document/page/1/image")
        assert res.status_code == 404


# ─── Performance characteristics ──────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPageImagePerformance:
    """Verify performance characteristics of the two rendering paths."""

    def test_unedited_page_fast(self, client):
        """Unedited pages should respond quickly (direct from source)."""
        import time

        start = time.perf_counter()
        for _ in range(3):
            res = client.get("/document/page/1/image")
            assert res.status_code == 200
        elapsed = time.perf_counter() - start

        # 3 requests for unedited pages should complete in under 10s
        assert elapsed < 10.0, f"Unedited page images too slow: {elapsed:.1f}s for 3 requests"

    def test_edited_page_responds(self, client):
        """Edited page re-render completes within reasonable time."""
        import time

        # Edit page 5
        res = client.get("/document/page/5/elements")
        elements = res.json()["elements"]
        target = next((e for e in elements if e["id"]), None)
        if not target:
            pytest.skip("No editable block")

        client.put(f"/document/block/{target['id']}", json={"new_text": "Perf test edit"})

        start = time.perf_counter()
        res = client.get("/document/page/5/image")
        elapsed = time.perf_counter() - start

        assert res.status_code == 200
        # Re-rendering via WeasyPrint is slower but should still be < 30s
        assert elapsed < 30.0, f"Edited page re-render too slow: {elapsed:.1f}s"
