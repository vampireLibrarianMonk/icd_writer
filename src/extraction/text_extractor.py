"""Text extraction using PyMuPDF.

Extracts text blocks from each page, preserving:
- Bounding boxes
- Reading order
- Font information
- Text content (verbatim)
- Block type classification (heading, paragraph, etc.)
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from src.models.common import BoundingBox
from src.models.document_ir import TextBlock, TextStyle


def extract_text_blocks(pdf_path: Path | str, pages: list[int] | None = None) -> list[TextBlock]:
    """Extract text blocks from a PDF file.

    Args:
        pdf_path: Path to the PDF file.
        pages: Optional list of 1-based page numbers to extract.
            If None, extracts from all pages.

    Returns:
        List of TextBlock objects with position and style information.
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    all_blocks: list[TextBlock] = []

    try:
        page_indices = range(len(doc))
        if pages:
            page_indices = [p - 1 for p in pages if 0 < p <= len(doc)]

        for page_idx in page_indices:
            page = doc[page_idx]
            page_number = page_idx + 1
            page_blocks = _extract_page_blocks(page, page_number)
            all_blocks.extend(page_blocks)
    finally:
        doc.close()

    return all_blocks


def _extract_page_blocks(page: fitz.Page, page_number: int) -> list[TextBlock]:
    """Extract text blocks from a single page using the dict method."""
    blocks: list[TextBlock] = []
    text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    block_idx = 0
    for block in text_dict.get("blocks", []):
        # Skip image blocks
        if block.get("type") != 0:
            continue

        block_bbox = BoundingBox(
            x0=block["bbox"][0],
            y0=block["bbox"][1],
            x1=block["bbox"][2],
            y1=block["bbox"][3],
        )

        # Collect text and determine dominant style from spans
        full_text_parts: list[str] = []
        dominant_style = _get_dominant_style(block)

        for line in block.get("lines", []):
            line_text_parts: list[str] = []
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                if span_text:
                    line_text_parts.append(span_text)
            if line_text_parts:
                full_text_parts.append("".join(line_text_parts))

        full_text = "\n".join(full_text_parts).strip()
        if not full_text:
            continue

        block_type = _classify_block_type(full_text, dominant_style, block_bbox, page)
        block_id = f"block-p{page_number:02d}-b{block_idx:02d}"

        blocks.append(
            TextBlock(
                id=block_id,
                block_type=block_type,
                page=page_number,
                bbox=block_bbox,
                text_verbatim=full_text,
                reading_order=block_idx,
                style=dominant_style,
                confidence=1.0,
                is_ocr=False,
            )
        )
        block_idx += 1

    return blocks


def _get_dominant_style(block: dict) -> TextStyle:
    """Determine the dominant text style from a block's spans."""
    font_sizes: list[float] = []
    font_names: list[str] = []
    is_bold = False
    is_italic = False

    for line in block.get("lines", []):
        for span in line.get("spans", []):
            size = span.get("size", 0)
            font = span.get("font", "")
            flags = span.get("flags", 0)

            if size:
                font_sizes.append(size)
            if font:
                font_names.append(font)

            # PyMuPDF flags: bit 0 = superscript, bit 1 = italic, bit 4 = bold
            if flags & (1 << 4):
                is_bold = True
            if flags & (1 << 1):
                is_italic = True

            # Also check font name for bold/italic indicators
            font_lower = font.lower()
            if "bold" in font_lower:
                is_bold = True
            if "italic" in font_lower or "oblique" in font_lower:
                is_italic = True

    avg_size = sum(font_sizes) / len(font_sizes) if font_sizes else None
    dominant_font = max(set(font_names), key=font_names.count) if font_names else None

    return TextStyle(
        font_name=dominant_font,
        font_size_pt=round(avg_size, 1) if avg_size else None,
        bold=is_bold,
        italic=is_italic,
    )


def _classify_block_type(text: str, style: TextStyle, bbox: BoundingBox, page: fitz.Page) -> str:
    """Classify a text block as heading, paragraph, caption, etc."""
    page_height = page.rect.height

    # Short text in large font near top is likely a heading
    line_count = text.count("\n") + 1
    text_length = len(text)

    if style.font_size_pt and style.font_size_pt >= 14 and line_count <= 3:
        return "heading"

    if style.bold and line_count <= 2 and text_length < 200:
        return "heading"

    # Detect section numbering pattern (e.g., "3.2.1 Title")
    if _is_numbered_heading(text):
        return "heading"

    # Headers/footers at top/bottom edges
    if bbox.y0 < page_height * 0.08:
        return "header"
    if bbox.y1 > page_height * 0.92 and line_count == 1:
        return "footer"

    # Captions are typically short, near figures/tables, possibly italic
    if text_length < 100 and (
        text.lower().startswith("figure") or text.lower().startswith("table")
    ):
        return "caption"

    return "paragraph"


def _is_numbered_heading(text: str) -> bool:
    """Check if text starts with a section number pattern like '3.2.1'."""
    import re

    # Match patterns like "1.", "1.2", "1.2.3", "A.1", etc.
    pattern = r"^[A-Z0-9]+(\.[0-9]+)*\.?\s+\S"
    first_line = text.split("\n")[0]
    return bool(re.match(pattern, first_line)) and len(first_line) < 200
