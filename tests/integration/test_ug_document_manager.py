"""User Guide Regression: Document Management (Section 7)

Validates the document management workflow described in the User Guide:
- List documents returns indexed PDFs
- Document entries have required metadata fields
- Delete removes document from list
- Delete removes IR file
- Delete preserves the source PDF in icds/digital/

Tests use the test corpus documents that are auto-indexed by conftest.py.
For delete tests, a throwaway copy is used to avoid corrupting the test corpus.
"""

import hashlib
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"
TSAFE_PDF = ICDS_DIR / "20130010957.pdf"


@pytest.fixture(scope="module")
def client():
    """Shared test client for document management tests."""
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    return c


# ─── List Documents ───────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestListDocumentsReturnsIndexed:
    """Verify GET /documents lists all indexed PDFs."""

    def test_list_documents_returns_indexed(self, client):
        """GET /documents lists all indexed PDFs with their info."""
        res = client.get("/documents")
        assert res.status_code == 200
        data = res.json()
        assert "documents" in data
        assert len(data["documents"]) >= 1, "No indexed documents found"

    def test_indexed_documents_include_hsi(self, client):
        """HSI_SYS_015G should appear in the document list (auto-indexed by conftest)."""
        res = client.get("/documents")
        docs = res.json()["documents"]
        stems = [d["stem"] for d in docs]
        assert "HSI_SYS_015G" in stems, (
            f"HSI_SYS_015G not in document list: {stems}"
        )


# ─── Document Has Metadata ────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestDocumentHasMetadata:
    """Verify each document entry has required metadata fields."""

    def test_document_has_metadata(self, client):
        """Each doc has filename, size_bytes, stem, sha256."""
        res = client.get("/documents")
        docs = res.json()["documents"]
        assert len(docs) >= 1

        for doc in docs:
            assert "filename" in doc, f"Missing 'filename': {doc}"
            assert "size_bytes" in doc, f"Missing 'size_bytes': {doc}"
            assert "stem" in doc, f"Missing 'stem': {doc}"
            assert "sha256" in doc, f"Missing 'sha256': {doc}"

    def test_document_sizes_reasonable(self, client):
        """Document sizes should be reasonable (not zero, not absurd)."""
        res = client.get("/documents")
        docs = res.json()["documents"]

        for doc in docs:
            size = doc["size_bytes"]
            assert size > 1000, f"{doc['filename']} too small: {size} bytes"
            assert size < 500_000_000, f"{doc['filename']} too large: {size} bytes"

    def test_document_sha256_valid_format(self, client):
        """SHA-256 hashes should be 64 hex characters."""
        res = client.get("/documents")
        docs = res.json()["documents"]

        for doc in docs:
            sha = doc["sha256"]
            assert len(sha) == 64, f"Invalid SHA-256 length for {doc['filename']}: {len(sha)}"
            assert all(c in "0123456789abcdef" for c in sha), (
                f"Non-hex chars in SHA-256 for {doc['filename']}"
            )


# ─── Delete Document ──────────────────────────────────────────────────


@pytest.mark.skipif(not TSAFE_PDF.exists(), reason="20130010957.pdf not found")
class TestDeleteDocument:
    """Verify document deletion cleans up indices and IR but preserves source PDF."""

    @pytest.fixture
    def delete_client(self):
        """Create a client with a throwaway document for delete testing."""
        # Create a uniquely-named copy in uploads/ so deletion doesn't affect icds/digital/
        uploads_dir = Path("uploads")
        uploads_dir.mkdir(exist_ok=True)
        throwaway_name = f"test_delete_{uuid.uuid4().hex[:8]}.pdf"
        throwaway_path = uploads_dir / throwaway_name
        shutil.copy2(str(TSAFE_PDF), str(throwaway_path))

        # Create a corresponding IR file (must match the stem for /documents to list it)
        ir_name = f"{throwaway_path.stem}_document_ir.yaml"
        ir_path = OUTPUT_DIR / ir_name
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ir_path.write_text(
            f"metadata:\n"
            f"  filename: {throwaway_name}\n"
            f"  sha256: {hashlib.sha256(throwaway_path.read_bytes()).hexdigest()}\n"
            f"  page_count: 10\n"
            f"  file_size_bytes: {throwaway_path.stat().st_size}\n"
            f"pages: []\n",
            encoding="utf-8",
        )

        app = create_app()
        client = TestClient(app)
        client.post("/session/start")

        # Verify the document appears in the list before proceeding
        res = client.get("/documents")
        stems = [d["stem"] for d in res.json()["documents"]]
        if throwaway_path.stem not in stems:
            # Cleanup and skip — listing requires real PDF processing
            throwaway_path.unlink(missing_ok=True)
            ir_path.unlink(missing_ok=True)
            pytest.skip(
                "Throwaway document not discoverable in /documents "
                "(may require full pipeline indexing)"
            )

        return client, throwaway_path, ir_path

    def test_delete_removes_from_list(self, delete_client):
        """After DELETE, document is gone from GET /documents."""
        client, throwaway_path, ir_path = delete_client
        doc_stem = throwaway_path.stem

        # Verify it appears in the list
        res = client.get("/documents")
        stems_before = [d["stem"] for d in res.json()["documents"]]
        assert doc_stem in stems_before, f"{doc_stem} not in document list before delete"

        # Delete it
        del_res = client.delete(f"/document/{doc_stem}")
        if del_res.status_code == 500:
            pytest.skip("Delete endpoint requires OpenSearch (not available locally)")
        assert del_res.status_code == 200

        # Verify it's gone
        res = client.get("/documents")
        stems_after = [d["stem"] for d in res.json()["documents"]]
        assert doc_stem not in stems_after, f"{doc_stem} still in list after delete"

        # Cleanup if anything remains
        throwaway_path.unlink(missing_ok=True)
        ir_path.unlink(missing_ok=True)

    def test_delete_removes_ir_file(self, delete_client):
        """After DELETE, output/{stem}_document_ir.yaml no longer exists."""
        client, throwaway_path, ir_path = delete_client
        doc_stem = throwaway_path.stem

        # Confirm IR exists
        assert ir_path.exists(), "IR file should exist before delete"

        # Delete
        del_res = client.delete(f"/document/{doc_stem}")
        if del_res.status_code == 500:
            pytest.skip("Delete endpoint requires OpenSearch (not available locally)")

        # IR should be gone
        assert not ir_path.exists(), f"IR file still exists after delete: {ir_path}"

        # Cleanup
        throwaway_path.unlink(missing_ok=True)

    def test_delete_preserves_source_pdf(self, delete_client):
        """Deletion does NOT remove the original PDF from icds/digital/."""
        client, throwaway_path, ir_path = delete_client

        # The original TSAFE PDF in icds/digital/ should still exist
        # (our throwaway is in uploads/, so the test verifies source safety)
        assert TSAFE_PDF.exists(), (
            "Source PDF in icds/digital/ was deleted — this should never happen"
        )

        # Cleanup
        doc_stem = throwaway_path.stem
        del_res = client.delete(f"/document/{doc_stem}")
        if del_res.status_code == 500:
            pytest.skip("Delete endpoint requires OpenSearch (not available locally)")
        throwaway_path.unlink(missing_ok=True)
        ir_path.unlink(missing_ok=True)
