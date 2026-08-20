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

        # Collect lines with their text and style info
        line_data: list[dict] = []  # [{text, size, bold, bbox}, ...]
        for line in block.get("lines", []):
            line_text_parts: list[str] = []
            max_size = 0.0
            line_bold = False
            line_bbox = line.get("bbox", [0, 0, 0, 0])
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                if span_text:
                    line_text_parts.append(span_text)
                    max_size = max(max_size, span.get("size", 0))
                    flags = span.get("flags", 0)
                    font = span.get("font", "")
                    if (flags & (1 << 4)) or "bold" in font.lower():
                        line_bold = True
            line_text = "".join(line_text_parts)
            if line_text.strip():
                line_data.append({
                    "text": line_text,
                    "size": max_size,
                    "bold": line_bold,
                    "bbox": line_bbox,
                })

        if not line_data:
            continue

        # Split block into sub-blocks based on font-size changes and heading patterns
        sub_block_groups = _split_block_by_style(line_data)

        dominant_style = _get_dominant_style(block)

        for group in sub_block_groups:
            sub_text = "\n".join(ld["text"] for ld in group).strip()
            if not sub_text:
                continue

            # Compute style for this sub-block (use first line's properties)
            first_line = group[0]
            sub_style = TextStyle(
                font_name=dominant_style.font_name,
                font_size_pt=first_line["size"] if first_line["size"] else dominant_style.font_size_pt,
                bold=first_line["bold"] or dominant_style.bold,
                italic=dominant_style.italic,
            )

            # Compute bbox for this sub-block
            sub_y0 = min(ld["bbox"][1] for ld in group)
            sub_y1 = max(ld["bbox"][3] for ld in group)
            sub_bbox = BoundingBox(
                x0=block_bbox.x0,
                y0=sub_y0,
                x1=block_bbox.x1,
                y1=sub_y1,
            )

            block_type = _classify_block_type(sub_text, sub_style, sub_bbox, page)
            block_id = f"block-p{page_number:02d}-b{block_idx:02d}"

            blocks.append(
                TextBlock(
                    id=block_id,
                    block_type=block_type,
                    page=page_number,
                    bbox=sub_bbox,
                    text_verbatim=sub_text,
                    reading_order=block_idx,
                    style=sub_style,
                    confidence=1.0,
                    is_ocr=False,
                )
            )
            block_idx += 1

    return blocks


def _split_on_embedded_headings(text: str) -> list[str]:
    """Split a text block if it contains section heading patterns mid-text.

    For example, a block containing:
        "TBD.\n3.17 Trial Accepted Message"
    gets split into:
        ["TBD.", "3.17 Trial Accepted Message"]
    """
    import re

    lines = text.split("\n")
    if len(lines) <= 1:
        return [text]

    # Section heading pattern: starts with number like "3.17 " or "A.1 "
    heading_pattern = re.compile(r"^[A-Z0-9]+(\.[0-9]+)+\.?\s+\S")

    result_blocks: list[str] = []
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # If this line looks like a heading AND we already have content above it, split
        if stripped and heading_pattern.match(stripped) and current_lines:
            # Flush the content before this heading
            block_text = "\n".join(current_lines).strip()
            if block_text:
                result_blocks.append(block_text)
            current_lines = [line]
        else:
            current_lines.append(line)

    # Flush remaining
    if current_lines:
        block_text = "\n".join(current_lines).strip()
        if block_text:
            result_blocks.append(block_text)

    return result_blocks if result_blocks else [text]


def _split_block_by_style(line_data: list[dict]) -> list[list[dict]]:
    """Split a block's lines into sub-blocks based on style transitions.

    Splits when:
    1. A line has a significantly larger font than the next line (heading → body)
    2. A line matches a section heading pattern AND the previous lines are body text
    3. A line with a section heading pattern starts after non-heading content

    Does NOT split TOC entries (lines with leader dots stay together).

    Args:
        line_data: list of {text, size, bold, bbox} dicts, one per line.

    Returns:
        List of groups, where each group is a list of line_data dicts.
    """
    import re

    if len(line_data) <= 1:
        return [line_data]

    heading_pattern = re.compile(r"^[A-Z0-9]+(\.[0-9]+)+\.?\s+\S")

    # Detect if this is a TOC block (most lines have leader dots)
    dot_lines = sum(1 for ld in line_data if "..." in ld["text"] or ld["text"].count(".") > 5)
    is_toc_block = dot_lines >= len(line_data) * 0.5 and len(line_data) >= 3

    if is_toc_block:
        # TOC blocks stay together — don't split
        return [line_data]

    groups: list[list[dict]] = []
    current_group: list[dict] = []

    for i, ld in enumerate(line_data):
        text = ld["text"].strip()
        size = ld["size"]
        bold = ld["bold"]

        if not current_group:
            current_group.append(ld)
            continue

        # Determine if this line starts a new logical block
        should_split = False

        prev = current_group[-1]
        prev_size = prev["size"]

        # Rule 1: This line is a section-numbered heading and there's already content
        if heading_pattern.match(text) and len(current_group) >= 1:
            # Only split if previous content wasn't also a heading pattern
            prev_text = prev["text"].strip()
            prev_is_heading = bool(heading_pattern.match(prev_text))
            if not prev_is_heading:
                should_split = True

        # Rule 2: Font size jump (this line is notably larger than previous)
        if size > 0 and prev_size > 0:
            if size >= prev_size + 2 and len(text) < 150:
                should_split = True
            # Rule 3: Font size drop (previous was large heading, this is body)
            if prev_size >= size + 2 and len(current_group) <= 3:
                # The current_group is a heading, start new group for body
                # But only if the heading group is short (1-3 lines)
                pass  # Don't split here — let the heading be its own block
                # Actually: if prev was large and this is small, the heading ended.
                # Split BEFORE this line.
                if len(current_group) <= 3 and prev_size >= 13:
                    should_split = True

        # Rule 4: Bold line after non-bold content (new sub-heading)
        if bold and not prev["bold"] and len(text) < 150 and len(current_group) >= 2:
            should_split = True

        if should_split:
            groups.append(current_group)
            current_group = [ld]
        else:
            current_group.append(ld)

    # Flush
    if current_group:
        groups.append(current_group)

    return groups


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
    """Classify a text block as heading, paragraph, caption, etc.

    Rules (in priority order):
    1. Header/footer by position
    2. TOC entry (has leader dots) → list_item
    3. Caption (short, starts with Figure/Table)
    4. Heading: large font + short, or bold + short, or numbered section
    5. Paragraph (default)
    """
    import re

    page_height = page.rect.height
    line_count = text.count("\n") + 1
    text_length = len(text)
    first_line = text.split("\n")[0].strip()
    block_height = bbox.y1 - bbox.y0

    # Headers/footers at top/bottom edges
    if bbox.y0 < page_height * 0.08:
        return "header"
    if bbox.y1 > page_height * 0.92 and line_count == 1:
        return "footer"

    # TOC entries: contain leader dots (3+ consecutive dots forming a dot leader)
    if "..." in first_line:
        # Must have actual leader dots (not just abbreviation ellipsis)
        # Leader dots: 4+ dots in sequence, typically connecting title to page number
        if re.search(r"\.{4,}", first_line):
            return "list_item"

    # Captions: short text starting with Figure/Table
    if text_length < 100 and (
        text.lower().startswith("figure") or text.lower().startswith("table")
    ):
        return "caption"

    # Heading detection — must be SHORT (height guard)
    # A heading block should not be taller than ~80px (3-4 lines max)
    if block_height > 80:
        # Too tall to be a heading — it's merged content
        return "paragraph"

    # Large font + short text = heading
    if style.font_size_pt and style.font_size_pt >= 14 and line_count <= 3:
        return "heading"

    # Bold + short text = heading
    if style.bold and line_count <= 2 and text_length < 200:
        return "heading"

    # Numbered section heading (e.g., "3.2.1 Title")
    if _is_numbered_heading(text) and line_count <= 3:
        return "heading"

    return "paragraph"


def _is_numbered_heading(text: str) -> bool:
    """Check if text starts with a section number pattern like '3.2.1'."""
    import re

    # Match patterns like "1.", "1.2", "1.2.3", "A.1", etc.
    pattern = r"^[A-Z0-9]+(\.[0-9]+)*\.?\s+\S"
    first_line = text.split("\n")[0]
    return bool(re.match(pattern, first_line)) and len(first_line) < 200
