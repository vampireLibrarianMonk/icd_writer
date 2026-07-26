"""Pipeline orchestrator.

Ties together ingestion, classification, and extraction into
a single workflow that produces a DocumentIR from a PDF file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.classification.classifier import classify_pages
from src.extraction.text_extractor import extract_text_blocks
from src.ingestion.pdf_reader import ingest_pdf
from src.models.common import Provenance
from src.models.document_ir import DocumentIR, PageInfo


def process_pdf(pdf_path: Path | str) -> DocumentIR:
    """Run the full extraction pipeline on a PDF file.

    Steps:
    1. Ingest PDF (hash, metadata, page dimensions)
    2. Classify each page
    3. Extract text blocks from each page
    4. Assemble into DocumentIR

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        A fully populated DocumentIR.
    """
    pdf_path = Path(pdf_path)

    # Step 1: Ingest
    ingestion = ingest_pdf(pdf_path)

    # Step 2: Classify pages
    classifications = classify_pages(pdf_path)

    # Step 3: Extract text blocks
    all_text_blocks = extract_text_blocks(pdf_path)

    # Step 4: Assemble pages
    pages: list[PageInfo] = []
    for i, (width, height) in enumerate(ingestion.page_dimensions):
        page_number = i + 1

        # Find classification for this page
        classification = next(
            (c for c in classifications if c.page_number == page_number),
            None,
        )
        if classification is None:
            from src.models.document_ir import PageClassification, PageClassificationType

            classification = PageClassification(
                page_number=page_number,
                classifications=[PageClassificationType.NATIVE_DIGITAL_TEXT],
            )

        # Collect text blocks for this page
        page_text_blocks = [b for b in all_text_blocks if b.page == page_number]

        pages.append(
            PageInfo(
                page_number=page_number,
                width_pt=width,
                height_pt=height,
                classification=classification,
                text_blocks=page_text_blocks,
            )
        )

    # Build provenance
    provenance = Provenance(
        source_document=ingestion.metadata.filename,
        source_sha256=ingestion.metadata.sha256,
        page=0,  # document-level
        extraction_engine="pymupdf",
        extraction_engine_version="1.25.5",
        extraction_confidence=0.0,  # will be computed as aggregate
        extraction_timestamp=datetime.now(timezone.utc),
    )

    document_ir = DocumentIR(
        metadata=ingestion.metadata,
        pages=pages,
        provenance=provenance,
    )

    return document_ir
