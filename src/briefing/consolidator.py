"""Briefing consolidation orchestrator.

Loads Document IRs for selected documents, runs TBD extraction,
cross-reference detection, maturity scoring, and assembles the
full BriefingDocument. All local processing — zero AWS cost.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.briefing.models import (
    BriefingDocument,
    DocumentSummary,
    TbdItem,
)
from src.models.document_ir import DocumentIR
from src.serialization import from_yaml
from src.tbd_tracker import TbxItem, scan_document
from src.version_diff import _extract_revision, _extract_date

logger = logging.getLogger(__name__)


def load_document_ir(stem: str, output_dir: Path | None = None) -> DocumentIR | None:
    """Load a Document IR from the output directory by document stem.

    Args:
        stem: Document stem (e.g., "IDSS_IDD_RevE")
        output_dir: Directory containing _document_ir.yaml files.

    Returns:
        DocumentIR if found and valid, None otherwise.
    """
    if output_dir is None:
        output_dir = Path("output")

    ir_path = output_dir / f"{stem}_document_ir.yaml"
    if not ir_path.exists():
        logger.warning(f"Document IR not found: {ir_path}")
        return None

    try:
        return from_yaml(DocumentIR, ir_path)
    except Exception as e:
        logger.warning(f"Failed to load Document IR from {ir_path}: {e}")
        return None


def build_document_summary(
    stem: str,
    ir: DocumentIR,
    tbds: list[TbxItem],
    pdf_path: str = "",
) -> DocumentSummary:
    """Build a DocumentSummary from a Document IR and its TBD scan results.

    Args:
        stem: Document stem.
        ir: The Document IR.
        tbds: TBD items found by scan_document.
        pdf_path: Path to the source PDF.

    Returns:
        DocumentSummary with metadata and TBD counts.
    """
    # Extract revision from metadata filename or first page text
    revision = ""
    date = ""
    if ir.pages:
        first_page_text = " ".join(
            b.text_verbatim for b in ir.pages[0].text_blocks[:10]
        )
        revision = _extract_revision(first_page_text)
        date = _extract_date(first_page_text)

    # Determine doc type from metadata
    doc_type = "digital"
    if ir.pages and any(b.is_ocr for p in ir.pages for b in p.text_blocks):
        doc_type = "flattened"

    tbd_count = sum(1 for t in tbds if t.item_type == "TBD")
    tbr_count = sum(1 for t in tbds if t.item_type in ("TBR", "TBC", "TBS"))

    return DocumentSummary(
        stem=stem,
        filename=ir.metadata.filename if ir.metadata else f"{stem}.pdf",
        path=pdf_path or str(Path("icds/digital") / f"{stem}.pdf"),
        revision=revision,
        date=date,
        page_count=len(ir.pages),
        tbd_count=tbd_count,
        tbr_count=tbr_count,
        doc_type=doc_type,
    )


def _convert_tbx_to_tbd_item(tbx: TbxItem, document: str) -> TbdItem:
    """Convert a TbxItem from the tracker to a briefing TbdItem."""
    return TbdItem(
        id=tbx.id,
        item_type=tbx.item_type,
        status=tbx.status,
        page=tbx.page,
        context=tbx.context,
        owner=tbx.owner,
        document=document,
    )


def gather_documents(
    stems: list[str],
    output_dir: Path | None = None,
) -> BriefingDocument:
    """Load multiple documents and assemble a BriefingDocument.

    This is the main entry point for Phase 1 consolidation.
    Loads each document's IR, scans for TBDs, and builds the briefing.

    Args:
        stems: List of document stems to include (e.g., ["IDSS_IDD_RevE", "IDSS_IDD_RevF"])
        output_dir: Directory containing _document_ir.yaml files.

    Returns:
        BriefingDocument with document summaries and aggregated TBDs.
    """
    if output_dir is None:
        output_dir = Path("output")

    briefing = BriefingDocument(
        generated_at=datetime.now(timezone.utc).isoformat(),
        document_count=0,
    )

    for stem in stems:
        ir = load_document_ir(stem, output_dir)
        if ir is None:
            logger.warning(f"Skipping {stem} — Document IR not available")
            continue

        # Scan for TBDs
        tbds = scan_document(ir)

        # Build summary
        summary = build_document_summary(stem, ir, tbds)
        briefing.documents.append(summary)

        # Aggregate TBDs
        for tbx in tbds:
            briefing.all_tbds.append(_convert_tbx_to_tbd_item(tbx, stem))

    briefing.document_count = len(briefing.documents)
    return briefing
