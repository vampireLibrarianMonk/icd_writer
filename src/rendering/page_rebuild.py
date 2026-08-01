"""Page rebuild: reconstruct a PDF page from rawdict with edits applied.

The cleanest approach to 1:1 PDF editing:
1. Extract every visual element from the source page (text spans, drawings, images)
2. Apply the user's text edits to the relevant spans
3. Write everything back to a blank page at exact positions

This produces a page that is visually identical to the original except
for the edited text, which flows naturally with correct font, color,
and positioning.
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)


def rebuild_page_with_edits(
    source_path: Path | str,
    page_number: int,
    edits: list[dict],
) -> bytes:
    """Rebuild a page from source with text edits applied.

    Args:
        source_path: Path to the original PDF
        page_number: 1-based page number
        edits: List of {"old_text": str, "new_text": str} dicts

    Returns:
        PNG image bytes of the rebuilt page
    """
    doc = fitz.open(str(source_path))
    page = doc[page_number - 1]

    # Rebuild the page content
    new_page_doc, overflow = _rebuild_page(page, edits)

    # Render to PNG
    pix = new_page_doc[0].get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    new_page_doc.close()
    doc.close()
    return img_bytes


def rebuild_page_to_doc(
    source_doc: fitz.Document,
    page_number: int,
    edits: list[dict],
) -> tuple[fitz.Document, list[str]]:
    """Rebuild a page and return as a single-page fitz.Document plus overflow lines.

    Returns:
        (new_doc, overflow_lines) - the rebuilt page doc and any lines that didn't fit.
    """
    page = source_doc[page_number - 1]
    new_doc, overflow = _rebuild_page(page, edits)
    return new_doc, overflow


def _rebuild_page(page: fitz.Page, edits: list[dict]) -> tuple[fitz.Document, list[str]]:
    """Core rebuild: extract source page content, apply edits, write to new page.

    Returns:
        (new_doc, overflow_lines) - rebuilt page and lines that didn't fit.
    """
    page_width = page.rect.width
    page_height = page.rect.height

    # Create new blank page
    new_doc = fitz.open()
    new_page = new_doc.new_page(width=page_width, height=page_height)

    # Step 1: Copy all drawings (vector graphics, table borders, lines)
    _copy_drawings(page, new_page)

    # Step 2: Copy all images
    _copy_images(page, new_page, page.parent)

    # Step 3: Extract text spans, apply edits, write back
    overflow = _rebuild_text(page, new_page, edits)

    return new_doc, overflow


def _copy_drawings(source_page: fitz.Page, target_page: fitz.Page) -> None:
    """Copy all vector drawings from source to target page."""
    drawings = source_page.get_drawings()
    for drawing in drawings:
        # Reconstruct each drawing on the target page
        items = drawing.get("items", [])
        color = drawing.get("color")
        fill = drawing.get("fill")
        width = drawing.get("width", 1.0)
        closePath = drawing.get("closePath", False)

        if not items:
            continue

        shape = target_page.new_shape()

        for item in items:
            if item[0] == "l":  # line
                shape.draw_line(item[1], item[2])
            elif item[0] == "re":  # rectangle
                shape.draw_rect(item[1])
            elif item[0] == "c":  # curve
                shape.draw_bezier(item[1], item[2], item[3], item[4])

        if closePath:
            shape.draw_line(shape.last_point, items[0][1] if items[0][0] == "l" else fitz.Point(0, 0))

        shape.finish(
            color=color,
            fill=fill,
            width=width,
        )
        shape.commit()


def _copy_images(source_page: fitz.Page, target_page: fitz.Page, source_doc: fitz.Document) -> None:
    """Copy all images from source to target page at their exact positions."""
    image_list = source_page.get_images(full=True)
    for img_info in image_list:
        xref = img_info[0]
        try:
            rects = source_page.get_image_rects(xref)
            if not rects:
                continue
            rect = rects[0]
            img_data = source_doc.extract_image(xref)
            if not img_data or not img_data["image"]:
                continue
            target_page.insert_image(rect, stream=img_data["image"])
        except Exception:
            continue


def _rebuild_text(source_page: fitz.Page, target_page: fitz.Page, edits: list[dict]) -> list[str]:
    """Extract all text spans, apply edits, write to target page.

    Returns overflow lines that didn't fit on the page.
    """
    raw = source_page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    # Build a map of old_text → new_text for quick lookup
    edit_map = []
    for edit in edits:
        old = edit["old_text"]
        new = edit["new_text"]
        if old != new:
            edit_map.append((old, new))

    overflow_lines = []

    # Collect all text from all blocks into a flat list of spans with their properties
    page_height = source_page.rect.height
    page_width = source_page.rect.width

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue

        # Collect full block text to check if any edit applies to this block
        block_lines = []
        block_spans = []
        for line in block.get("lines", []):
            line_spans = []
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                text = "".join(c["c"] for c in chars)
                line_spans.append({
                    "text": text,
                    "font": span.get("font", ""),
                    "size": span.get("size", 12),
                    "flags": span.get("flags", 0),
                    "color": span.get("color", 0),
                    "origin": span.get("origin", (0, 0)),
                    "bbox": span["bbox"],
                })
            block_spans.append(line_spans)
            block_lines.append("".join(s["text"] for s in line_spans).rstrip())

        block_text = " ".join(block_lines)

        # Check if any edit applies to this block
        applied_edit = None
        for old_text, new_text in edit_map:
            old_normalized = " ".join(old_text.split())
            block_normalized = " ".join(block_text.split())
            # Match if the block contains the start of the old text (40+ chars)
            # OR if the old text contains the block text
            old_start = old_normalized[:60]
            if (old_start in block_normalized
                    or block_normalized[:60] in old_normalized
                    or old_normalized in block_normalized):
                applied_edit = (old_text, new_text)
                break

        if applied_edit:
            # This block has an edit — rebuild it with the new text
            block_overflow = _write_edited_block(
                target_page, block, block_text, applied_edit,
                page_width, page_height,
            )
            if block_overflow:
                overflow_lines.extend(block_overflow)
        else:
            # No edit — write all spans back at exact positions
            _write_block_verbatim(target_page, block_spans)

    return overflow_lines


def _write_block_verbatim(target_page: fitz.Page, block_spans: list[list[dict]]) -> None:
    """Write all spans of a block back at their exact original positions."""
    for line_spans in block_spans:
        for span in line_spans:
            text = span["text"]
            if not text.rstrip():
                continue

            origin = span["origin"]
            font_name = span["font"]
            font_size = span["size"]
            color_int = span["color"]

            # Convert color int to RGB tuple
            r = ((color_int >> 16) & 0xFF) / 255.0
            g = ((color_int >> 8) & 0xFF) / 255.0
            b = (color_int & 0xFF) / 255.0

            # Map font to a usable PyMuPDF font
            builtin = _map_font(font_name, span["flags"])

            target_page.insert_text(
                fitz.Point(origin[0], origin[1]),
                text.rstrip(),
                fontname=builtin,
                fontsize=font_size,
                color=(r, g, b),
            )


def _write_edited_block(
    target_page: fitz.Page,
    block: dict,
    block_text: str,
    edit: tuple[str, str],
    page_width: float,
    page_height: float,
) -> None:
    """Rebuild a block with the edit applied, maintaining position and style.

    Strategy:
    - Get the block's bounding box and first line position
    - Apply the text replacement
    - Word-wrap the new text to fit the block width
    - Write each line at the correct position with original line spacing
    - Clip at the footer boundary (content_bottom = page_height - 72)
    """
    old_text, new_text = edit
    bbox = block["bbox"]
    block_x0 = bbox[0]
    block_width = bbox[2] - bbox[0]
    content_bottom = page_height - 72

    # Get style from first span
    first_span = block["lines"][0]["spans"][0]
    font_name = first_span.get("font", "TimesNewRoman")
    font_size = first_span.get("size", 12)
    color_int = first_span.get("color", 0)
    first_origin = first_span.get("origin", (bbox[0], bbox[1] + font_size))

    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0

    builtin = _map_font(font_name, first_span.get("flags", 0))

    # Calculate line height from original block
    num_lines = len(block["lines"])
    block_height = bbox[3] - bbox[1]
    line_height = block_height / num_lines if num_lines > 1 else font_size * 1.2

    # Apply the edit — since this block was identified as the edit target,
    # replace the entire block content with the new text
    new_block_text = " ".join(new_text.split())

    # Word-wrap
    try:
        measure_font = fitz.Font(fontname=builtin)
    except Exception:
        measure_font = None

    wrapped = _word_wrap_simple(new_block_text.strip(), block_width, measure_font, font_size)

    # Write lines
    baseline_y = first_origin[1]
    overflow_lines = []

    for i, line_text in enumerate(wrapped):
        y = baseline_y + i * line_height
        if y > content_bottom:
            overflow_lines = wrapped[i:]
            break
        target_page.insert_text(
            fitz.Point(block_x0, y),
            line_text,
            fontname=builtin,
            fontsize=font_size,
            color=(r, g, b),
        )

    # Store overflow lines on the page object for the export to retrieve
    if overflow_lines:
        if not hasattr(target_page, "_overflow_lines"):
            target_page._overflow_lines = []
        target_page._overflow_lines.extend(overflow_lines)



def _map_font(font_name: str, flags: int) -> str:
    """Map a PDF font name to a PyMuPDF built-in font name."""
    lower = font_name.lower()
    bold = bool(flags & (1 << 4)) or "bold" in lower
    italic = bool(flags & (1 << 1)) or "italic" in lower

    if "times" in lower:
        if bold and italic:
            return "tibi"
        if bold:
            return "tibo"
        if italic:
            return "tiit"
        return "tiro"
    if "arial" in lower or "helvetica" in lower:
        if bold and italic:
            return "hebi"
        if bold:
            return "hebo"
        if italic:
            return "heit"
        return "helv"
    if "courier" in lower:
        return "cobo" if bold else "cour"
    if "symbol" in lower:
        return "symb"
    return "tiro"


def _word_wrap_simple(text: str, max_width: float, font, font_size: float) -> list[str]:
    """Word-wrap text to fit within max_width."""
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip() if current else word
        if font:
            w = font.text_length(test, fontsize=font_size)
        else:
            w = len(test) * font_size * 0.5

        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines

    return overflow_lines
