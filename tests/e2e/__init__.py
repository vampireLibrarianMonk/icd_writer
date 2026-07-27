"""End-to-end API tests against real ICD documents.

Tests the full backend workflow as a user would experience it:
1. Session management
2. Document loading (open, upload)
3. Page navigation and rendering
4. Element selection (overlays, analysis, table zones)
5. Text editing (click-to-edit, apply, undo/redo)
6. Export (PDF generation)
7. Search and RAG
8. TBD Dashboard

These tests simulate the frontend's API calls in sequence.
Requires: PDFs in icds/digital/, a running OpenSearch instance for search tests.
"""

from pathlib import Path

import pytest

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
DIGITAL_PDFS = list((ICDS_DIR / "digital").glob("*.pdf")) if (ICDS_DIR / "digital").exists() else []


@pytest.fixture(scope="module")
def app_client():
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture(scope="module")
def loaded_client(app_client):
    """A client with a document already loaded (HSI ICD)."""
    # Start session
    res = app_client.post("/session/start")
    assert res.status_code == 200

    # Open the smallest digital PDF
    hsi_path = ICDS_DIR / "digital" / "HSI_SYS_015G.pdf"
    if not hsi_path.exists():
        pytest.skip("HSI_SYS_015G.pdf not found")

    res = app_client.post(f"/document/open?pdf_path={hsi_path}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["pages"] > 0

    return app_client, data["pages"]
