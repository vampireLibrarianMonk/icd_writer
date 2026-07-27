"""Rogue text detector.

Identifies text blocks that are visually obscured by overlapping elements
(images, filled shapes) in the PDF. These are text spans that exist in the
PDF data but aren't meant to be visible — they were drawn first, then
covered by a later element.

Common cases:
- White text on a light background (meant for dark bg that covers it)
- Text behind full-coverage images
- Template/placeholder text hidden by filled shapes

The user can choose to: keep, hide, or delete these blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz
import numpy as np
from PIL import Image as PILImage

from src.models.common import BoundingBox
from src.models.document_ir import DocumentIR


@dataclass
class RogueText:
    """A text block detected as visually hidden/rogue."""

    page: int
    block_id: str
    text: str
    bbox: BoundingBox
    reason: str  # "white_on_light", "covered_by_image", "low_contrast"
    confidence: float = 0.0  # how confident we are it's rogue


def detect_rogue_text(
    document_ir: DocumentIR,
    source_pdf: Path | str,
) -> list[RogueText]:
    """Detect text blocks that are visually hidden in the rendered PDF.

    Strategy: White text is rogue if there's no overlapping image or
    filled drawing at its position (nothing dark behind it to make it visible).
    """
    source_pdf = Path(source_pdf)
    doc = fitz.open(str(source_pdf))
    rogues: list[RogueText] = []

    for page_info in document_ir.pages:
        page_idx = page_info.page_number - 1
        if page_idx >= len(doc):
            continue

        page = doc[page_idx]
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        # Get all image rects on this page
        image_rects = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                for r in page.get_image_rects(xref):
                    image_rects.append((r.x0, r.y0, r.x1, r.y1))
            except Exception:
                pass

        # Get all filled drawings on this page
        fill_rects = []
        for d in page.get_drawings():
            fill = d.get("fill")
            if fill:  # has a fill color
                rect = d.get("rect")
                if rect:
                    # Only count dark fills (not light gray/white fills)
                    fill_bright = sum(fill) / len(fill) * 255
                    if fill_bright < 200:
                        fill_rects.append((rect.x0, rect.y0, rect.x1, rect.y1))

        # Check each white text span
        for raw_block in raw.get("blocks", []):
            if raw_block.get("type") != 0:
                continue
            for line in raw_block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars).strip()
                    if not text or len(text) < 2:
                        continue

                    color_int = span.get("color", 0)
                    text_r = (color_int >> 16) & 0xFF
                    text_g = (color_int >> 8) & 0xFF
                    text_b = color_int & 0xFF
                    text_bright = (text_r + text_g + text_b) / 3

                    if text_bright < 200:
                        continue  # Not white text, skip

                    bbox = span["bbox"]
                    text_cx = (bbox[0] + bbox[2]) / 2
                    text_cy = (bbox[1] + bbox[3]) / 2

                    # Check if any image overlaps this text position
                    has_dark_bg = False
                    for ix0, iy0, ix1, iy1 in image_rects:
                        if ix0 <= text_cx <= ix1 and iy0 <= text_cy <= iy1:
                            has_dark_bg = True
                            break

                    # Check if any filled drawing overlaps
                    if not has_dark_bg:
                        for fx0, fy0, fx1, fy1 in fill_rects:
                            if fx0 <= text_cx <= fx1 and fy0 <= text_cy <= fy1:
                                has_dark_bg = True
                                break

                    if not has_dark_bg:
                        # White text with nothing dark behind it = rogue
                        for block in page_info.text_blocks:
                            if (abs(block.bbox.x0 - bbox[0]) < 20 and
                                    abs(block.bbox.y0 - bbox[1]) < 20):
                                if not any(
                                    rg.block_id == block.id and rg.text == text
                                    for rg in rogues
                                ):
                                    rogues.append(
                                        RogueText(
                                            page=page_info.page_number,
                                            block_id=block.id,
                                            text=text[:80],
                                            bbox=BoundingBox(
                                                x0=bbox[0], y0=bbox[1],
                                                x1=bbox[2], y1=bbox[3],
                                            ),
                                            reason="white_no_background",
                                            confidence=0.95,
                                        )
                                    )
                                break
                            # Fallback: text content match
                        else:
                            for block in page_info.text_blocks:
                                if text in block.text_verbatim:
                                    if not any(
                                        rg.block_id == block.id and rg.text == text
                                        for rg in rogues
                                    ):
                                        rogues.append(
                                            RogueText(
                                                page=page_info.page_number,
                                                block_id=block.id,
                                                text=text[:80],
                                                bbox=BoundingBox(
                                                    x0=bbox[0], y0=bbox[1],
                                                    x1=bbox[2], y1=bbox[3],
                                                ),
                                                reason="white_no_background",
                                                confidence=0.95,
                                            )
                                        )
                                    break

    doc.close()
    return rogues


def _analyze_region(region: np.ndarray, block) -> str | None:
    """Analyze a rendered region to determine if text is visually hidden.

    Returns a reason string if rogue, or None if text appears visible.
    """
    # Check 1: Is the region nearly uniform? (text covered by solid fill)
    pixel_range = region.max() - region.min()
    if pixel_range < 15:
        # Region is almost flat — text is not visible
        mean_val = region.mean()
        if mean_val > 200:
            return "white_on_light"
        elif mean_val < 50:
            return "covered_by_dark"
        else:
            return "covered_by_fill"

    # Check 2: Very low contrast (text color matches background)
    # Look at the standard deviation — visible text creates high variance
    std = region.std()
    if std < 8:
        return "low_contrast"

    # Text appears visible
    return None


def remove_rogue_text(
    document_ir: DocumentIR, rogues: list[RogueText]
) -> int:
    """Remove rogue text blocks from the Document IR.

    Returns the number of blocks removed.
    """
    rogue_ids = {r.block_id for r in rogues}
    removed = 0

    for page in document_ir.pages:
        original_count = len(page.text_blocks)
        page.text_blocks = [
            b for b in page.text_blocks if b.id not in rogue_ids
        ]
        removed += original_count - len(page.text_blocks)

    return removed


def rogue_text_report(rogues: list[RogueText]) -> str:
    """Generate a markdown report of detected rogue text."""
    lines = []
    lines.append(f"# Rogue Text Detection ({len(rogues)} found)")
    lines.append("")
    lines.append(
        "These text blocks exist in the PDF data but are visually hidden "
        "(covered by images, same color as background, etc.)."
    )
    lines.append("")
    lines.append("| Page | Reason | Text |")
    lines.append("|------|--------|------|")
    for r in rogues:
        text_short = r.text[:50].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r.page} | {r.reason} | {text_short} |")

    lines.append("")
    lines.append("## Actions")
    lines.append("")
    lines.append("- **Keep**: Leave in the IR (will render if background changes)")
    lines.append("- **Hide**: Mark as hidden (kept in IR but excluded from export)")
    lines.append("- **Delete**: Remove from IR permanently")

    return "\n".join(lines)
