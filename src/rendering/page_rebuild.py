"""Page rebuild: reconstruct a PDF page from rawdict with edits applied.

The cleanest approach to 1:1 PDF editing:
1. Extract every visual element from the source page (text spans, drawings, images)
2. Apply the user's text edits to the relevant spans
3. Write everything back to a blank page at exact positions using system fonts
   (metrically identical to the document's embedded fonts)

This produces a page that is visually identical to the original except
for the edited text, which flows naturally with correct font, color,
and positioning.
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz

from src.rendering.page_patch import _get_font_object, _get_pymupdf_fontname

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def rebuild_page_with_edits(
    source_path: Path | str,
    page_number: int,
    edits: list[dict],
    prepend_overflow: list[dict] | None = None,
) -> bytes:
    """Rebuild a page from source with text edits applied.

    Args:
        source_path: Path to the original PDF
        page_number: 1-based page number
        edits: List of {"old_text": str, "new_text": str} dicts
        prepend_overflow: Optional list of overflow span dicts from the previous page
                          to insert at the top of this page (before existing content).

    Returns:
        PNG image bytes of the rebuilt page
    """
    doc = fitz.open(str(source_path))
    page = doc[page_number - 1]

    new_page_doc, overflow = _rebuild_page(page, edits, prepend_overflow)

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
    prepend_overflow: list[dict] | None = None,
) -> tuple[fitz.Document, list[dict]]:
    """Rebuild a page and return as a single-page fitz.Document plus overflow spans.

    Args:
        source_doc: Open fitz.Document
        page_number: 1-based page number
        edits: List of {"old_text": str, "new_text": str} dicts
        prepend_overflow: Optional overflow spans from previous page to prepend.

    Returns:
        (new_doc, overflow_spans) - the rebuilt page doc and any spans that didn't fit.
        overflow_spans is a list of dicts with keys: text, font, size, flags, color, line_height
    """
    page = source_doc[page_number - 1]
    new_doc, overflow = _rebuild_page(page, edits, prepend_overflow)
    return new_doc, overflow


# ---------------------------------------------------------------------------
# Core rebuild logic
# ---------------------------------------------------------------------------


def _rebuild_page(
    page: fitz.Page,
    edits: list[dict],
    prepend_overflow: list[dict] | None = None,
) -> tuple[fitz.Document, list[dict]]:
    """Core rebuild: extract source page content, apply edits, write to new page.

    Returns:
        (new_doc, overflow_spans) - rebuilt page and spans that didn't fit.
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
    overflow = _rebuild_text(page, new_page, edits, prepend_overflow)

    return new_doc, overflow


# ---------------------------------------------------------------------------
# Drawing / Image copy (unchanged from original)
# ---------------------------------------------------------------------------


def _copy_drawings(source_page: fitz.Page, target_page: fitz.Page) -> None:
    """Copy all vector drawings from source to target page."""
    drawings = source_page.get_drawings()
    for drawing in drawings:
        items = drawing.get("items", [])
        color = drawing.get("color")
        fill = drawing.get("fill")
        width = drawing.get("width", 1.0)
        close_path = drawing.get("closePath", False)

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

        if close_path:
            first_pt = items[0][1] if items[0][0] == "l" else fitz.Point(0, 0)
            shape.draw_line(shape.last_point, first_pt)

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


# ---------------------------------------------------------------------------
# Text rebuild (the core rewrite)
# ---------------------------------------------------------------------------


def _rebuild_text(
    source_page: fitz.Page,
    target_page: fitz.Page,
    edits: list[dict],
    prepend_overflow: list[dict] | None = None,
) -> list[dict]:
    """Extract all text spans, apply edits, write to target page using TextWriter.

    Uses system fonts (Liberation family) for exact metric matching with
    the document's embedded fonts.

    Returns overflow spans that didn't fit on the page.
    """
    raw = source_page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    # Build edit lookup: list of (old_text_normalized, new_text)
    edit_map = []
    for edit in edits:
        old = edit["old_text"]
        new = edit["new_text"]
        if old != new:
            edit_map.append((old, new))

    page_height = source_page.rect.height
    page_width = source_page.rect.width
    content_bottom = page_height - 72  # footer boundary

    # TextWriter for precise font-based text placement
    tw = fitz.TextWriter(target_page.rect)

    # Font object cache: (font_name, bold, italic) -> fitz.Font
    font_cache: dict[tuple[str, bool, bool], fitz.Font] = {}

    overflow_spans: list[dict] = []

    # If we have overflow from a previous page, write it at the top first
    # and track how much vertical space it consumed so we can shift content down.
    overflow_shift = 0.0
    if prepend_overflow:
        overflow_shift = _write_prepended_overflow(
            tw, font_cache, prepend_overflow, page_width, content_bottom
        )

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue

        # Collect block-level information
        block_lines_data = _extract_block_lines(block)
        block_text = " ".join(
            "".join(s["text"] for s in line_spans).rstrip()
            for line_spans in block_lines_data
        )

        # Determine if this block is a header/footer (should NOT be shifted)
        block_y0 = block["bbox"][1]
        is_header_footer = block_y0 < 60 or block_y0 > page_height - 55
        effective_shift = 0.0 if is_header_footer else overflow_shift

        # Check if any edit applies to this block
        applied_edit = _find_matching_edit(block_text, edit_map)

        if applied_edit:
            # This block has an edit — rebuild with heading preservation
            block_overflow = _write_edited_block_v2(
                tw, font_cache, block, block_lines_data, block_text,
                applied_edit, page_width, content_bottom, effective_shift,
            )
            if block_overflow:
                overflow_spans.extend(block_overflow)
        else:
            # No edit — write all spans back at exact positions using TextWriter
            _write_block_verbatim_v2(
                tw, font_cache, block_lines_data, effective_shift, content_bottom,
                overflow_spans,
            )

    # Commit all text to the page
    tw.write_text(target_page)

    return overflow_spans


# ---------------------------------------------------------------------------
# Overflow prepending
# ---------------------------------------------------------------------------


def _write_prepended_overflow(
    tw: fitz.TextWriter,
    font_cache: dict,
    overflow_spans: list[dict],
    page_width: float,
    content_bottom: float,
) -> float:
    """Write overflow spans from a previous page at the top of this page.

    Returns the total vertical shift (how much existing content needs to move down).
    """
    # Start writing at the top content area (below header zone)
    y_start = 72.0  # below header
    y = y_start

    for span_info in overflow_spans:
        text = span_info["text"]
        font_name = span_info.get("font", "TimesNewRoman")
        font_size = span_info.get("size", 12.0)
        flags = span_info.get("flags", 0)
        line_height = span_info.get("line_height", font_size * 1.18)
        x = span_info.get("x", 90.0)

        bold = bool(flags & (1 << 4)) or "bold" in font_name.lower()
        italic = bool(flags & (1 << 1)) or "italic" in font_name.lower()

        font_obj = _get_cached_font(font_cache, font_name, bold, italic)

        if y + line_height > content_bottom:
            # Even the overflow doesn't fit — this shouldn't normally happen
            break

        tw.append(fitz.Point(x, y), text, font=font_obj, fontsize=font_size)
        y += line_height

    return y - y_start  # total shift amount


# ---------------------------------------------------------------------------
# Verbatim block writing (unedited blocks)
# ---------------------------------------------------------------------------


def _write_block_verbatim_v2(
    tw: fitz.TextWriter,
    font_cache: dict,
    block_lines_data: list[list[dict]],
    overflow_shift: float,
    content_bottom: float,
    overflow_collector: list[dict],
) -> None:
    """Write all spans of a block at their exact original positions using TextWriter.

    If overflow_shift > 0, all y-positions are shifted down. Spans that would
    exceed content_bottom are added to overflow_collector instead.
    """
    for line_spans in block_lines_data:
        for span in line_spans:
            text = span["text"]
            if not text.rstrip():
                continue

            origin_x, origin_y = span["origin"]
            font_name = span["font"]
            font_size = span["size"]
            flags = span["flags"]
            color_int = span["color"]

            bold = bool(flags & (1 << 4)) or "bold" in font_name.lower()
            italic = bool(flags & (1 << 1)) or "italic" in font_name.lower()

            effective_y = origin_y + overflow_shift

            if effective_y > content_bottom:
                # This span overflows — collect it for the next page
                overflow_collector.append({
                    "text": text.rstrip(),
                    "font": font_name,
                    "size": font_size,
                    "flags": flags,
                    "color": color_int,
                    "line_height": font_size * 1.18,
                    "x": origin_x,
                })
                continue

            font_obj = _get_cached_font(font_cache, font_name, bold, italic)

            try:
                tw.append(
                    fitz.Point(origin_x, effective_y),
                    text.rstrip(),
                    font=font_obj,
                    fontsize=font_size,
                )
            except Exception:
                # Fallback: skip problematic spans silently
                logger.debug(f"Failed to write span: {text[:30]}")


# ---------------------------------------------------------------------------
# Edited block writing (with heading preservation)
# ---------------------------------------------------------------------------


def _write_edited_block_v2(
    tw: fitz.TextWriter,
    font_cache: dict,
    block: dict,
    block_lines_data: list[list[dict]],
    block_text: str,
    edit: tuple[str, str],
    page_width: float,
    content_bottom: float,
    overflow_shift: float,
) -> list[dict]:
    """Rebuild a block with the edit applied, preserving heading lines.

    Strategy:
    1. Identify heading lines (first line(s) in Bold/larger font)
    2. Write heading lines verbatim at their original positions
    3. Word-wrap the new paragraph text using the paragraph font/size
    4. Write wrapped lines starting after the heading
    5. Return overflow spans if text exceeds content_bottom
    """
    old_text, new_text = edit
    bbox = block["bbox"]
    block_x0 = bbox[0]
    block_width = bbox[2] - bbox[0]

    # Separate heading lines from paragraph lines
    heading_lines, para_lines = _split_heading_and_paragraph(block_lines_data)

    # Write heading lines verbatim
    last_heading_y = 0.0
    last_heading_line_height = 14.0

    for line_spans in heading_lines:
        for span in line_spans:
            text = span["text"]
            if not text.rstrip():
                continue
            origin_x, origin_y = span["origin"]
            font_name = span["font"]
            font_size = span["size"]
            flags = span["flags"]

            bold = bool(flags & (1 << 4)) or "bold" in font_name.lower()
            italic = bool(flags & (1 << 1)) or "italic" in font_name.lower()

            effective_y = origin_y + overflow_shift
            font_obj = _get_cached_font(font_cache, font_name, bold, italic)

            try:
                tw.append(
                    fitz.Point(origin_x, effective_y),
                    text.rstrip(),
                    font=font_obj,
                    fontsize=font_size,
                )
            except Exception:
                pass

            if effective_y > last_heading_y:
                last_heading_y = effective_y
                last_heading_line_height = font_size * 1.18

    # Determine paragraph style from the first paragraph span
    para_font_name = "TimesNewRoman"
    para_font_size = 12.0
    para_flags = 0
    para_color_int = 0
    para_line_height = 14.16  # default

    if para_lines:
        first_para_span = para_lines[0][0]
        para_font_name = first_para_span["font"]
        para_font_size = first_para_span["size"]
        para_flags = first_para_span["flags"]
        para_color_int = first_para_span["color"]

        # Calculate line height from original paragraph lines
        if len(para_lines) >= 2:
            y1 = para_lines[0][0]["origin"][1]
            y2 = para_lines[1][0]["origin"][1]
            para_line_height = y2 - y1
        else:
            para_line_height = para_font_size * 1.18

    para_bold = bool(para_flags & (1 << 4)) or "bold" in para_font_name.lower()
    para_italic = bool(para_flags & (1 << 1)) or "italic" in para_font_name.lower()
    para_font_obj = _get_cached_font(font_cache, para_font_name, para_bold, para_italic)

    # Determine the starting y for paragraph text
    if heading_lines:
        para_start_y = last_heading_y + last_heading_line_height
    elif para_lines:
        para_start_y = para_lines[0][0]["origin"][1] + overflow_shift
    else:
        para_start_y = bbox[1] + para_font_size + overflow_shift

    # Word-wrap the new text
    new_block_text = " ".join(new_text.split())
    wrapped = _word_wrap(new_block_text.strip(), block_width, para_font_obj, para_font_size)

    # Write wrapped paragraph lines
    overflow_spans: list[dict] = []

    for i, line_text in enumerate(wrapped):
        y = para_start_y + i * para_line_height

        if y > content_bottom:
            # Everything from here on overflows
            for j in range(i, len(wrapped)):
                overflow_spans.append({
                    "text": wrapped[j],
                    "font": para_font_name,
                    "size": para_font_size,
                    "flags": para_flags,
                    "color": para_color_int,
                    "line_height": para_line_height,
                    "x": block_x0,
                })
            break

        try:
            tw.append(
                fitz.Point(block_x0, y),
                line_text,
                font=para_font_obj,
                fontsize=para_font_size,
            )
        except Exception:
            pass

    return overflow_spans


# ---------------------------------------------------------------------------
# Heading/paragraph splitting
# ---------------------------------------------------------------------------


def _split_heading_and_paragraph(
    block_lines_data: list[list[dict]],
) -> tuple[list[list[dict]], list[list[dict]]]:
    """Split a block's lines into heading lines and paragraph lines.

    A line is considered a heading if:
    - It's in a Bold font (flags & 1<<4 or "bold" in font name)
    - OR it's in a sans-serif font (Arial/Helvetica) while the rest is serif
    - AND it appears before any non-heading line

    This preserves section headings like "4. Electrical Interface" that
    appear on the first line of a block before the paragraph text.
    """
    if not block_lines_data:
        return [], []

    heading_lines: list[list[dict]] = []
    para_lines: list[list[dict]] = []

    # Determine the "majority" font family of the block (for comparison)
    all_fonts = []
    for line_spans in block_lines_data:
        for span in line_spans:
            if span["text"].strip():
                all_fonts.append(span["font"].lower())

    # If the block is entirely one font, there's no heading distinction
    # (unless the first line is bold)
    heading_ended = False

    for line_spans in block_lines_data:
        if heading_ended:
            para_lines.append(line_spans)
            continue

        # Check if this line is a heading line
        is_heading_line = False
        for span in line_spans:
            if not span["text"].strip():
                continue
            font_lower = span["font"].lower()
            flags = span["flags"]
            is_bold = bool(flags & (1 << 4)) or "bold" in font_lower
            is_sans = (
                "arial" in font_lower
                or "helvetica" in font_lower
                or ("liberation" in font_lower and "sans" in font_lower)
            )

            # Heading if bold, or if it's sans-serif while block also contains serif
            if is_bold or (is_sans and any("times" in f or "serif" in f for f in all_fonts)):
                is_heading_line = True
                break

        if is_heading_line:
            heading_lines.append(line_spans)
        else:
            heading_ended = True
            para_lines.append(line_spans)

    return heading_lines, para_lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_block_lines(block: dict) -> list[list[dict]]:
    """Extract all spans from a rawdict block into a structured format.

    Returns a list of lines, where each line is a list of span dicts with keys:
    text, font, size, flags, color, origin, bbox
    """
    block_lines = []
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
        block_lines.append(line_spans)
    return block_lines


def _find_matching_edit(
    block_text: str, edit_map: list[tuple[str, str]]
) -> tuple[str, str] | None:
    """Check if any edit applies to this block.

    Matches by checking if the normalized old_text overlaps with the block text.
    """
    block_normalized = " ".join(block_text.split())

    for old_text, new_text in edit_map:
        old_normalized = " ".join(old_text.split())
        # Match if the block contains the start of the old text (60+ chars)
        # OR if the old text contains the block text
        # OR if the old text is fully within the block text
        old_start = old_normalized[:60]
        if (old_start and old_start in block_normalized
                or block_normalized[:60] in old_normalized
                or old_normalized in block_normalized):
            return (old_text, new_text)

    return None


def _get_cached_font(
    cache: dict[tuple[str, bool, bool], fitz.Font],
    font_name: str,
    bold: bool,
    italic: bool,
) -> fitz.Font:
    """Get or create a fitz.Font object, using system fonts when available.

    Falls back to PyMuPDF built-in fonts if no system font is found.
    """
    key = (font_name.lower(), bold, italic)
    if key in cache:
        return cache[key]

    # Try system font first (metric-compatible Liberation family)
    font_obj = _get_font_object(font_name, bold, italic)
    if font_obj:
        cache[key] = font_obj
        return font_obj

    # Fallback to built-in font
    builtin_name = _get_pymupdf_fontname(font_name, bold, italic)
    try:
        font_obj = fitz.Font(fontname=builtin_name)
    except Exception:
        font_obj = fitz.Font(fontname="tiro")

    cache[key] = font_obj
    return font_obj


def _word_wrap(text: str, max_width: float, font: fitz.Font, font_size: float) -> list[str]:
    """Word-wrap text to fit within max_width using precise font metrics."""
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip() if current else word
        w = font.text_length(test, fontsize=font_size)

        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines
