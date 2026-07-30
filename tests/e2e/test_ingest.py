"""E2E Test: Document Ingestion Pipeline

Tests the upload-and-ingest flow:
- POST /document/ingest accepts a PDF and returns an ingest_id
- GET /document/ingest/status/{id} returns progress updates
- Pipeline runs: extract → index → detect TBDs
- Final status contains page count, chunk count, TBD/TBR counts

Requires: OpenSearch running locally (docker compose up opensearch).
"""

import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
TSAFE_PDF = ICDS_DIR / "20130010957.pdf"


def opensearch_available() -> bool:
    """Check if OpenSearch is running."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("localhost", 9200))
        s.close()
        return True
    except Exception:
        return False


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestIngestEndpoint:
    """POST /document/ingest — upload and pipeline trigger."""

    def test_ingest_rejects_non_pdf(self, client):
        """Non-PDF files are rejected with 400."""
        fake_file = io.BytesIO(b"not a pdf")
        res = client.post(
            "/document/ingest",
            files={"file": ("test.txt", fake_file, "text/plain")},
        )
        assert res.status_code == 400

    def test_ingest_rejects_missing_file(self, client):
        """Missing file returns 422."""
        res = client.post("/document/ingest")
        assert res.status_code == 422

    @pytest.mark.skipif(not TSAFE_PDF.exists(), reason="Test PDF not available")
    def test_ingest_returns_ingest_id(self, client):
        """Valid PDF upload returns an ingest_id and started status."""
        with open(TSAFE_PDF, "rb") as f:
            res = client.post(
                "/document/ingest",
                files={"file": ("20130010957.pdf", f, "application/pdf")},
            )
        assert res.status_code == 200
        data = res.json()
        assert "ingest_id" in data
        assert data["status"] == "started"
        assert data["filename"] == "20130010957.pdf"


class TestIngestStatusEndpoint:
    """GET /document/ingest/status/{id} — progress polling."""

    def test_status_404_for_unknown_id(self, client):
        """Unknown ingest_id returns 404."""
        res = client.get("/document/ingest/status/nonexistent")
        assert res.status_code == 404

    @pytest.mark.skipif(not TSAFE_PDF.exists(), reason="Test PDF not available")
    def test_status_returns_valid_structure(self, client):
        """Status response has all required fields."""
        with open(TSAFE_PDF, "rb") as f:
            ingest_res = client.post(
                "/document/ingest",
                files={"file": ("20130010957.pdf", f, "application/pdf")},
            )
        ingest_id = ingest_res.json()["ingest_id"]

        # Give pipeline a moment to start
        time.sleep(1)

        res = client.get(f"/document/ingest/status/{ingest_id}")
        assert res.status_code == 200
        data = res.json()

        required_fields = [
            "ingest_id", "filename", "pdf_path", "status", "step",
            "total_steps", "message", "progress_pct", "pages",
            "text_blocks", "chunks_indexed", "tbd_count", "tbr_count",
            "error", "done",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.skipif(
        not TSAFE_PDF.exists() or not opensearch_available(),
        reason="Test PDF or OpenSearch not available",
    )
    def test_ingest_completes_successfully(self, client):
        """Full pipeline completes with pages > 0 and chunks > 0."""
        # Wait for any prior ingest to finish (avoids index conflict in CI)
        import time as _time
        _time.sleep(3)

        with open(TSAFE_PDF, "rb") as f:
            ingest_res = client.post(
                "/document/ingest",
                files={"file": ("20130010957.pdf", f, "application/pdf")},
            )
        ingest_id = ingest_res.json()["ingest_id"]

        # Poll until done (max 120s)
        for _ in range(60):
            time.sleep(2)
            res = client.get(f"/document/ingest/status/{ingest_id}")
            data = res.json()
            if data["done"]:
                break

        assert data["done"] is True
        assert data["status"] == "done"
        assert data["pages"] == 15
        assert data["text_blocks"] > 0
        assert data["chunks_indexed"] > 0
        assert data["error"] is None

    @pytest.mark.skipif(
        not TSAFE_PDF.exists() or not opensearch_available(),
        reason="Test PDF or OpenSearch not available",
    )
    def test_ingest_progress_increases(self, client):
        """Progress percentage increases over time during ingestion."""
        with open(TSAFE_PDF, "rb") as f:
            ingest_res = client.post(
                "/document/ingest",
                files={"file": ("20130010957.pdf", f, "application/pdf")},
            )
        ingest_id = ingest_res.json()["ingest_id"]

        seen_pcts = set()
        for _ in range(60):
            time.sleep(1)
            res = client.get(f"/document/ingest/status/{ingest_id}")
            data = res.json()
            seen_pcts.add(data["progress_pct"])
            if data["done"]:
                break

        # Should have seen multiple distinct progress values
        assert len(seen_pcts) >= 3, f"Only saw progress values: {seen_pcts}"
        assert 100 in seen_pcts  # Final state
