"""Text reflow engine for edited documents.

Phase 5: When text edits change block size, reflow surrounding content.

Steps implemented:
1. Word-wrap within block (respecting column width)
2. Block push-down (shift subsequent blocks when one grows/shrinks)
3. Overflow detection (flag when content exceeds page bottom)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.models.document_ir import DocumentIR, PageInfo, TextBlock
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
        if _is_header_or_footer(block, page_height):
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
