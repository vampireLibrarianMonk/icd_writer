"""Document structure detection — headers, footers, and tables.

Identifies repeating elements (headers/footers) and table structures
within the Document IR for structured editing.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from src.models.document_ir import DocumentIR, TextBlock


@dataclass
class HeaderFooter:
    """A detected repeating header or footer element."""

    text: str
    position: str  # "header" or "footer"
    y_position: float
    pages: list[int] = field(default_factory=list)
    block_ids: list[str] = field(default_factory=list)


@dataclass
class TableStructure:
    """Logical table structure detected on a page."""

    page: int
    columns: list[float]  # x-positions of column starts
    rows: list[float]  # y-positions of row starts
    header_row: list[str] = field(default_factory=list)
    data: list[list[str]] = field(default_factory=list)


def detect_headers_footers(
    document_ir: DocumentIR,
    min_occurrences: int = 3,
    header_y_max: float = 80.0,
    footer_y_min: float = 700.0,
) -> list[HeaderFooter]:
    """Detect repeating text that appears on multiple pages.

    Text appearing at the same y-position on 3+ pages is likely
    a header or footer.
    """
    # Collect text with y-position from each page
    occurrences: dict[tuple[str, str], list[tuple[int, str]]] = {}

    for page in document_ir.pages:
        for block in page.text_blocks:
            text = block.text_verbatim.strip()
            if not text:
                continue

            y = block.bbox.y0
            if y < header_y_max:
                position = "header"
            elif y > footer_y_min:
                position = "footer"
            else:
                continue

            key = (text[:50], position)
            if key not in occurrences:
                occurrences[key] = []
            occurrences[key].append((page.page_number, block.id))

    # Filter to those appearing on enough pages
    results = []
    for (text, position), pages_blocks in occurrences.items():
        if len(pages_blocks) >= min_occurrences:
            results.append(
                HeaderFooter(
                    text=text,
                    position=position,
                    y_position=0.0,  # set below
                    pages=[pb[0] for pb in pages_blocks],
                    block_ids=[pb[1] for pb in pages_blocks],
                )
            )

    return results


def update_header_footer_text(
    document_ir: DocumentIR,
    header_footer: HeaderFooter,
    new_text: str,
) -> int:
    """Update a header/footer across all pages where it appears.

    Returns the number of blocks updated.
    """
    updated = 0
    for page in document_ir.pages:
        for block in page.text_blocks:
            if block.id in header_footer.block_ids:
                block.text_verbatim = block.text_verbatim.replace(
                    header_footer.text, new_text
                )
                updated += 1
    return updated


@dataclass
class ChangeRecord:
    """A single change between two IR versions."""

    page: int
    block_id: str
    change_type: str  # "modified", "added", "removed"
    old_text: str = ""
    new_text: str = ""


def diff_documents(
    original: DocumentIR,
    modified: DocumentIR,
) -> list[ChangeRecord]:
    """Compare two Document IR versions and return the differences.

    Matches blocks by ID and compares text content.
    """
    changes: list[ChangeRecord] = []

    # Build lookup of original blocks
    orig_blocks: dict[str, tuple[int, TextBlock]] = {}
    for page in original.pages:
        for block in page.text_blocks:
            orig_blocks[block.id] = (page.page_number, block)

    # Build lookup of modified blocks
    mod_blocks: dict[str, tuple[int, TextBlock]] = {}
    for page in modified.pages:
        for block in page.text_blocks:
            mod_blocks[block.id] = (page.page_number, block)

    # Find modifications and removals
    for block_id, (page_num, orig_block) in orig_blocks.items():
        if block_id in mod_blocks:
            _, mod_block = mod_blocks[block_id]
            if orig_block.text_verbatim != mod_block.text_verbatim:
                changes.append(
                    ChangeRecord(
                        page=page_num,
                        block_id=block_id,
                        change_type="modified",
                        old_text=orig_block.text_verbatim,
                        new_text=mod_block.text_verbatim,
                    )
                )
        else:
            changes.append(
                ChangeRecord(
                    page=page_num,
                    block_id=block_id,
                    change_type="removed",
                    old_text=orig_block.text_verbatim,
                )
            )

    # Find additions
    for block_id, (page_num, mod_block) in mod_blocks.items():
        if block_id not in orig_blocks:
            changes.append(
                ChangeRecord(
                    page=page_num,
                    block_id=block_id,
                    change_type="added",
                    new_text=mod_block.text_verbatim,
                )
            )

    return changes


def diff_report(changes: list[ChangeRecord]) -> str:
    """Generate a markdown report of changes between two IR versions."""
    if not changes:
        return "# Change Report\n\nNo changes detected."

    modified = [c for c in changes if c.change_type == "modified"]
    added = [c for c in changes if c.change_type == "added"]
    removed = [c for c in changes if c.change_type == "removed"]

    lines = []
    lines.append(f"# Change Report ({len(changes)} changes)")
    lines.append("")
    lines.append("| Type | Count |")
    lines.append("|------|-------|")
    lines.append(f"| Modified | {len(modified)} |")
    lines.append(f"| Added | {len(added)} |")
    lines.append(f"| Removed | {len(removed)} |")
    lines.append("")

    if modified:
        lines.append("## Modified Blocks")
        lines.append("")
        for c in modified:
            old_short = c.old_text[:50].replace("\n", " ")
            new_short = c.new_text[:50].replace("\n", " ")
            lines.append(f"**Page {c.page}** ({c.block_id})")
            lines.append(f"- Old: `{old_short}`")
            lines.append(f"- New: `{new_short}`")
            lines.append("")

    if removed:
        lines.append("## Removed Blocks")
        lines.append("")
        for c in removed:
            lines.append(f"- Page {c.page}: `{c.old_text[:50]}`")
        lines.append("")

    if added:
        lines.append("## Added Blocks")
        lines.append("")
        for c in added:
            lines.append(f"- Page {c.page}: `{c.new_text[:50]}`")

    return "\n".join(lines)
