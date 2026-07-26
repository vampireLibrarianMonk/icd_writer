"""PDF reader and ingestion logic.

Accepts a PDF path, computes SHA-256, extracts metadata, and produces
a PdfIngestionResult containing document metadata and per-page basic info.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

from src.models.common import DocumentMetadata


class PdfIngestionResult:
    """Result of ingesting a single PDF file."""

    def __init__(
        self,
        path: Path,
        metadata: DocumentMetadata,
        page_dimensions: list[tuple[float, float]],
    ) -> None:
        self.path = path
        self.metadata = metadata
        self.page_dimensions = page_dimensions  # list of (width_pt, height_pt)

    @property
    def page_count(self) -> int:
        return self.metadata.page_count


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _parse_pdf_date(date_str: str | None) -> datetime | None:
    """Parse a PDF date string (D:YYYYMMDDHHmmSS format) to datetime."""
    if not date_str:
        return None
    # Strip the D: prefix if present
    if date_str.startswith("D:"):
        date_str = date_str[2:]
    # Try common formats
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d", "%Y"):
        try:
            # Handle timezone suffix by truncating
            clean = date_str[
                : len(
                    fmt.replace("%", "")
                    .replace("Y", "1111")
                    .replace("m", "11")
                    .replace("d", "11")
                    .replace("H", "11")
                    .replace("M", "11")
                    .replace("S", "11")
                )
            ]
            return datetime.strptime(date_str[: len(clean)], fmt)
        except (ValueError, IndexError):
            continue
    return None


def ingest_pdf(path: Path | str) -> PdfIngestionResult:
    """Ingest a PDF file and extract basic metadata.

    Args:
        path: Path to the PDF file.

    Returns:
        PdfIngestionResult with metadata and page dimensions.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a valid PDF.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    sha256 = compute_sha256(path)
    file_size = path.stat().st_size

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {path} — {e}") from e

    try:
        pdf_metadata = doc.metadata or {}
        page_count = len(doc)

        page_dimensions: list[tuple[float, float]] = []
        for page in doc:
            rect = page.rect
            page_dimensions.append((rect.width, rect.height))

        creation_date = _parse_pdf_date(pdf_metadata.get("creationDate"))
        mod_date = _parse_pdf_date(pdf_metadata.get("modDate"))

        metadata = DocumentMetadata(
            filename=path.name,
            sha256=sha256,
            page_count=page_count,
            title=pdf_metadata.get("title") or None,
            author=pdf_metadata.get("author") or None,
            subject=pdf_metadata.get("subject") or None,
            creator=pdf_metadata.get("creator") or None,
            creation_date=creation_date,
            modification_date=mod_date,
            file_size_bytes=file_size,
        )
    finally:
        doc.close()

    return PdfIngestionResult(
        path=path,
        metadata=metadata,
        page_dimensions=page_dimensions,
    )
