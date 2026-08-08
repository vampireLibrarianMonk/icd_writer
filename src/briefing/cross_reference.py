"""Cross-reference detection between ICD documents.

Finds references between documents by searching for document titles,
document numbers, and known identifiers in the "Applicable Documents"
and "Reference Documents" sections, as well as inline mentions.

All local processing — no AWS costs.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.briefing.models import CrossReference
from src.models.document_ir import DocumentIR

logger = logging.getLogger(__name__)

# Patterns for "Applicable Documents" / "Reference Documents" section headings
REFERENCE_SECTION_PATTERNS = [
    re.compile(r"(?:applicable|reference|referenced)\s+documents?", re.IGNORECASE),
    re.compile(r"documents?\s+(?:applicable|referenced)", re.IGNORECASE),
    re.compile(r"^\d+\.?\d*\s+(?:applicable|reference)\s+documents?", re.IGNORECASE),
]

# Common document identifier patterns in ICDs
DOC_ID_PATTERNS = [
    # NASA-style: SSP 50001, SSP-50001, JSC-12345
    re.compile(r"\b(SSP[\s-]?\d+)\b", re.IGNORECASE),
    re.compile(r"\b(JSC[\s-]?\d+)\b", re.IGNORECASE),
    re.compile(r"\b(GSFC[\s-]?\d+)\b", re.IGNORECASE),
    # ICD-style: HSI_SYS_015, IDSS-IDD
    re.compile(r"\b(HSI[\s_-]SYS[\s_-]\d+[A-Z]?)\b", re.IGNORECASE),
    re.compile(r"\b(IDSS[\s_-]IDD)\b", re.IGNORECASE),
    re.compile(r"\b(NDS[\s_-]IDD)\b", re.IGNORECASE),
    # Generic: ICD-nnnn, IDD-nnnn
    re.compile(r"\b(IC[D]\s*[-]?\s*\d+)\b", re.IGNORECASE),
    re.compile(r"\b(ID[D]\s*[-]?\s*\d+)\b", re.IGNORECASE),
]


def _extract_document_title(ir: DocumentIR) -> str:
    """Extract the document title from the first page of the IR."""
    if not ir.pages:
        return ""
    # Look in the first few blocks of page 1 for the title
    first_page = ir.pages[0]
    title_candidates = []
    for block in first_page.text_blocks[:8]:
        text = block.text_verbatim.strip()
        if len(text) > 5 and len(text) < 200:
            title_candidates.append(text)

    # The longest block among the first few is likely the title
    if title_candidates:
        return max(title_candidates, key=len)
    return ""


def _extract_document_number(ir: DocumentIR) -> str:
    """Extract a document number/identifier from the IR metadata or first page."""
    if ir.metadata and ir.metadata.filename:
        stem = ir.metadata.filename.replace(".pdf", "")
        # Clean up: IDSS_IDD_RevF -> IDSS IDD
        clean = re.sub(r"_Rev[A-Z]$", "", stem, flags=re.IGNORECASE)
        return clean.replace("_", " ")
    return ""


def _get_all_text_for_page(ir: DocumentIR, page_num: int) -> str:
    """Get all text content for a given page number."""
    for page in ir.pages:
        if page.page_number == page_num:
            return "\n".join(b.text_verbatim for b in page.text_blocks)
    return ""


def _find_reference_sections(ir: DocumentIR) -> list[tuple[int, str]]:
    """Find pages/sections that contain document reference lists.

    Returns list of (page_number, section_text) tuples.
    """
    results = []
    for page in ir.pages:
        page_text = "\n".join(b.text_verbatim for b in page.text_blocks)
        for pattern in REFERENCE_SECTION_PATTERNS:
            if pattern.search(page_text):
                results.append((page.page_number, page_text))
                break
    return results


def detect_cross_refs(
    doc_a_ir: DocumentIR,
    doc_b_ir: DocumentIR,
    doc_a_stem: str = "",
    doc_b_stem: str = "",
) -> list[CrossReference]:
    """Detect cross-references between two documents.

    Searches for mentions of document B in document A, and vice versa.
    Checks both dedicated reference sections and inline mentions throughout.

    Args:
        doc_a_ir: Document IR for the first document.
        doc_b_ir: Document IR for the second document.
        doc_a_stem: Stem name for doc A (for labeling).
        doc_b_stem: Stem name for doc B (for labeling).

    Returns:
        List of CrossReference objects found.
    """
    if not doc_a_stem:
        doc_a_stem = (doc_a_ir.metadata.filename or "doc_a").replace(".pdf", "")
    if not doc_b_stem:
        doc_b_stem = (doc_b_ir.metadata.filename or "doc_b").replace(".pdf", "")

    refs: list[CrossReference] = []

    # Get searchable identifiers for each document
    title_a = _extract_document_title(doc_a_ir)
    title_b = _extract_document_title(doc_b_ir)
    number_a = _extract_document_number(doc_a_ir)
    number_b = _extract_document_number(doc_b_ir)

    # Build search terms for each document
    search_terms_a = _build_search_terms(doc_a_stem, title_a, number_a)
    search_terms_b = _build_search_terms(doc_b_stem, title_b, number_b)

    # Search doc A for references to doc B
    refs.extend(_search_for_references(
        doc_a_ir, doc_a_stem, doc_b_stem, search_terms_b
    ))

    # Search doc B for references to doc A
    refs.extend(_search_for_references(
        doc_b_ir, doc_b_stem, doc_a_stem, search_terms_a
    ))

    return refs


def _build_search_terms(stem: str, title: str, number: str) -> list[str]:
    """Build a list of search terms that identify a document."""
    terms = []

    # The document number/stem variations
    if number:
        terms.append(number)
        # Also try with underscores replaced by spaces and hyphens
        terms.append(number.replace("_", " "))
        terms.append(number.replace("_", "-"))

    # Key words from the stem
    stem_words = stem.replace("_", " ").replace("-", " ")
    if len(stem_words) > 3:
        terms.append(stem_words)

    # Title keywords (only use significant words, at least 3 chars)
    if title:
        # Use the full title as a search term
        if len(title) > 10:
            terms.append(title[:80])

    # Deduplicate and filter empty
    seen = set()
    unique_terms = []
    for t in terms:
        t_lower = t.lower().strip()
        if t_lower and t_lower not in seen and len(t_lower) >= 3:
            seen.add(t_lower)
            unique_terms.append(t)

    return unique_terms


def _search_for_references(
    source_ir: DocumentIR,
    source_stem: str,
    target_stem: str,
    target_search_terms: list[str],
) -> list[CrossReference]:
    """Search source_ir for references to the target document."""
    refs: list[CrossReference] = []

    if not target_search_terms:
        return refs

    # First check dedicated reference sections
    ref_sections = _find_reference_sections(source_ir)
    for page_num, section_text in ref_sections:
        for term in target_search_terms:
            if term.lower() in section_text.lower():
                refs.append(CrossReference(
                    source_document=source_stem,
                    target_document=target_stem,
                    reference_text=term,
                    section="Applicable/Reference Documents",
                    page=page_num,
                    ref_type="applicable_document",
                ))
                break  # One ref per section is enough

    # Then check all pages for inline mentions
    ref_pages = {r.page for r in refs}  # Skip pages already found in ref sections
    for page in source_ir.pages:
        if page.page_number in ref_pages:
            continue
        page_text = "\n".join(b.text_verbatim for b in page.text_blocks)
        for term in target_search_terms:
            if term.lower() in page_text.lower():
                refs.append(CrossReference(
                    source_document=source_stem,
                    target_document=target_stem,
                    reference_text=term,
                    section=f"Page {page.page_number}",
                    page=page.page_number,
                    ref_type="inline_mention",
                ))
                break  # One ref per page is enough

    return refs
