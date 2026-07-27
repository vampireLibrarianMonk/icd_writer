"""E2E Test: TBD Dashboard

Tests the cross-document TBD tracking dashboard:
- Get dashboard data
- Ingest TBDs from documents
- Filter by status and type
- Update item status
- Verify stats accuracy
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestTBDDashboardEndpoints:
    """TBD Dashboard API endpoints."""

    def test_get_dashboard_returns_structure(self, client):
        """GET /tbd-dashboard returns stats and items."""
        res = client.get("/tbd-dashboard")
        assert res.status_code == 200
        data = res.json()
        assert "stats" in data
        assert "items" in data
        assert "correlations" in data

    def test_stats_have_required_fields(self, client):
        """Stats object contains all tracking fields."""
        res = client.get("/tbd-dashboard")
        data = res.json()
        stats = data["stats"]
        required_fields = [
            "total_items", "open_count", "assigned_count",
            "resolved_count", "verified_count", "tbd_count",
            "tbr_count", "in_shall_statements", "documents_count",
        ]
        for field in required_fields:
            assert field in stats, f"Missing field: {field}"

    def test_items_have_required_fields(self, client):
        """Each TBD item has the required structure."""
        res = client.get("/tbd-dashboard")
        data = res.json()
        for item in data["items"]:
            assert "item_id" in item
            assert "item_type" in item
            assert item["item_type"] in ("TBD", "TBR", "TBC", "TBS")
            assert "status" in item
            assert item["status"] in ("open", "assigned", "resolved", "verified")
            assert "document_title" in item
            assert "page_number" in item
            assert "context" in item
            assert "in_shall_statement" in item

    def test_filter_by_status(self, client):
        """Filtering by status returns only matching items."""
        res = client.get("/tbd-dashboard?status=open")
        assert res.status_code == 200
        data = res.json()
        for item in data["items"]:
            assert item["status"] == "open"

    def test_filter_by_type(self, client):
        """Filtering by item_type returns only matching items."""
        res = client.get("/tbd-dashboard?item_type=TBD")
        assert res.status_code == 200
        data = res.json()
        for item in data["items"]:
            assert item["item_type"] == "TBD"

    def test_ingest_endpoint(self, client):
        """POST /tbd-dashboard/ingest scans documents for TBDs."""
        # This requires output/*.yaml files to exist
        res = client.post("/tbd-dashboard/ingest")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert data["status"] == "ingested"
        assert "new_items" in data
        assert "total_files" in data

    def test_stats_consistency(self, client):
        """Stats counts are consistent with items list."""
        res = client.get("/tbd-dashboard")
        data = res.json()
        stats = data["stats"]
        items = data["items"]

        # Total should match or stats reflect full dataset including filtered-out
        assert stats["total_items"] >= len(items)
        # Type counts should sum correctly
        tbd_in_list = sum(1 for i in items if i["item_type"] == "TBD")
        tbr_in_list = sum(1 for i in items if i["item_type"] == "TBR")
        assert stats["tbd_count"] >= tbd_in_list
        assert stats["tbr_count"] >= tbr_in_list


class TestTBDItemUpdate:
    """Updating TBD item status."""

    def test_update_status_success(self, client):
        """PUT /tbd-dashboard/item/{id} updates status."""
        # First get an item ID
        res = client.get("/tbd-dashboard")
        data = res.json()
        if not data["items"]:
            pytest.skip("No TBD items to update")

        item_id = data["items"][0]["item_id"]
        res = client.put(f"/tbd-dashboard/item/{item_id}?status=assigned")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "updated"

    def test_update_nonexistent_item(self, client):
        """Updating a non-existent item returns 404."""
        res = client.put("/tbd-dashboard/item/fake-id-12345?status=resolved")
        assert res.status_code == 404


class TestTBDNavigation:
    """TBD-to-document navigation support.

    Validates that TBD items provide enough information for the frontend
    to navigate to the relevant page and locate the content.
    """

    def test_items_have_page_number(self, client):
        """Each TBD item has a valid page number for navigation."""
        res = client.get("/tbd-dashboard")
        data = res.json()
        for item in data["items"]:
            assert "page_number" in item
            assert isinstance(item["page_number"], int)
            assert item["page_number"] >= 1

    def test_items_have_context_for_highlighting(self, client):
        """Each TBD item has context text for locating it on the page."""
        res = client.get("/tbd-dashboard")
        data = res.json()
        for item in data["items"]:
            assert "context" in item
            assert len(item["context"]) > 0, f"Item {item['item_id']} has empty context"

    def test_item_context_contains_tbd_marker(self, client):
        """Context text contains the actual TBD/TBR marker for matching."""
        res = client.get("/tbd-dashboard")
        data = res.json()
        for item in data["items"]:
            marker = item["item_type"]  # "TBD" or "TBR"
            assert marker.lower() in item["context"].lower(), (
                f"Item {item['item_id']} context doesn't contain '{marker}'"
            )

    def test_items_have_document_title(self, client):
        """Items identify their source document for cross-doc navigation."""
        res = client.get("/tbd-dashboard")
        data = res.json()
        for item in data["items"]:
            assert "document_title" in item
            assert len(item["document_title"]) > 0

    def test_page_elements_contain_tbd_text(self, client):
        """The elements on a TBD's page actually contain the TBD text.

        This validates the full navigation chain: TBD item → page → overlay → highlight.
        """
        # Open the HSI document (has TBDs on pages 5 and 7)
        hsi_path = Path(__file__).parent.parent.parent / "icds" / "digital" / "HSI_SYS_015G.pdf"
        if not hsi_path.exists():
            pytest.skip("HSI PDF not found")

        client.post("/session/start")
        client.post(f"/document/open?pdf_path={hsi_path}")

        # Get TBD items from HSI
        res = client.get("/tbd-dashboard")
        data = res.json()
        hsi_items = [i for i in data["items"] if "HSI" in i["document_title"]]

        if not hsi_items:
            pytest.skip("No HSI TBD items found")

        # For each HSI TBD, verify its page has elements containing the marker text
        for item in hsi_items:
            page_num = item["page_number"]
            res = client.get(f"/document/page/{page_num}/elements")
            assert res.status_code == 200
            elements = res.json()["elements"]

            # At least one element on that page should contain part of the context
            context_words = [
                w for w in item["context"].split()
                if len(w) > 4 and w.upper() not in ("FLOAT", "CONST")
            ][:3]

            page_text = " ".join(e["text"] for e in elements).lower()
            matches = sum(1 for w in context_words if w.lower() in page_text)

            assert matches > 0, (
                f"TBD {item['item_id']} context words not found in page {page_num} elements. "
                f"Context: '{item['context'][:60]}'"
            )

    def test_document_title_resolvable_to_path(self, client):
        """Every TBD item's document_title can be matched to an actual PDF.

        This catches the bug where PDF metadata title (e.g., 'Primitive data
        type definitions and sizes in bytes') doesn't match any filename,
        preventing navigation.
        """
        # Get all TBD items
        res = client.get("/tbd-dashboard")
        data = res.json()
        if not data["items"]:
            pytest.skip("No TBD items")

        # Get all available documents (with titles)
        res = client.get("/documents")
        docs = res.json()["documents"]

        # For each unique document_title in TBD items, verify it matches a PDF
        unique_titles = set(item["document_title"] for item in data["items"])
        for title in unique_titles:
            title_lower = title.lower()
            matched = any(
                title_lower.includes_any(d)
                for d in docs
            ) if False else None  # Use same logic as frontend

            # Replicate the frontend matching logic
            match_found = False
            for d in docs:
                stem_lower = d["stem"].lower()
                filename_lower = d["filename"].lower()
                pdf_title = (d.get("title") or "").lower()
                if pdf_title and title_lower[:15] in pdf_title:
                    match_found = True
                    break
                if pdf_title and pdf_title[:15] in title_lower:
                    match_found = True
                    break
                if stem_lower in title_lower:
                    match_found = True
                    break
                if title_lower[:10] in filename_lower:
                    match_found = True
                    break

            assert match_found, (
                f"TBD document_title '{title}' cannot be matched to any PDF in /documents. "
                f"Available: {[d['filename'] + ' (title: ' + (d.get('title') or '') + ')' for d in docs]}"
            )
