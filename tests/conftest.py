"""Shared test configuration and fixtures.

Provides:
- skip markers for tests requiring WeasyPrint (GTK/Pango)
- docker_only marker for tests that must run in Docker
- automatic ICD PDF indexing before tests (ensures _document_ir.yaml files exist)
"""

import logging
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


# ─── Paths ─────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).parent.parent
ICDS_DIGITAL_DIR = ROOT_DIR / "icds" / "digital"
ICDS_FLAT_DIR = ROOT_DIR / "icds" / "flat"
OUTPUT_DIR = ROOT_DIR / "output"


# ─── WeasyPrint detection ──────────────────────────────────────────────


def _weasyprint_available() -> bool:
    """Check if WeasyPrint can be imported (requires GTK/Pango libs)."""
    try:
        from weasyprint import HTML  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


WEASYPRINT_AVAILABLE = _weasyprint_available()

skip_no_weasyprint = pytest.mark.skipif(
    not WEASYPRINT_AVAILABLE,
    reason="WeasyPrint not available (missing GTK/Pango system libraries)",
)

# Alias for clarity: marks a test as docker_only AND skips if WeasyPrint unavailable.
docker_only = pytest.mark.docker_only


# ─── ICD PDF indexing ──────────────────────────────────────────────────


def _ensure_icds_indexed():
    """Ensure all ICD PDFs in icds/digital/ have a _document_ir.yaml in output/.

    This runs once at session start. If a PDF has no corresponding IR file,
    it processes the PDF through the pipeline to generate one.
    Requires git-lfs to have downloaded the actual PDF files.

    Also creates marker files for flat variants so version_diff family
    detection can find digital/flat pairs.
    """
    if not ICDS_DIGITAL_DIR.exists():
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from src.pipeline import process_pdf
    from src.serialization import to_yaml

    # Index all digital PDFs
    for pdf_path in sorted(ICDS_DIGITAL_DIR.glob("*.pdf")):
        ir_path = OUTPUT_DIR / f"{pdf_path.stem}_document_ir.yaml"
        if ir_path.exists():
            continue

        # Check if it's a real PDF (not an LFS pointer)
        if pdf_path.stat().st_size < 200:
            logger.warning(f"Skipping {pdf_path.name} — appears to be an LFS pointer (run `git lfs pull`)")
            continue

        logger.info(f"Indexing {pdf_path.name}...")
        try:
            ir = process_pdf(pdf_path)
            ir_path.write_text(to_yaml(ir), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to index {pdf_path.name}: {e}")

    # Create marker files for flat variants (needed for version_diff family detection).
    # These must be valid DocumentIR YAML to avoid crashing the TBD ingest.
    if ICDS_FLAT_DIR.exists():
        import fitz
        import hashlib
        for pdf_path in sorted(ICDS_FLAT_DIR.glob("*.pdf")):
            ir_path = OUTPUT_DIR / f"{pdf_path.stem}_document_ir.yaml"
            if ir_path.exists():
                continue
            if pdf_path.stat().st_size < 200:
                continue
            # Create a minimal valid DocumentIR YAML
            try:
                doc = fitz.open(str(pdf_path))
                page_count = len(doc)
                sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
                doc.close()
                ir_path.write_text(
                    f"metadata:\n"
                    f"  filename: {pdf_path.name}\n"
                    f"  sha256: {sha}\n"
                    f"  page_count: {page_count}\n"
                    f"  file_size_bytes: {pdf_path.stat().st_size}\n"
                    f"pages: []\n",
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning(f"Failed to create marker for {pdf_path.name}: {e}")


# ─── Pytest hooks ─────────────────────────────────────────────────────


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "docker_only: mark test as requiring Docker environment (WeasyPrint + GTK/Pango)",
    )


def pytest_sessionstart(session):
    """Ensure all ICD PDFs are indexed before any tests run."""
    _ensure_icds_indexed()


def pytest_collection_modifyitems(config, items):
    """Auto-skip docker_only tests when WeasyPrint is not available.

    Also auto-applies docker_only marker to tests that use skip_no_weasyprint
    so they can be discovered via `pytest -m docker_only`.
    """
    skip_docker = pytest.mark.skip(
        reason="Requires Docker environment (WeasyPrint/GTK not available locally)"
    )
    for item in items:
        # If test already has docker_only marker, skip it when no WeasyPrint
        if "docker_only" in item.keywords and not WEASYPRINT_AVAILABLE:
            item.add_marker(skip_docker)

        # Auto-tag tests that skip for WeasyPrint so they're discoverable via -m docker_only
        for marker in item.iter_markers("skipif"):
            if marker.kwargs.get("reason", "") and "WeasyPrint" in marker.kwargs.get("reason", ""):
                item.add_marker(pytest.mark.docker_only)
                break
            # Also check positional reason from the mark args
            if marker.args and len(marker.args) >= 2 and "WeasyPrint" in str(marker.args[1] if len(marker.args) > 1 else ""):
                item.add_marker(pytest.mark.docker_only)
                break
