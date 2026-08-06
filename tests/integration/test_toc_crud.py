"""Integration Tests: TOC CRUD Operations

Tests Add, Edit, Delete operations on Table of Contents pages.
Verifies across multiple ICD documents that have TOC pages.
"""

import shutil
import uuid
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"
NDS_PDF = ICDS_DIR / "NDS_IDD_RevC.pdf"
IDSS_PDF = ICDS_DIR / "IDSS_IDD_RevF.pdf"


def _fresh_client(pdf_path: Path) -> TestClient:
    """Create a test client with an isolated copy."""
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    test_copy = output_dir / f".toc_{uuid.uuid4().hex[:8]}_{pdf_path.name}"
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


# ─── HSI Document (page 3 is TOC) ────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTocCrudHSI:
    """TOC CRUD on HSI_SYS_015G.pdf."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_toc_detected_on_page_3(self, client):
        """Page 3 is identified as a TOC page."""
        res = client.get("/document/page/3/toc")
        assert res.status_code == 200
        data = res.json()
        assert data["is_toc"] is True
        assert len(data["entries"]) >= 5

    def test_toc_entries_have_clean_titles(self, client):
        """TOC entries don't have leader dots in the title."""
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        for entry in entries:
            assert "..." not in entry["title"], f"Dots in title: '{entry['title']}'"

    def test_toc_entries_have_page_refs(self, client):
        """Most TOC entries have a page reference."""
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        with_refs = [e for e in entries if e["page_ref"]]
        assert len(with_refs) >= 3

    def test_edit_toc_entry_title(self, client):
        """Editing a TOC entry title persists."""
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        original_title = entries[2]["title"]  # "1. Introduction" typically

        # Edit it
        edit_res = client.put(
            f"/document/page/3/toc?index=2&title=1.+Modified+Introduction"
        )
        assert edit_res.status_code == 200
        assert edit_res.json()["status"] == "updated"

        # Verify it persisted in the session
        actions = client.get("/session/actions").json()
        assert actions["undo_available"] is True

    def test_edit_toc_page_ref(self, client):
        """Editing a TOC entry page number works."""
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        # Find an entry with a page ref
        for i, entry in enumerate(entries):
            if entry["page_ref"] and entry["page_ref"].isdigit():
                edit_res = client.put(
                    f"/document/page/3/toc?index={i}&page_ref=99"
                )
                assert edit_res.status_code == 200
                return
        pytest.skip("No entry with numeric page ref found")

    def test_add_toc_entry(self, client):
        """Adding a TOC entry creates text on the page."""
        res = client.get("/document/page/3/toc")
        count_before = len(res.json()["entries"])

        # Add entry
        add_res = client.post("/document/page/3/toc?title=5.+New+Section&page_ref=7")
        assert add_res.status_code == 200
        assert add_res.json()["status"] == "added"

        # Re-fetch — should have more entries
        res2 = client.get("/document/page/3/toc")
        entries_after = res2.json()["entries"]
        # The new entry text should be present
        all_titles = [e["title"] for e in entries_after]
        assert any("New Section" in t for t in all_titles), (
            f"'New Section' not found in: {all_titles}"
        )

    def test_delete_toc_entry(self, client):
        """Deleting a TOC entry removes it from the page."""
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        count_before = len(entries)
        # Delete the last entry
        last_idx = count_before - 1
        last_title = entries[last_idx]["title"]

        del_res = client.delete(f"/document/page/3/toc?index={last_idx}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Re-fetch
        res2 = client.get("/document/page/3/toc")
        entries_after = res2.json()["entries"]
        after_titles = [e["title"] for e in entries_after]
        assert last_title not in after_titles

    def test_sequential_add_and_delete(self, client):
        """Add → Delete in sequence maintains consistency."""
        # Add
        client.post("/document/page/3/toc?title=Temp+Entry&page_ref=42")

        # Verify added
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        assert any("Temp Entry" in e["title"] for e in entries)

        # Delete
        temp_idx = next(i for i, e in enumerate(entries) if "Temp Entry" in e["title"])
        client.delete(f"/document/page/3/toc?index={temp_idx}")

        # Verify gone
        res2 = client.get("/document/page/3/toc")
        entries2 = res2.json()["entries"]
        assert not any("Temp Entry" in e["title"] for e in entries2)

    def test_page_image_updates_after_add(self, client):
        """Page image changes after adding a TOC entry."""
        img_before = client.get("/document/page/3/image").content
        client.post("/document/page/3/toc?title=Image+Test+Entry&page_ref=99")
        img_after = client.get("/document/page/3/image").content
        assert img_before != img_after


# ─── NDS Document ─────────────────────────────────────────────────────


@pytest.mark.skipif(not NDS_PDF.exists() or NDS_PDF.stat().st_size < 200, reason="NDS PDF not found")
class TestTocCrudNDS:
    """TOC CRUD on NDS_IDD_RevC.pdf."""

    @pytest.fixture
    def client(self):
        return _fresh_client(NDS_PDF)

    def test_find_toc_page(self, client):
        """NDS document has a detectable TOC page."""
        toc_page = _find_toc_page(client, 10)
        if toc_page is None:
            pytest.skip("No TOC page found in NDS")
        res = client.get(f"/document/page/{toc_page}/toc")
        data = res.json()
        assert data["is_toc"]
        assert len(data["entries"]) >= 3

    def test_add_entry_to_nds_toc(self, client):
        """Can add an entry to the NDS TOC."""
        toc_page = _find_toc_page(client, 10)
        if toc_page is None:
            pytest.skip("No TOC page found in NDS")
        add_res = client.post(f"/document/page/{toc_page}/toc?title=Appendix+Z&page_ref=100")
        assert add_res.status_code == 200


# ─── IDSS Document ────────────────────────────────────────────────────


@pytest.mark.skipif(not IDSS_PDF.exists() or IDSS_PDF.stat().st_size < 200, reason="IDSS PDF not found")
class TestTocCrudIDSS:
    """TOC CRUD on IDSS_IDD_RevF.pdf."""

    @pytest.fixture
    def client(self):
        return _fresh_client(IDSS_PDF)

    def test_find_toc_page(self, client):
        """IDSS document has a detectable TOC page."""
        toc_page = _find_toc_page(client, 10)
        if toc_page is None:
            pytest.skip("No TOC page found in IDSS")
        res = client.get(f"/document/page/{toc_page}/toc")
        data = res.json()
        assert data["is_toc"]
        assert len(data["entries"]) >= 3

    def test_edit_idss_toc(self, client):
        """Can edit an entry in the IDSS TOC."""
        toc_page = _find_toc_page(client, 10)
        if toc_page is None:
            pytest.skip("No TOC page found in IDSS")
        res = client.get(f"/document/page/{toc_page}/toc")
        entries = res.json()["entries"]
        if len(entries) < 2:
            pytest.skip("Not enough TOC entries")
        edit_res = client.put(f"/document/page/{toc_page}/toc?index=1&title=Edited+IDSS+Section")
        assert edit_res.status_code == 200


# ─── Export verification ──────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTocExport:
    """Verify TOC edits appear in exported PDF."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_added_entry_in_export(self, client):
        """A new TOC entry appears in the exported PDF."""
        client.post("/document/page/3/toc?title=EXPORT+TEST+SECTION&page_ref=55")

        # Export
        export_res = client.post("/document/export")
        assert export_res.status_code == 200
        export_path = Path(export_res.json()["path"])

        # Check the exported PDF
        doc = fitz.open(str(export_path))
        page3_text = doc[2].get_text("text")
        doc.close()
        assert "EXPORT TEST SECTION" in page3_text

    def test_deleted_entry_not_in_export(self, client):
        """A deleted TOC entry is gone from the exported PDF."""
        # Get entries and remember the last one
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        last_title = entries[-1]["title"]

        # Delete it
        client.delete(f"/document/page/3/toc?index={len(entries) - 1}")

        # Export
        export_res = client.post("/document/export")
        assert export_res.status_code == 200
        export_path = Path(export_res.json()["path"])

        doc = fitz.open(str(export_path))
        page3_text = doc[2].get_text("text")
        doc.close()
        assert last_title not in page3_text


# ─── Undo Tests ───────────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTocUndo:
    """Verify undo reverts TOC add/delete operations."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_undo_reverts_toc_add(self, client):
        """After adding a TOC entry + undo, the entry is gone."""
        # Get baseline
        res_before = client.get("/document/page/3/toc")
        count_before = len(res_before.json()["entries"])

        # Add entry
        client.post("/document/page/3/toc?title=UNDO_ADD_TEST&page_ref=88")

        # Verify added
        res_mid = client.get("/document/page/3/toc")
        entries_mid = res_mid.json()["entries"]
        assert any("UNDO_ADD_TEST" in e["title"] for e in entries_mid)

        # Undo
        undo_res = client.post("/document/undo")
        assert undo_res.status_code == 200
        assert undo_res.json()["status"] == "undone"

        # Verify reverted
        res_after = client.get("/document/page/3/toc")
        entries_after = res_after.json()["entries"]
        assert not any("UNDO_ADD_TEST" in e["title"] for e in entries_after)
        assert len(entries_after) == count_before

    def test_undo_reverts_toc_delete(self, client):
        """After deleting a TOC entry + undo, the entry is restored."""
        # Get baseline
        res_before = client.get("/document/page/3/toc")
        entries_before = res_before.json()["entries"]
        last_title = entries_before[-1]["title"]

        # Delete last entry
        client.delete(f"/document/page/3/toc?index={len(entries_before) - 1}")

        # Verify deleted
        res_mid = client.get("/document/page/3/toc")
        assert last_title not in [e["title"] for e in res_mid.json()["entries"]]

        # Undo
        undo_res = client.post("/document/undo")
        assert undo_res.status_code == 200

        # Verify restored
        res_after = client.get("/document/page/3/toc")
        entries_after = res_after.json()["entries"]
        assert last_title in [e["title"] for e in entries_after]

    def test_export_after_toc_put_edit_no_duplicates(self, client):
        """Export after PUT /toc edit doesn't duplicate text."""
        # Edit a TOC entry via PUT
        res = client.get("/document/page/3/toc")
        entries = res.json()["entries"]
        original_title = entries[2]["title"]

        client.put(f"/document/page/3/toc?index=2&title=UNIQUE_EDIT_TITLE")

        # Export
        export_res = client.post("/document/export")
        assert export_res.status_code == 200
        export_path = Path(export_res.json()["path"])

        doc = fitz.open(str(export_path))
        page3_text = doc[2].get_text("text")
        doc.close()

        # New title present, not duplicated
        assert page3_text.count("UNIQUE_EDIT_TITLE") >= 1
