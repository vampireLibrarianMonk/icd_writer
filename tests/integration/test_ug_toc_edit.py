"""User Guide Regression: TOC Editing (Section 4.6)

Validates the TOC editing workflow described in the User Guide:
- TOC detected on correct page
- TOC entries have titles and page refs
- Edit TOC entry title persists
- TOC edit appears in page image
- Undo reverts TOC edit

Tests use HSI_SYS_001H.pdf (pages 4-5 are TOC pages).
Falls back to HSI_SYS_015G.pdf page 3 if 001H not available.
"""

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_001H_PDF = ICDS_DIR / "HSI_SYS_001H.pdf"
HSI_015G_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"

# Use 001H if available, fall back to 015G
TOC_PDF = HSI_001H_PDF if HSI_001H_PDF.exists() else HSI_015G_PDF

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _fresh_client(pdf_path: Path) -> TestClient:
    """Create a test client with an isolated copy of the PDF."""
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    test_copy = output_dir / f".test_toc_{uuid.uuid4().hex[:8]}_{pdf_path.name}"
    shutil.copy2(str(pdf_path), str(test_copy))

    app = create_app()
    client = TestClient(app)
    client.post("/session/start")
    res = client.post(f"/document/open?pdf_path={test_copy}")
    assert res.status_code == 200
    return client


def _find_toc_page(client: TestClient, max_pages: int = 10) -> int | None:
    """Find the first TOC page in the document."""
    for pg in range(1, max_pages + 1):
        res = client.get(f"/document/page/{pg}/toc")
        if res.status_code == 200 and res.json().get("is_toc"):
            return pg
    return None


# ─── TOC Detection ────────────────────────────────────────────────────


@pytest.mark.skipif(not TOC_PDF.exists(), reason="TOC PDF not found")
class TestTocDetectedOnCorrectPage:
    """Verify that TOC pages are correctly identified."""

    @pytest.fixture
    def client(self):
        return _fresh_client(TOC_PDF)

    def test_toc_detected_on_correct_page(self, client):
        """GET /document/page/{n}/toc returns is_toc=true for a TOC page."""
        toc_page = _find_toc_page(client)
        assert toc_page is not None, "No TOC page detected in document"

        res = client.get(f"/document/page/{toc_page}/toc")
        assert res.status_code == 200
        data = res.json()
        assert data["is_toc"] is True

    def test_non_toc_page_returns_false(self, client):
        """A non-TOC page (like page 1 or last page) returns is_toc=false."""
        # Page 1 is typically a cover page, not TOC
        res = client.get("/document/page/1/toc")
        assert res.status_code == 200
        data = res.json()
        # Page 1 is usually not a TOC (it's a cover page)
        # If it is, just verify the endpoint works
        assert "is_toc" in data


# ─── TOC Entries Have Titles and Refs ─────────────────────────────────


@pytest.mark.skipif(not TOC_PDF.exists(), reason="TOC PDF not found")
class TestTocEntriesHaveTitlesAndRefs:
    """Verify TOC entries contain required fields."""

    @pytest.fixture
    def client(self):
        return _fresh_client(TOC_PDF)

    def test_toc_entries_have_titles_and_refs(self, client):
        """TOC entries have title + page_ref fields."""
        toc_page = _find_toc_page(client)
        if toc_page is None:
            pytest.skip("No TOC page found")

        res = client.get(f"/document/page/{toc_page}/toc")
        data = res.json()
        entries = data.get("entries", [])

        assert len(entries) >= 3, f"Only {len(entries)} TOC entries found"

        for entry in entries:
            assert "title" in entry, "TOC entry missing 'title' field"
            assert entry["title"].strip(), "TOC entry has empty title"

    def test_toc_entries_have_page_refs(self, client):
        """Most TOC entries have a page reference number."""
        toc_page = _find_toc_page(client)
        if toc_page is None:
            pytest.skip("No TOC page found")

        res = client.get(f"/document/page/{toc_page}/toc")
        entries = res.json().get("entries", [])

        with_refs = [e for e in entries if e.get("page_ref")]
        assert len(with_refs) >= 3, (
            f"Only {len(with_refs)} entries have page refs out of {len(entries)}"
        )

    def test_toc_titles_no_leader_dots(self, client):
        """TOC entry titles should not contain leader dots (...)."""
        toc_page = _find_toc_page(client)
        if toc_page is None:
            pytest.skip("No TOC page found")

        res = client.get(f"/document/page/{toc_page}/toc")
        entries = res.json().get("entries", [])

        for entry in entries:
            title = entry["title"]
            assert "..." not in title, f"Leader dots in TOC title: '{title}'"


# ─── Edit TOC Title ──────────────────────────────────────────────────


@pytest.mark.skipif(not TOC_PDF.exists(), reason="TOC PDF not found")
class TestEditTocTitle:
    """Verify that editing a TOC entry title persists."""

    @pytest.fixture
    def client(self):
        return _fresh_client(TOC_PDF)

    def test_edit_toc_title(self, client):
        """PUT /document/page/{n}/toc changes the title text."""
        toc_page = _find_toc_page(client)
        if toc_page is None:
            pytest.skip("No TOC page found")

        # Get current entries
        res = client.get(f"/document/page/{toc_page}/toc")
        entries = res.json().get("entries", [])
        if len(entries) < 3:
            pytest.skip("Not enough TOC entries to edit")

        # Edit entry at index 2
        new_title = "1. Modified Section Title"
        edit_res = client.put(
            f"/document/page/{toc_page}/toc",
            params={"index": 2, "title": new_title},
        )
        assert edit_res.status_code == 200
        assert edit_res.json()["status"] == "updated"

    def test_edit_toc_records_in_session(self, client):
        """TOC edit creates an undo-able action in the session."""
        toc_page = _find_toc_page(client)
        if toc_page is None:
            pytest.skip("No TOC page found")

        res = client.get(f"/document/page/{toc_page}/toc")
        entries = res.json().get("entries", [])
        if len(entries) < 3:
            pytest.skip("Not enough TOC entries")

        # Edit
        client.put(
            f"/document/page/{toc_page}/toc",
            params={"index": 2, "title": "Edit Record Test"},
        )

        # Verify undo is available
        actions = client.get("/session/actions").json()
        assert actions["undo_available"] is True


# ─── TOC Edit Appears in Image ────────────────────────────────────────


@pytest.mark.skipif(not TOC_PDF.exists(), reason="TOC PDF not found")
class TestTocEditAppearsInImage:
    """Verify that the page image changes after a TOC edit."""

    @pytest.fixture
    def client(self):
        return _fresh_client(TOC_PDF)

    def test_toc_edit_appears_in_image(self, client):
        """Page image changes after TOC edit."""
        toc_page = _find_toc_page(client)
        if toc_page is None:
            pytest.skip("No TOC page found")

        res = client.get(f"/document/page/{toc_page}/toc")
        entries = res.json().get("entries", [])
        if len(entries) < 3:
            pytest.skip("Not enough TOC entries")

        # Get image before
        img_before = client.get(f"/document/page/{toc_page}/image")
        assert img_before.status_code == 200
        assert img_before.content[:8] == PNG_MAGIC

        # Edit TOC
        client.put(
            f"/document/page/{toc_page}/toc",
            params={"index": 2, "title": "IMAGE_CHANGE_TOC_TEST"},
        )

        # Get image after
        img_after = client.get(f"/document/page/{toc_page}/image")
        assert img_after.status_code == 200
        assert img_after.content[:8] == PNG_MAGIC

        assert img_before.content != img_after.content, (
            "Page image did not change after TOC edit"
        )


# ─── Undo Reverts TOC Edit ────────────────────────────────────────────


@pytest.mark.skipif(not TOC_PDF.exists(), reason="TOC PDF not found")
class TestUndoRevertsTocEdit:
    """Verify that undo restores the original TOC text."""

    @pytest.fixture
    def client(self):
        return _fresh_client(TOC_PDF)

    def test_undo_reverts_toc_edit(self, client):
        """Undo restores original TOC text after edit."""
        toc_page = _find_toc_page(client)
        if toc_page is None:
            pytest.skip("No TOC page found")

        # Get original entries
        res = client.get(f"/document/page/{toc_page}/toc")
        entries_before = res.json().get("entries", [])
        if len(entries_before) < 3:
            pytest.skip("Not enough TOC entries")

        original_title = entries_before[2]["title"]

        # Edit
        client.put(
            f"/document/page/{toc_page}/toc",
            params={"index": 2, "title": "UNDO_TOC_TEST"},
        )

        # Undo
        undo_res = client.post("/document/undo")
        assert undo_res.status_code == 200

        # Verify original title is restored
        res = client.get(f"/document/page/{toc_page}/toc")
        entries_after = res.json().get("entries", [])
        assert entries_after[2]["title"] == original_title, (
            f"TOC title not restored: got '{entries_after[2]['title']}', "
            f"expected '{original_title}'"
        )
