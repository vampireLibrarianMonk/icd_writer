"""Text reflow engine for edited documents.

Phase 5: When text edits change block size, reflow surrounding content.
Phase 6: Page extension — when overflow is detected, split content to a new page.

Steps implemented:
1. Word-wrap within block (respecting column width)
2. Block push-down (shift subsequent blocks when one grows/shrinks)
3. Overflow detection (flag when content exceeds page bottom)
4. Page split (move overflowing paragraph blocks to a new page)
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from src.models.document_ir import (
    DocumentIR,
    PageClassification,
    PageClassificationType,
    PageInfo,
    TableBlock,
    TextBlock,
)
from src.models.common import BoundingBox

logger = logging.getLogger(__name__)


@dataclass
class ReflowResult:
    """Result of a reflow operation on a page."""

    page_number: int
    blocks_shifted: int
    height_delta_pt: float  # How much the edited block grew (+) or shrunk (-)
    overflow_pt: float  # How much content exceeds page bottom (0 = no overflow)
    overflowing_blocks: list[str] = field(default_factory=list)  # Block IDs that overflow
    page_added: bool = False  # Whether a new page was created due to overflow
    new_page_number: int | None = None  # Page number of newly created page


@dataclass
class FontMetrics:
    """Approximate font metrics for word-wrap calculation."""

    font_size_pt: float
    avg_char_width_pt: float  # Average character width
    line_height_pt: float  # Line spacing

    @classmethod
    def from_block(cls, block: TextBlock) -> "FontMetrics":
        """Estimate font metrics from a text block's properties."""
        font_size = 10.0
        if block.style and block.style.font_size_pt:
            font_size = block.style.font_size_pt
        # Approximate: average char width ≈ 0.5 × font size for proportional fonts
        avg_char_width = font_size * 0.5
        # Line height ≈ 1.2 × font size
        line_height = font_size * 1.2
        return cls(
            font_size_pt=font_size,
            avg_char_width_pt=avg_char_width,
            line_height_pt=line_height,
        )


def compute_wrapped_height(text: str, available_width_pt: float,
                           metrics: FontMetrics) -> tuple[float, int]:
    """Compute the height needed to display wrapped text.

    Args:
        text: The text content to wrap
        available_width_pt: Width of the block in points
        metrics: Font metrics for measurement

    Returns:
        (required_height_pt, line_count)
    """
    if not text.strip():
        return metrics.line_height_pt, 1

    words = text.split()
    lines = 1
    current_line_width = 0.0
    space_width = metrics.avg_char_width_pt

    for word in words:
        word_width = len(word) * metrics.avg_char_width_pt
        needed = word_width + (space_width if current_line_width > 0 else 0)

        if current_line_width + needed > available_width_pt and current_line_width > 0:
            # Wrap to next line
            lines += 1
            current_line_width = word_width
        else:
            current_line_width += needed

    return lines * metrics.line_height_pt, lines


def reflow_page(document_ir: DocumentIR, page_number: int,
                edited_block_id: str,
                page_bottom_margin: float = 72.0) -> ReflowResult:
    """Reflow blocks on a page after an edit.

    Steps:
    1. Find the edited block
    2. Compute its new height (word-wrap within available width)
    3. Calculate height delta
    4. Shift all subsequent blocks by the delta
    5. Detect overflow

    Args:
        document_ir: The document IR (will be modified in place)
        page_number: 1-based page number
        edited_block_id: ID of the block that was edited
        page_bottom_margin: Bottom margin in points (content below this overflows)

    Returns:
        ReflowResult with shift info and overflow detection
    """
    page_idx = page_number - 1
    if page_idx < 0 or page_idx >= len(document_ir.pages):
        return ReflowResult(page_number=page_number, blocks_shifted=0,
                            height_delta_pt=0, overflow_pt=0)

    page = document_ir.pages[page_idx]
    page_height = page.height_pt
    content_bottom = page_height - page_bottom_margin

    # Sort blocks by y-position
    blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)

    # Find the edited block
    edited_idx = -1
    edited_block = None
    for i, block in enumerate(blocks):
        if block.id == edited_block_id:
            edited_idx = i
            edited_block = block
            break

    if edited_block is None:
        return ReflowResult(page_number=page_number, blocks_shifted=0,
                            height_delta_pt=0, overflow_pt=0)

    # Compute new height for edited block
    metrics = FontMetrics.from_block(edited_block)
    available_width = edited_block.bbox.x1 - edited_block.bbox.x0
    original_height = edited_block.bbox.y1 - edited_block.bbox.y0

    new_height, line_count = compute_wrapped_height(
        edited_block.text_verbatim, available_width, metrics
    )
    # Ensure minimum height matches original single-line height
    new_height = max(new_height, metrics.line_height_pt)

    height_delta = new_height - original_height

    # Update the edited block's bounding box
    edited_block.bbox = BoundingBox(
        x0=edited_block.bbox.x0,
        y0=edited_block.bbox.y0,
        x1=edited_block.bbox.x1,
        y1=edited_block.bbox.y0 + new_height,
    )

    # Shift subsequent blocks
    blocks_shifted = 0
    if abs(height_delta) > 0.5:  # Only shift if delta is meaningful (>0.5pt)
        for i in range(edited_idx + 1, len(blocks)):
            block = blocks[i]
            # Skip headers/footers (they stay fixed)
            if _is_header_or_footer(block, page_height):
                continue

            block.bbox = BoundingBox(
                x0=block.bbox.x0,
                y0=block.bbox.y0 + height_delta,
                x1=block.bbox.x1,
                y1=block.bbox.y1 + height_delta,
            )
            blocks_shifted += 1

    # Detect overflow
    overflow_pt = 0.0
    overflowing_blocks: list[str] = []
    for block in blocks:
        # Skip headers (top of page), typed footer/header blocks
        if block.bbox.y0 < 60 or block.block_type in ("header", "footer"):
            continue
        # Skip page footers by content heuristic: contains "Page N" pattern
        # and sits at the very bottom of the page (y0 > page_height - 60)
        if block.bbox.y0 > page_height - 60:
            import re
            if re.search(r'\bPage\s+\d+\b', block.text_verbatim, re.IGNORECASE):
                continue
        if block.bbox.y1 > content_bottom:
            overflow_amount = block.bbox.y1 - content_bottom
            overflow_pt = max(overflow_pt, overflow_amount)
            overflowing_blocks.append(block.id)

    if overflow_pt > 0:
        logger.warning(
            f"Page {page_number}: overflow detected ({overflow_pt:.1f}pt, "
            f"{len(overflowing_blocks)} blocks)"
        )

    return ReflowResult(
        page_number=page_number,
        blocks_shifted=blocks_shifted,
        height_delta_pt=height_delta,
        overflow_pt=overflow_pt,
        overflowing_blocks=overflowing_blocks,
    )


def reflow_page_shrink(document_ir: DocumentIR, page_number: int,
                       edited_block_id: str,
                       page_bottom_margin: float = 72.0) -> ReflowResult:
    """Handle text shrinkage — pull subsequent blocks up.

    Same as reflow_page but specifically for when text gets shorter.
    The implementation is identical (height_delta will be negative).
    """
    return reflow_page(document_ir, page_number, edited_block_id, page_bottom_margin)


def get_page_overflow(document_ir: DocumentIR, page_number: int,
                      page_bottom_margin: float = 72.0) -> float:
    """Check if a page has overflow without modifying anything.

    Returns overflow amount in points (0 = no overflow).
    Uses the original header/footer detection since this checks unmodified layout.
    """
    page_idx = page_number - 1
    if page_idx < 0 or page_idx >= len(document_ir.pages):
        return 0.0

    page = document_ir.pages[page_idx]
    content_bottom = page.height_pt - page_bottom_margin

    for block in page.text_blocks:
        if _is_header_or_footer(block, page.height_pt):
            continue
        if block.bbox.y1 > content_bottom:
            return block.bbox.y1 - content_bottom

    return 0.0


def _is_header_or_footer(block: TextBlock, page_height: float) -> bool:
    """Determine if a block is a header or footer (should not be reflowed)."""
    # Header zone: top 60pt of page
    if block.bbox.y0 < 60:
        return True
    # Footer zone: bottom 72pt of page
    if block.bbox.y0 > page_height - 72:
        return True
    return False


# -----------------------------------------------------------------
# Phase 6: Page extension (split overflowing content to new page)
# -----------------------------------------------------------------

@dataclass
class PageSplitResult:
    """Result of splitting a page due to overflow."""

    split_occurred: bool
    source_page_number: int
    new_page_number: int | None = None  # The inserted page number
    blocks_moved: int = 0  # Number of text blocks moved to the new page
    tables_moved: int = 0  # Number of tables moved to the new page
    moved_block_ids: list[str] = field(default_factory=list)


def split_page_on_overflow(
    document_ir: DocumentIR,
    page_number: int,
    page_top_margin: float = 72.0,
    page_bottom_margin: float = 72.0,
) -> PageSplitResult:
    """Split a page by moving overflowing paragraph blocks to a new page.

    When content overflows the bottom margin of a page, this function:
    1. Identifies which blocks overflow (y1 > page_height - bottom_margin)
    2. Creates a new page with the same dimensions (inserted after current page)
    3. Moves overflowing paragraph blocks to the new page
    4. Repositions moved blocks starting from the top margin
    5. Renumbers all subsequent pages and their blocks

    Only paragraph-type blocks are moved in Phase 1. Headers, footers,
    tables, and figures are left in place (they'll be handled in later phases).

    Args:
        document_ir: The Document IR (modified in place)
        page_number: 1-based page number that has overflow
        page_top_margin: Top margin for content on the new page (pt)
        page_bottom_margin: Bottom margin threshold (pt)

    Returns:
        PageSplitResult with details about the split
    """
    page_idx = page_number - 1
    if page_idx < 0 or page_idx >= len(document_ir.pages):
        return PageSplitResult(split_occurred=False, source_page_number=page_number)

    page = document_ir.pages[page_idx]
    page_height = page.height_pt
    content_bottom = page_height - page_bottom_margin

    # Block types eligible for page-split movement
    MOVABLE_BLOCK_TYPES = {"paragraph", "list_item", "caption"}

    # Find overflowing blocks (not headers/footers, only movable types)
    blocks_to_move: list[TextBlock] = []
    blocks_to_keep: list[TextBlock] = []

    for block in page.text_blocks:
        # Keep headers (top of page) and explicitly typed header/footer blocks
        if block.bbox.y0 < 60 or block.block_type in ("header", "footer"):
            blocks_to_keep.append(block)
        elif block.block_type in MOVABLE_BLOCK_TYPES and block.bbox.y0 >= content_bottom:
            # Check if this is a page footer (contains "Page N" at the very bottom)
            import re
            is_page_footer = (
                block.bbox.y0 > page_height - 60
                and re.search(r'\bPage\s+\d+\b', block.text_verbatim, re.IGNORECASE)
            )
            if is_page_footer:
                blocks_to_keep.append(block)
            else:
                blocks_to_move.append(block)
        elif block.block_type in MOVABLE_BLOCK_TYPES and block.bbox.y1 > content_bottom:
            import re
            is_page_footer = (
                block.bbox.y0 > page_height - 60
                and re.search(r'\bPage\s+\d+\b', block.text_verbatim, re.IGNORECASE)
            )
            if is_page_footer:
                blocks_to_keep.append(block)
            else:
                blocks_to_move.append(block)
        else:
            blocks_to_keep.append(block)

    if not blocks_to_move:
        # Check tables too before giving up
        tables_to_move = []
        tables_to_keep = []
        for table in page.tables:
            if table.bbox.y0 >= content_bottom or table.bbox.y1 > content_bottom:
                tables_to_move.append(table)
            else:
                tables_to_keep.append(table)

        if not tables_to_move:
            return PageSplitResult(split_occurred=False, source_page_number=page_number)

        # Only tables overflow — proceed with split for tables
        blocks_to_keep = list(page.text_blocks)
    else:
        # Also check if any tables overflow
        tables_to_move = []
        tables_to_keep = []
        for table in page.tables:
            if table.bbox.y0 >= content_bottom or table.bbox.y1 > content_bottom:
                tables_to_move.append(table)
            else:
                tables_to_keep.append(table)

    # Create the new page
    new_page_number = page_number + 1
    new_page = PageInfo(
        page_number=new_page_number,
        width_pt=page.width_pt,
        height_pt=page.height_pt,
        classification=PageClassification(
            page_number=new_page_number,
            classifications=[PageClassificationType.NATIVE_DIGITAL_TEXT],
            native_text_available=True,
        ),
        text_blocks=[],
        tables=[],
        figures=[],
    )

    # Reposition moved text blocks on the new page starting at top margin
    current_y = page_top_margin
    block_gap = 6.0  # 6pt gap between blocks

    for block in sorted(blocks_to_move, key=lambda b: b.bbox.y0):
        block_height = block.bbox.y1 - block.bbox.y0
        block_width = block.bbox.x1 - block.bbox.x0

        # Assign new position on the new page
        block.bbox = BoundingBox(
            x0=block.bbox.x0,  # Keep horizontal position
            y0=current_y,
            x1=block.bbox.x0 + block_width,
            y1=current_y + block_height,
        )
        block.page = new_page_number

        # Generate a new ID scoped to the new page
        block.id = f"block-p{new_page_number:02d}-b{len(new_page.text_blocks):02d}"

        new_page.text_blocks.append(block)
        current_y += block_height + block_gap

    # Reposition moved tables on the new page (after text blocks)
    for table in sorted(tables_to_move, key=lambda t: t.bbox.y0):
        table_height = table.bbox.y1 - table.bbox.y0
        table_width = table.bbox.x1 - table.bbox.x0

        table.bbox = BoundingBox(
            x0=table.bbox.x0,
            y0=current_y,
            x1=table.bbox.x0 + table_width,
            y1=current_y + table_height,
        )
        table.page = new_page_number
        new_page.tables.append(table)
        current_y += table_height + block_gap

    # Update the source page — remove moved blocks and tables
    page.text_blocks = blocks_to_keep
    page.tables = tables_to_keep

    # Insert the new page into the document
    document_ir.pages.insert(page_idx + 1, new_page)

    # Renumber all pages after the insertion point
    _renumber_pages(document_ir, start_from=page_idx + 2)

    moved_ids = [b.id for b in new_page.text_blocks]
    logger.info(
        f"Page {page_number}: split — moved {len(new_page.text_blocks)} blocks "
        f"and {len(tables_to_move)} tables to new page {new_page_number}"
    )

    return PageSplitResult(
        split_occurred=True,
        source_page_number=page_number,
        new_page_number=new_page_number,
        blocks_moved=len(new_page.text_blocks),
        tables_moved=len(tables_to_move),
        moved_block_ids=moved_ids,
    )


def reflow_and_split(
    document_ir: DocumentIR,
    page_number: int,
    edited_block_id: str,
    page_bottom_margin: float = 72.0,
    page_top_margin: float = 72.0,
) -> ReflowResult:
    """Reflow a page after an edit, then split if overflow occurs.

    This is the main entry point for the edit pipeline — it combines
    reflow_page() with split_page_on_overflow() into a single operation.

    Args:
        document_ir: The Document IR (modified in place)
        page_number: 1-based page number of the edited block
        edited_block_id: ID of the block that was edited
        page_bottom_margin: Bottom margin in points
        page_top_margin: Top margin for new pages in points

    Returns:
        ReflowResult with overflow and page-added info
    """
    # Step 1: Reflow (shift blocks, detect overflow)
    result = reflow_page(document_ir, page_number, edited_block_id, page_bottom_margin)

    # Step 2: If overflow detected, split the page
    if result.overflow_pt > 0 and result.overflowing_blocks:
        split_result = split_page_on_overflow(
            document_ir, page_number, page_top_margin, page_bottom_margin
        )
        if split_result.split_occurred:
            result.page_added = True
            result.new_page_number = split_result.new_page_number
            # Clear overflow since we resolved it
            result.overflow_pt = 0.0
            result.overflowing_blocks = []
            logger.info(
                f"Page {page_number}: overflow resolved by creating page {split_result.new_page_number} "
                f"({split_result.blocks_moved} blocks moved)"
            )

    return result


def _renumber_pages(document_ir: DocumentIR, start_from: int) -> None:
    """Renumber pages and their blocks from a given index onward.

    Args:
        document_ir: The Document IR to update
        start_from: 0-based index to start renumbering from
    """
    for idx in range(start_from, len(document_ir.pages)):
        page = document_ir.pages[idx]
        new_page_num = idx + 1
        page.page_number = new_page_num
        page.classification.page_number = new_page_num

        # Update block page references and IDs
        for block_idx, block in enumerate(page.text_blocks):
            block.page = new_page_num
            block.id = f"block-p{new_page_num:02d}-b{block_idx:02d}"

        for table in page.tables:
            table.page = new_page_num

        for figure in page.figures:
            figure.page = new_page_num
