"""Requirement extraction from document text.

Detects candidate requirements by looking for normative language
(shall, must, will) and structural patterns (numbered sections,
requirement IDs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models.document_ir import DocumentIR, TextBlock


@dataclass
class ExtractedRequirement:
    """A candidate requirement found in the document."""

    text: str
    page: int
    block_id: str
    normative_term: str  # "shall", "must", "will"
    section: str | None = None  # e.g., "3.2.1"
    requirement_id: str | None = None  # e.g., "REQ-001" if found
    confidence: float = 0.0
    has_tbd: bool = False


# Normative terms that indicate requirements
NORMATIVE_TERMS = ["shall", "must", "will", "should"]

# Pattern for section numbers like "3.2.1"
SECTION_PATTERN = re.compile(r"^(\d+\.[\d.]*\d)")

# Pattern for requirement IDs like "REQ-001", "IF-CMD-001"
REQ_ID_PATTERN = re.compile(r"\b([A-Z]{2,}-[A-Z0-9]+-\d+|REQ-\d+)\b")

# TBD/TBR detection
TBD_PATTERN = re.compile(r"\b(TBD|TBR|TBC|TBS)\b")


def extract_requirements(document_ir: DocumentIR) -> list[ExtractedRequirement]:
    """Extract candidate requirements from the Document IR.

    Scans all text blocks for normative language (shall, must, will)
    and returns them as tagged requirements.
    """
    requirements: list[ExtractedRequirement] = []
    current_section: str | None = None

    for page in document_ir.pages:
        for block in page.text_blocks:
            text = block.text_verbatim

            # Track section numbers
            section_match = SECTION_PATTERN.match(text.strip())
            if section_match:
                current_section = section_match.group(1)

            # Check for normative terms
            text_lower = text.lower()
            for term in NORMATIVE_TERMS:
                if f" {term} " in text_lower or text_lower.startswith(f"{term} "):
                    # Found a candidate requirement
                    req_id_match = REQ_ID_PATTERN.search(text)
                    has_tbd = bool(TBD_PATTERN.search(text))

                    # Confidence based on term strength
                    confidence = 0.95 if term == "shall" else 0.85 if term == "must" else 0.70

                    requirements.append(
                        ExtractedRequirement(
                            text=text.strip(),
                            page=page.page_number,
                            block_id=block.id,
                            normative_term=term,
                            section=current_section,
                            requirement_id=req_id_match.group(1) if req_id_match else None,
                            confidence=confidence,
                            has_tbd=has_tbd,
                        )
                    )
                    break  # Only count once per block

    return requirements


def requirements_summary(requirements: list[ExtractedRequirement]) -> str:
    """Generate a markdown summary of extracted requirements."""
    lines = []
    lines.append(f"# Extracted Requirements ({len(requirements)} found)")
    lines.append("")

    # Summary stats
    shall_count = sum(1 for r in requirements if r.normative_term == "shall")
    must_count = sum(1 for r in requirements if r.normative_term == "must")
    will_count = sum(1 for r in requirements if r.normative_term == "will")
    tbd_count = sum(1 for r in requirements if r.has_tbd)

    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total requirements | {len(requirements)} |")
    lines.append(f"| 'shall' statements | {shall_count} |")
    lines.append(f"| 'must' statements | {must_count} |")
    lines.append(f"| 'will' statements | {will_count} |")
    lines.append(f"| Contains TBD/TBR | {tbd_count} |")
    lines.append("")

    # Per-requirement table
    lines.append("| # | Page | Section | Term | Text (truncated) |")
    lines.append("|---|------|---------|------|------------------|")
    for i, req in enumerate(requirements, 1):
        text_short = req.text[:60].replace("\n", " ").replace("|", "\\|")
        section = req.section or "—"
        lines.append(f"| {i} | {req.page} | {section} | {req.normative_term} | {text_short} |")

    return "\n".join(lines)
