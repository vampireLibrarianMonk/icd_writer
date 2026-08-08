"""Maturity scoring for ICD documents and sections.

Computes a maturity score based on the ratio of resolved content
to open items (TBDs/TBRs). A fully mature section has no open items.

All local processing — zero AWS cost.
"""

from __future__ import annotations

import logging
import re

from src.briefing.models import MaturityScore
from src.models.document_ir import DocumentIR
from src.tbd_tracker import TbxItem

logger = logging.getLogger(__name__)

# Heading pattern to identify section boundaries
HEADING_PATTERN = re.compile(
    r'^(\d+(?:\.\d+)*)\s+(.+)$|^([A-Z][A-Z\s]{5,})$'
)


def score_document(ir: DocumentIR, tbds: list[TbxItem]) -> list[MaturityScore]:
    """Compute maturity scores for each section and overall document.

    Args:
        ir: Document IR with text blocks.
        tbds: TBD/TBR items detected in this document.

    Returns:
        List of MaturityScore objects (one per section + one "overall").
    """
    sections = _extract_sections_with_blocks(ir)
    scores: list[MaturityScore] = []

    total_blocks = 0
    total_tbds = 0

    for section_heading, block_count, page_num in sections:
        # Count TBDs in this section (by page proximity)
        section_tbds = _count_tbds_in_section(
            tbds, section_heading, page_num, ir
        )
        total_blocks += block_count
        total_tbds += section_tbds

        # Score: 1.0 means no TBDs relative to content
        if block_count == 0:
            score = 1.0
        else:
            # Each TBD penalizes the score proportionally
            # A section with 1 TBD in 20 blocks = 0.95
            # A section with 5 TBDs in 10 blocks = 0.50
            score = max(0.0, 1.0 - (section_tbds / max(block_count, 1)))

        rating = MaturityScore.compute_rating(score)
        scores.append(MaturityScore(
            section=section_heading,
            total_blocks=block_count,
            tbd_count=section_tbds,
            score=round(score, 3),
            rating=rating,
        ))

    # Overall score
    if total_blocks > 0:
        overall_score = max(0.0, 1.0 - (total_tbds / max(total_blocks, 1)))
    else:
        overall_score = 1.0

    scores.append(MaturityScore(
        section="overall",
        total_blocks=total_blocks,
        tbd_count=total_tbds,
        score=round(overall_score, 3),
        rating=MaturityScore.compute_rating(overall_score),
    ))

    return scores


def _extract_sections_with_blocks(
    ir: DocumentIR,
) -> list[tuple[str, int, int]]:
    """Extract section headings with their block counts.

    Returns list of (heading, block_count, start_page) tuples.
    """
    sections: list[tuple[str, int, int]] = []
    current_heading = "Preamble"
    current_count = 0
    current_page = 1

    for page in ir.pages:
        for block in page.text_blocks:
            text = block.text_verbatim.strip()
            if not text:
                continue

            # Check if this block is a heading
            is_heading = False
            if block.style and block.style.font_size_pt and block.style.font_size_pt > 12:
                if len(text) < 100:
                    is_heading = True
            elif HEADING_PATTERN.match(text) and len(text) < 80:
                is_heading = True

            if is_heading:
                # Save previous section
                if current_count > 0:
                    sections.append((current_heading, current_count, current_page))
                current_heading = text
                current_count = 0
                current_page = page.page_number
            else:
                current_count += 1

    # Flush last section
    if current_count > 0:
        sections.append((current_heading, current_count, current_page))

    return sections


def _count_tbds_in_section(
    tbds: list[TbxItem],
    section_heading: str,
    section_start_page: int,
    ir: DocumentIR,
) -> int:
    """Count TBDs that belong to a given section.

    Uses page proximity and context matching to assign TBDs to sections.
    """
    count = 0
    heading_lower = section_heading.lower()

    for tbd in tbds:
        # Simple heuristic: TBD is on or after the section start page
        # and before the next section. We approximate by checking if
        # the TBD's context relates to the section.
        if tbd.page >= section_start_page:
            # Check if this TBD's context mentions the section keyword
            if _contexts_overlap(heading_lower, tbd.context.lower()):
                count += 1
            elif tbd.page == section_start_page:
                count += 1

    return count


def _contexts_overlap(heading: str, context: str) -> bool:
    """Check if a section heading and TBD context share meaningful keywords."""
    # Extract significant words (3+ chars, not common words)
    stop_words = {"the", "and", "for", "are", "but", "not", "you",
                  "all", "can", "had", "her", "was", "one", "our",
                  "this", "that", "with", "from", "have", "been"}
    heading_words = set(
        w for w in re.findall(r'\b\w{3,}\b', heading)
        if w not in stop_words
    )
    context_words = set(
        w for w in re.findall(r'\b\w{3,}\b', context)
        if w not in stop_words
    )

    # If they share at least one significant word, they're related
    return bool(heading_words & context_words)
