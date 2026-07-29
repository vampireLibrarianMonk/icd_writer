"""E2E Test: Document List Filtering

Tests that GET /documents only returns indexed documents:
- Documents without a _document_ir.yaml in output/ are excluded
- Documents with an IR file are included with correct metadata
- The TBD dashboard document filter works with the document parameter
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
TSAFE_PDF = ICDS_DIR / "20130010957.pdf"


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestDocumentListEndpoint:
    """GET /documents — only indexed documents are returned."""

    def test_returns_documents_list(self, client):
        """Response has a 'documents' key with a list."""
        res = client.get("/documents")
        assert res.status_code == 200
        data = res.json()
        assert "documents" in data
        assert isinstance(data["documents"], list)

    def test_unindexed_pdf_not_in_list(self, client):
        """A PDF without a corresponding IR file does NOT appear."""
        # All PDFs in icds/digital that don't have an IR file should be absent
        res = client.get("/documents")
        data = res.json()
        indexed_stems = {d["stem"] for d in data["documents"]}

        for pdf in ICDS_DIR.glob("*.pdf"):
            ir_path = OUTPUT_DIR / f"{pdf.stem}_document_ir.yaml"
            if not ir_path.exists():
                assert pdf.stem not in indexed_stems, (
                    f"{pdf.stem} appears in /documents but has no IR file"
                )

    @pytest.mark.skipif(not TSAFE_PDF.exists(), reason="Test PDF not available")
    def test_indexed_pdf_appears_in_list(self, client):
        """A PDF with a corresponding IR file appears with correct fields."""
        ir_path = OUTPUT_DIR / "20130010957_document_ir.yaml"
        if not ir_path.exists():
            pytest.skip("20130010957 not indexed yet")

        res = client.get("/documents")
        data = res.json()
        stems = [d["stem"] for d in data["documents"]]
        assert "20130010957" in stems

        # Check required fields on the matching document
        doc = next(d for d in data["documents"] if d["stem"] == "20130010957")
        assert doc["indexed"] is True
        assert doc["filename"] == "20130010957.pdf"
        assert "path" in doc
        assert "sha256" in doc
        assert doc["size_bytes"] > 0

    def test_document_fields_all_present(self, client):
        """Every document in the list has the required field set."""
        res = client.get("/documents")
        data = res.json()
        required_fields = ["path", "filename", "stem", "title", "indexed", "size_bytes", "sha256"]
        for doc in data["documents"]:
            for field in required_fields:
                assert field in doc, f"Missing field '{field}' in document: {doc.get('filename')}"


class TestTBDDashboardDocumentFilter:
    """GET /tbd-dashboard?document=... — filter by document name."""

    def test_no_filter_returns_all(self, client):
        """Without a document filter, all items are returned."""
        res = client.get("/tbd-dashboard")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "stats" in data

    def test_filter_by_existing_document(self, client):
        """Filtering by a known document returns only items from that doc."""
        # First get all items to find a document name
        all_res = client.get("/tbd-dashboard")
        all_items = all_res.json()["items"]
        if not all_items:
            pytest.skip("No TBD items in dashboard")

        target_doc = all_items[0]["document_title"]

        # Now filter
        filtered_res = client.get(f"/tbd-dashboard?document={target_doc}")
        filtered_data = filtered_res.json()

        # All returned items should be from that document
        for item in filtered_data["items"]:
            assert item["document_title"] == target_doc

    def test_filter_by_nonexistent_document(self, client):
        """Filtering by a document that doesn't exist returns empty list."""
        res = client.get("/tbd-dashboard?document=DOES_NOT_EXIST_12345.pdf")
        data = res.json()
        assert data["items"] == []

    def test_filter_combined_with_status(self, client):
        """Document filter works together with status filter."""
        res = client.get("/tbd-dashboard?document=nonexistent&status=open")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []

    def test_filter_combined_with_type(self, client):
        """Document filter works together with item_type filter."""
        # Get all items first
        all_res = client.get("/tbd-dashboard")
        all_items = all_res.json()["items"]
        if not all_items:
            pytest.skip("No TBD items in dashboard")

        target_doc = all_items[0]["document_title"]
        target_type = all_items[0]["item_type"]

        res = client.get(f"/tbd-dashboard?document={target_doc}&item_type={target_type}")
        data = res.json()
        for item in data["items"]:
            assert item["document_title"] == target_doc
            assert item["item_type"] == target_type
