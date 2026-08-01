"""Page patching: 1:1 text replacement on PDF pages.

Instead of re-rendering entire pages from IR (which loses formatting),
this module patches the source PDF page directly using PyMuPDF redaction.

The result is pixel-identical to the original except for the changed text.

Workflow:
1. Open source PDF, get the target page
2. For each edit on that page: find old text, redact it, insert new text
3. Render the patched page to PNG (for preview) or keep as PDF page (for export)
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz

from src.models.document_ir import DocumentIR, TextBlock

logger = logging.getLogger(__name__)

# System font file paths (metric-compatible substitutes for common PDF fonts)
# Liberation Serif = Times New Roman, Liberation Sans = Arial, Liberation Mono = Courier
import os as _os

_SYSTEM_FONT_PATHS = {
    # Liberation fonts (installed in Docker via fonts-liberation2)
    "liberation-serif": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "liberation-serif-bold": "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "liberation-serif-italic": "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "liberation-serif-bolditalic": "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
    "liberation-sans": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "liberation-sans-bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "liberation-sans-italic": "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    "liberation-sans-bolditalic": "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
    "liberation-mono": "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "liberation-mono-bold": "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    # Also check liberation2 path
    "liberation2-serif": "/usr/share/fonts/liberation2/LiberationSerif-Regular.ttf",
    "liberation2-serif-bold": "/usr/share/fonts/liberation2/LiberationSerif-Bold.ttf",
    "liberation2-sans": "/usr/share/fonts/liberation2/LiberationSans-Regular.ttf",
    "liberation2-sans-bold": "/usr/share/fonts/liberation2/LiberationSans-Bold.ttf",
    # Windows paths
    "win-times": "C:/Windows/Fonts/times.ttf",
    "win-times-bold": "C:/Windows/Fonts/timesbd.ttf",
    "win-arial": "C:/Windows/Fonts/arial.ttf",
    "win-arial-bold": "C:/Windows/Fonts/arialbd.ttf",
    "win-courier": "C:/Windows/Fonts/cour.ttf",
}


def _find_system_font(font_name: str, bold: bool = False, italic: bool = False) -> str | None:
    """Find a metrically-compatible system font file for a PDF font name.

    Returns the path to a TTF file, or None if not found.
    """
    lower = font_name.lower()

    # Determine font family
    if "times" in lower or lower in ("tiro",):
        family = "serif"
    elif "arial" in lower or "helvetica" in lower or lower in ("helv",):
        family = "sans"
    elif "courier" in lower or lower in ("cour",):
        family = "mono"
    else:
        family = "serif"  # Default to serif

    # Build variant key
    variant = ""
    if bold and italic:
        variant = "-bolditalic"
    elif bold:
        variant = "-bold"
    elif italic:
        variant = "-italic"

    # Try Liberation fonts first (Linux/Docker)
    candidates = [
        f"liberation-{family}{variant}",
        f"liberation2-{family}{variant}",
        f"liberation-{family}",  # fallback to regular
        f"liberation2-{family}",
    ]

    # Add Windows fallbacks
    if family == "serif":
        candidates.append("win-times-bold" if bold else "win-times")
    elif family == "sans":
        candidates.append("win-arial-bold" if bold else "win-arial")
    elif family == "mono":
        candidates.append("win-courier")

    for key in candidates:
        path = _SYSTEM_FONT_PATHS.get(key)
        if path and _os.path.exists(path):
            return path

    return None


def _get_font_object(font_name: str, bold: bool = False, italic: bool = False) -> fitz.Font | None:
    """Get a fitz.Font object using a system font file for exact metric matching.

    Returns None if no matching system font is found (will fall back to built-in).
    """
    path = _find_system_font(font_name, bold, italic)
    if path:
        try:
            return fitz.Font(fontfile=path)
        except Exception:
            pass
    return None


def _get_pymupdf_fontname(font_name: str, bold: bool = False, italic: bool = False) -> str:
    """Map a PDF font name to a PyMuPDF built-in font name (fallback only)."""
    lower = font_name.lower()
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
        if bold:
            return "cobo"
        return "cour"
    return "tiro"


def find_edit_diff(source_page: fitz.Page, block: TextBlock, old_text: str, new_text: str) -> dict | None:
    """Find where old_text appears on the source page and prepare the patch.

    Returns a dict with:
        - rect: fitz.Rect of the old text on page
        - font_name: PyMuPDF font to use for replacement
        - font_size: size in points
        - baseline_y: y-coordinate of text baseline
        - new_text: the replacement text

    Returns None if old_text cannot be found on the page.
    """
    # Search for the exact old text
    instances = source_page.search_for(old_text)
    if not instances:
        # Try searching for the text without extra spaces
        instances = source_page.search_for(old_text.strip())
    if not instances:
        logger.warning(f"Could not find '{old_text[:30]}...' on page for patching")
        return None

    rect = instances[0]

    # Get font info from the source span at that location
    raw = source_page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    font_name = "TimesNewRoman"
    font_size = 12.0
    baseline_y = rect.y1 - 2.5
    bold = False
    italic = False

    for pdf_block in raw.get("blocks", []):
        if pdf_block.get("type") != 0:
            continue
        for line in pdf_block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                span_text = "".join(c["c"] for c in chars)
                if old_text in span_text:
                    font_name = span.get("font", "TimesNewRoman")
                    font_size = span.get("size", 12.0)
                    flags = span.get("flags", 0)
                    bold = bool(flags & (1 << 4)) or "bold" in font_name.lower()
                    italic = bool(flags & (1 << 1)) or "italic" in font_name.lower()
                    origin = span.get("origin")
                    if origin:
                        baseline_y = origin[1]
                    break

    return {
        "rect": rect,
        "font_name": _get_pymupdf_fontname(font_name, bold, italic),
        "font_size": font_size,
        "baseline_y": baseline_y,
        "new_text": new_text,
        "bold": bold,
        "italic": italic,
    }


def patch_page(
    source_path: Path | str,
    page_number: int,
    edits: list[dict],
) -> bytes:
    """Patch a page with text edits and return PNG bytes.

    Each edit is a dict from the session's edit history:
        {"old_text": str, "new_text": str, "block_id": str}

    Args:
        source_path: Path to the original PDF
        page_number: 1-based page number
        edits: List of edit dicts to apply

    Returns:
        PNG image bytes of the patched page
    """
    doc = fitz.open(str(source_path))
    page = doc[page_number - 1]

    for edit in edits:
        old_text = edit["old_text"]
        new_text = edit["new_text"]

        if old_text == new_text:
            continue

        _apply_edit_to_page(page, old_text, new_text)

    # Render to PNG
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def _detect_alignment(page: fitz.Page, rect: fitz.Rect, text: str) -> str:
    """Detect whether text at this position is center-aligned or left-aligned.

    Checks other spans on nearby lines (same column region) to determine
    if texts share a common center-x (table column) or have varying x0
    positions (paragraph flow).

    Returns:
        "center" for table cells, "left" for inline paragraph text.
    """
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    target_center = (rect.x0 + rect.x1) / 2
    target_y = (rect.y0 + rect.y1) / 2

    # Collect centers of other spans in a vertical band (same column, +/-50pt vertically)
    nearby_centers = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span["bbox"]
                span_center_y = (bbox[1] + bbox[3]) / 2
                span_center_x = (bbox[0] + bbox[2]) / 2
                if (abs(span_center_y - target_y) < 50
                        and abs(span_center_x - target_center) < 80
                        and not (abs(bbox[0] - rect.x0) < 1 and abs(bbox[1] - rect.y0) < 1)):
                    nearby_centers.append(span_center_x)

    if not nearby_centers:
        return "left"

    # Count how many nearby spans share our center (within 5pt)
    matching = sum(1 for c in nearby_centers if abs(c - target_center) < 5)

    # If 2+ neighbors share the same center -> table column (center-aligned)
    if matching >= 2:
        return "center"

    return "left"


def patch_page_to_pdf(
    source_path: Path | str,
    page_number: int,
    edits: list[dict],
) -> bytes:
    """Patch a page with text edits and return PDF bytes (single page).

    Same as patch_page but returns PDF bytes instead of PNG.
    """
    doc = fitz.open(str(source_path))
    page = doc[page_number - 1]

    for edit in edits:
        old_text = edit["old_text"]
        new_text = edit["new_text"]

        if old_text == new_text:
            continue

        _apply_edit_to_page(page, old_text, new_text)

    # Save as single-page PDF bytes
    # Create a new doc with just this page
    out_doc = fitz.open()
    out_doc.insert_pdf(doc, from_page=page_number - 1, to_page=page_number - 1)
    pdf_bytes = out_doc.tobytes()
    out_doc.close()
    doc.close()
    return pdf_bytes


def _extract_font_at_rect(page: fitz.Page, rect: fitz.Rect, text: str) -> tuple[str, float, float]:
    """Extract font name, size, and corrected baseline_y for text at a given rect.

    Returns:
        (pymupdf_fontname_or_system, font_size, corrected_baseline_y)
    """
    pdf_font_name, font_size, baseline_y, bold, italic, color = _extract_font_info(page, rect, text)
    return pdf_font_name, font_size, baseline_y


def _patch_paragraph_line(
    page: fitz.Page, rect: fitz.Rect, old_text: str, new_text: str,
    font_name: str, font_size: float, bold: bool, italic: bool, color: tuple,
) -> None:
    """Patch paragraph text by reflowing the paragraph portion of a block.

    Finds the PDF block containing the old text. If the block starts with
    heading lines (bold/sans-serif font), those are preserved at their original
    positions. Only the paragraph portion is redacted and retypeset.

    This ensures section headings like "4. Electrical Interface" are never
    destroyed by paragraph edits below them.
    """
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    target_block = None
    target_block_text = ""

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines_text = []
        for line in block.get("lines", []):
            line_text = ""
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                line_text += "".join(c["c"] for c in chars)
            lines_text.append(line_text.rstrip())
        block_text = " ".join(lines_text)
        old_text_normalized = " ".join(old_text.split())
        block_text_normalized = " ".join(block_text.split())
        if old_text_normalized in block_text_normalized:
            target_block = block
            target_block_text = block_text
            break

    if not target_block:
        # Fallback: redact just the search rect and insert
        page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions()
        builtin = _get_pymupdf_fontname(font_name, bold, italic)
        page.insert_text(
            fitz.Point(rect.x0, rect.y1 - 2.5), new_text,
            fontname=builtin, fontsize=font_size, color=color,
        )
        return

    # --- Separate heading lines from paragraph lines ---
    # A "heading line" is a line whose first span is bold or in a sans-serif font
    # (Arial, Helvetica) while the block also contains serif text.
    block_lines = target_block["lines"]
    heading_line_count = 0

    for line in block_lines:
        spans = line.get("spans", [])
        if not spans:
            break
        first_span = spans[0]
        span_font = first_span.get("font", "").lower()
        span_flags = first_span.get("flags", 0)
        is_bold = bool(span_flags & (1 << 4)) or "bold" in span_font
        is_sans = "arial" in span_font or "helvetica" in span_font

        if is_bold or is_sans:
            heading_line_count += 1
        else:
            break  # First non-heading line — everything after is paragraph

    # Get block geometry
    block_bbox = target_block["bbox"]
    block_rect = fitz.Rect(block_bbox)

    if heading_line_count > 0 and heading_line_count < len(block_lines):
        # Block has heading lines followed by paragraph lines.
        # Only redact the PARAGRAPH portion (below the heading).
        heading_last_line = block_lines[heading_line_count - 1]
        heading_bottom_y = max(
            span["bbox"][3] for span in heading_last_line.get("spans", [])
        )

        # Paragraph rect: from below the heading to the bottom of the block
        para_rect = fitz.Rect(
            block_bbox[0],
            heading_bottom_y,
            block_bbox[2],
            block_bbox[3],
        )

        # Get paragraph style from first paragraph span
        para_first_line = block_lines[heading_line_count]
        para_first_span = para_first_line["spans"][0]
        para_font_name = para_first_span.get("font", font_name)
        para_font_size = para_first_span.get("size", font_size)
        para_flags = para_first_span.get("flags", 0)
        para_bold = bool(para_flags & (1 << 4)) or "bold" in para_font_name.lower()
        para_italic = bool(para_flags & (1 << 1)) or "italic" in para_font_name.lower()
        para_origin = para_first_span.get("origin", (para_rect.x0, para_rect.y0 + para_font_size))

        # Extract color from paragraph span
        para_color_int = para_first_span.get("color", 0)
        pr = ((para_color_int >> 16) & 0xFF) / 255.0
        pg = ((para_color_int >> 8) & 0xFF) / 255.0
        pb = (para_color_int & 0xFF) / 255.0
        para_color = (pr, pg, pb)

        # Compute paragraph line height
        para_lines_in_block = block_lines[heading_line_count:]
        if len(para_lines_in_block) >= 2:
            y1 = para_lines_in_block[0]["spans"][0].get("origin", (0, 0))[1]
            y2 = para_lines_in_block[1]["spans"][0].get("origin", (0, 0))[1]
            para_line_height = y2 - y1
        else:
            para_line_height = para_font_size * 1.2

        # Redact ONLY the paragraph portion (heading stays intact)
        page.add_redact_annot(para_rect, fill=(1, 1, 1))
        page.apply_redactions()

        # Reconstruct the full paragraph text from the original rawdict lines,
        # then apply the old→new fragment replacement within it.
        # This ensures we don't lose text that was OUTSIDE the changed fragment.
        original_para_parts = []
        for line in block_lines[heading_line_count:]:
            line_text = ""
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                line_text += "".join(c["c"] for c in chars)
            original_para_parts.append(line_text.rstrip())
        original_para_text = " ".join(original_para_parts)

        # Apply the fragment replacement within the full paragraph
        old_text_normalized = " ".join(old_text.split())
        new_text_normalized = " ".join(new_text.split())
        original_para_normalized = " ".join(original_para_text.split())

        # Check if the new_text includes the heading (full block replacement)
        heading_text_parts = []
        for line in block_lines[:heading_line_count]:
            line_text = ""
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                line_text += "".join(c["c"] for c in chars)
            heading_text_parts.append(line_text.strip())
        heading_normalized = " ".join(" ".join(heading_text_parts).split())

        if new_text_normalized.startswith(heading_normalized):
            # Full block replacement — new_text includes heading, strip it
            para_new_text = new_text_normalized[len(heading_normalized):].strip()
        elif old_text_normalized in original_para_normalized:
            # Fragment replacement within the paragraph
            para_new_text = original_para_normalized.replace(
                old_text_normalized, new_text_normalized, 1
            )
        else:
            # Fallback: use new_text as-is
            para_new_text = new_text_normalized

        # Word-wrap and insert the paragraph text
        builtin = _get_pymupdf_fontname(para_font_name, para_bold, para_italic)
        content_width = para_rect.width

        try:
            measure_font = fitz.Font(fontname=builtin)
        except Exception:
            measure_font = None

        wrapped_lines = _word_wrap(para_new_text.strip(), content_width, measure_font, para_font_size)

        page_height = page.rect.height
        content_bottom_y = page_height - 72
        first_para_y = para_origin[1]

        overflow_lines = []
        for i, line_text in enumerate(wrapped_lines):
            y = first_para_y + i * para_line_height
            if y > content_bottom_y:
                overflow_lines = wrapped_lines[i:]
                break
            page.insert_text(
                fitz.Point(para_rect.x0, y),
                line_text,
                fontname=builtin,
                fontsize=para_font_size,
                color=para_color,
            )

        return overflow_lines

    # --- No heading separation needed: reflow the entire block ---
    # Apply the text replacement to the full block text
    block_text_spaces = " ".join(target_block_text.split())
    old_text_spaces = " ".join(old_text.split())
    new_text_spaces = " ".join(new_text.split())
    new_block_text = block_text_spaces.replace(old_text_spaces, new_text_spaces, 1)

    # Compute line height from original
    num_lines = len(block_lines)
    line_height = block_rect.height / num_lines if num_lines > 0 else font_size * 1.2

    # Get the first line's baseline for correct vertical positioning
    first_origin = block_lines[0]["spans"][0].get("origin", (0, 0))
    first_baseline_y = first_origin[1] if first_origin else block_rect.y0 + font_size

    # Redact the entire paragraph block
    page.add_redact_annot(block_rect, fill=(1, 1, 1))
    page.apply_redactions()

    # Manually word-wrap and insert line-by-line with correct line spacing
    builtin = _get_pymupdf_fontname(font_name, bold, italic)
    content_width = block_rect.width

    try:
        measure_font = fitz.Font(fontname=builtin)
    except Exception:
        measure_font = None

    wrapped_lines = _word_wrap(new_block_text.strip(), content_width, measure_font, font_size)

    page_height = page.rect.height
    content_bottom_y = page_height - 72

    overflow_lines = []
    for i, line_text in enumerate(wrapped_lines):
        y = first_baseline_y + i * line_height
        if y > content_bottom_y:
            overflow_lines = wrapped_lines[i:]
            break
        page.insert_text(
            fitz.Point(block_rect.x0, y),
            line_text,
            fontname=builtin,
            fontsize=font_size,
            color=color,
        )

    return overflow_lines


def _apply_edit_to_page(page: fitz.Page, old_text: str, new_text: str) -> list[str]:
    """Apply a single text edit to a PDF page.

    Uses the same logic as the page image renderer:
    - Finds the old text on the page
    - Detects alignment (table center vs paragraph)
    - For paragraphs: reflows the entire paragraph block
    - For tables: centers the new text in the cell

    Returns:
        List of overflow lines that didn't fit on the page (empty if all fit).
    """
    if old_text == new_text:
        return []

    instances = page.search_for(old_text)
    if not instances:
        logger.warning(f"_apply_edit_to_page: '{old_text[:30]}...' not found")
        return []

    # search_for can return multiple rects for one match (when the text spans
    # across separate PDF spans/lines). Union them into a single covering rect.
    if len(instances) == 1:
        rect = instances[0]
    else:
        # Multiple rects: likely one match split across spans (e.g., "4." + "Electrical Interface")
        # Union all rects that are on the same line (similar y)
        first_y = instances[0].y0
        same_line = [r for r in instances if abs(r.y0 - first_y) < 5]
        if same_line:
            rect = same_line[0]
            for r in same_line[1:]:
                rect = rect | r  # union
        else:
            rect = instances[0]
    font_name, font_size, baseline_y, bold, italic, color = _extract_font_info(page, rect, old_text)
    alignment = _detect_alignment(page, rect, old_text)

    if alignment == "center":
        # TABLE CELL — shrink the redaction rect slightly to avoid
        # covering the cell border lines (drawn as thin filled rectangles
        # just below/beside the text bbox).
        redact_rect = fitz.Rect(
            rect.x0 + 0.5,
            rect.y0 + 0.5,
            rect.x1 - 0.5,
            rect.y1 - 1.0,  # extra margin at bottom where border sits
        )
        page.add_redact_annot(redact_rect, fill=(1, 1, 1))
        page.apply_redactions()

        original_center_x = (rect.x0 + rect.x1) / 2
        font_obj = _get_font_object(font_name, bold, italic)
        if font_obj:
            new_width = font_obj.text_length(new_text, fontsize=font_size)
            insert_x = original_center_x - new_width / 2
            tw = fitz.TextWriter(page.rect)
            tw.append(fitz.Point(insert_x, baseline_y), new_text, font=font_obj, fontsize=font_size)
            tw.write_text(page, color=color)
        else:
            builtin = _get_pymupdf_fontname(font_name, bold, italic)
            try:
                fb = fitz.Font(fontname=builtin)
                new_width = fb.text_length(new_text, fontsize=font_size)
                insert_x = original_center_x - new_width / 2
            except Exception:
                insert_x = rect.x0
            page.insert_text(
                fitz.Point(insert_x, baseline_y), new_text,
                fontname=builtin, fontsize=font_size, color=color,
            )
        return []
    elif len(old_text) < 120 and "\n" not in old_text:
        # SHORT INLINE REPLACEMENT — for TOC entries, short titles, labels.
        # Just redact the found rect and insert new text at the same position.
        # Do NOT trigger paragraph reflow (which would destroy surrounding content
        # by redacting the entire containing block).
        #
        # For TOC entries: the search rect may only cover the title text, but
        # the full line includes leader dots and page number. Find the containing
        # span in rawdict to get the full visual extent of the line, the correct
        # font, and the correct insertion point.
        redact_rect = rect
        insert_x = rect.x0
        span_font = font_name
        span_size = font_size
        span_bold = bold
        span_italic = italic
        span_baseline = baseline_y
        span_color = color

        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    span_text = "".join(c["c"] for c in chars)
                    # Find the span that contains the core of our search text
                    # (last word of old_text to avoid matching the section number)
                    search_word = old_text.split()[-1]  # e.g., "Interface"
                    if search_word in span_text and "..." in span_text:
                        # This is the TOC entry span — use its full extent
                        redact_rect = fitz.Rect(span["bbox"])
                        insert_x = span["bbox"][0]
                        span_font = span.get("font", font_name)
                        span_size = span.get("size", font_size)
                        flags = span.get("flags", 0)
                        span_bold = bool(flags & (1 << 4)) or "bold" in span_font.lower()
                        span_italic = bool(flags & (1 << 1)) or "italic" in span_font.lower()
                        origin = span.get("origin")
                        if origin:
                            span_baseline = origin[1]
                        # Extract color
                        color_int = span.get("color", 0)
                        cr = ((color_int >> 16) & 0xFF) / 255.0
                        cg = ((color_int >> 8) & 0xFF) / 255.0
                        cb = (color_int & 0xFF) / 255.0
                        span_color = (cr, cg, cb)
                        break

        # Also redact the section number span ("4.") if it's separate
        # so we can rewrite the full entry cleanly
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    span_text = "".join(c["c"] for c in chars).strip()
                    bbox = span["bbox"]
                    # Section number: same y-line, to the left of our span, short text like "4."
                    if (abs(bbox[1] - redact_rect.y0) < 2
                            and bbox[0] < redact_rect.x0
                            and len(span_text) <= 5
                            and span_text.endswith(".")):
                        # Check if this section number is part of our old_text
                        if old_text.startswith(span_text) or old_text.startswith(span_text.rstrip(".")):
                            # Expand redact rect to include the section number
                            num_rect = fitz.Rect(bbox)
                            redact_rect = redact_rect | num_rect
                            insert_x = bbox[0]  # Start insertion from section number position
                            break

        page.add_redact_annot(redact_rect, fill=(1, 1, 1))
        page.apply_redactions()

        # Insert new text with the SAME font/size/color as the original span
        font_obj = _get_font_object(span_font, span_bold, span_italic)
        if font_obj:
            tw = fitz.TextWriter(page.rect)
            tw.append(
                fitz.Point(insert_x, span_baseline),
                new_text,
                font=font_obj,
                fontsize=span_size,
            )
            tw.write_text(page, color=span_color)
        else:
            builtin = _get_pymupdf_fontname(span_font, span_bold, span_italic)
            page.insert_text(
                fitz.Point(insert_x, span_baseline),
                new_text,
                fontname=builtin,
                fontsize=span_size,
                color=span_color,
            )
        return []
    else:
        # PARAGRAPH: full block reflow — returns overflow lines
        return _patch_paragraph_line(page, rect, old_text, new_text,
                              font_name, font_size, bold, italic, color)


def _extract_font_info(page: fitz.Page, rect: fitz.Rect, text: str) -> tuple[str, float, float, bool, bool, tuple]:
    """Extract font name, size, corrected baseline_y, bold, italic, and color.

    Returns:
        (pdf_font_name, font_size, corrected_baseline_y, bold, italic, color_rgb)
        color_rgb is (r, g, b) floats 0.0-1.0
    """
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    pdf_font_name = "TimesNewRoman"
    font_size = 12.0
    baseline_y = rect.y1 - 2.5
    bold = False
    italic = False
    color_rgb = (0.0, 0.0, 0.0)

    for pdf_block in raw.get("blocks", []):
        if pdf_block.get("type") != 0:
            continue
        for line in pdf_block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                span_text = "".join(c["c"] for c in chars)
                if text in span_text:
                    pdf_font_name = span.get("font", "TimesNewRoman")
                    font_size = span.get("size", 12.0)
                    flags = span.get("flags", 0)
                    bold = bool(flags & (1 << 4)) or "bold" in pdf_font_name.lower()
                    italic = bool(flags & (1 << 1)) or "italic" in pdf_font_name.lower()

                    # Extract color from span
                    color_int = span.get("color", 0)
                    cr = ((color_int >> 16) & 0xFF) / 255.0
                    cg = ((color_int >> 8) & 0xFF) / 255.0
                    cb = (color_int & 0xFF) / 255.0
                    color_rgb = (cr, cg, cb)

                    origin = span.get("origin")
                    bbox_y0 = span["bbox"][1]

                    if origin and font_size > 0:
                        baseline_y = origin[1]
                        font_obj = _get_font_object(pdf_font_name, bold, italic)
                        if not font_obj:
                            ascender_original = (origin[1] - bbox_y0) / font_size
                            try:
                                builtin_name = _get_pymupdf_fontname(pdf_font_name, bold, italic)
                                sub_font = fitz.Font(fontname=builtin_name)
                                ascender_sub = sub_font.ascender
                                ascender_diff = (ascender_sub - ascender_original) * font_size
                                baseline_y = origin[1] + ascender_diff
                            except Exception:
                                pass
                    elif origin:
                        baseline_y = origin[1]

                    return pdf_font_name, font_size, baseline_y, bold, italic, color_rgb

    return pdf_font_name, font_size, baseline_y, bold, italic, color_rgb


def get_page_edits_from_session(session, document_ir: DocumentIR, page_number: int) -> list[dict]:
    """Extract the edits that apply to a specific page from the session history.

    Scans the session's action journal for BLOCK_EDITED actions on the given page.
    Returns a list of {old_text, new_text, block_id} dicts representing the
    SPECIFIC text fragments that changed (not the full block text).

    The key insight: the session stores the full block's old and new text,
    but for PDF patching we need only the CHANGED substring that can be
    found via page.search_for().
    """
    if not session or not session.actions:
        return []

    from src.api.session import ActionType

    # Collect net edits per block
    block_edits: dict[str, dict] = {}

    for action in session.actions:
        if action.action_type != ActionType.BLOCK_EDITED:
            continue
        if action.page != page_number:
            continue
        block_id = action.block_id
        old_text = action.data.get("old_text", "")
        new_text = action.data.get("new_text", "")
        # TOC edits store explicit patch targets
        patch_old = action.data.get("patch_old", "")
        patch_new = action.data.get("patch_new", "")

        if block_id not in block_edits:
            block_edits[block_id] = {
                "old_text": old_text, "new_text": new_text,
                "patch_old": patch_old, "patch_new": patch_new,
                "block_id": block_id,
            }
        else:
            block_edits[block_id]["new_text"] = new_text
            if patch_new:
                block_edits[block_id]["patch_new"] = patch_new

    # Convert full-block edits to specific text fragment diffs
    result = []
    for edit in block_edits.values():
        old_full = edit["old_text"]
        new_full = edit["new_text"]
        patch_old = edit.get("patch_old", "")
        patch_new = edit.get("patch_new", "")

        if old_full == new_full:
            continue

        # If explicit patch targets are provided (TOC edits), use them directly
        if patch_old and patch_new and patch_old != patch_new:
            result.append({
                "old_text": patch_old,
                "new_text": patch_new,
                "block_id": edit["block_id"],
            })
            continue

        # Short edits (< 200 chars) are already targeted — use directly
        # without fragmentation. This handles inline replacements
        # where the old_text IS the searchable text on the page.
        if len(old_full) < 200:
            result.append({
                "old_text": old_full,
                "new_text": new_full,
                "block_id": edit["block_id"],
            })
            continue

        # Find the specific changed fragment by diffing
        fragments = _find_changed_fragments(old_full, new_full)
        for old_frag, new_frag in fragments:
            result.append({
                "old_text": old_frag,
                "new_text": new_frag,
                "block_id": edit["block_id"],
            })

    return result


def _find_changed_fragments(old_text: str, new_text: str) -> list[tuple[str, str]]:
    """Find the specific text fragments that differ between old and new.

    Strategy: find the changed region, then search for progressively shorter
    substrings of the old text until we find something that `page.search_for`
    can locate (short enough to be on one line, long enough to be unique).
    """
    if old_text == new_text:
        return []

    # Find common prefix
    prefix_len = 0
    for i in range(min(len(old_text), len(new_text))):
        if old_text[i] == new_text[i]:
            prefix_len = i + 1
        else:
            break

    # Find common suffix
    suffix_len = 0
    for i in range(1, min(len(old_text), len(new_text)) - prefix_len + 1):
        if old_text[-i] == new_text[-i]:
            suffix_len = i
        else:
            break

    old_end = len(old_text) - suffix_len if suffix_len else len(old_text)
    new_end = len(new_text) - suffix_len if suffix_len else len(new_text)

    # The changed portions
    old_changed = old_text[prefix_len:old_end]
    new_changed = new_text[prefix_len:new_end]

    if not old_changed and not new_changed:
        return []

    # For a pure insertion (old_changed is empty), expand to include
    # the word on either side so we have something to search for
    if not old_changed:
        # Pure insertion — find the word before and after the insertion point
        # and use "word_before + word_after" as old, "word_before + insertion + word_after" as new
        before_end = prefix_len
        before_start = before_end
        while before_start > 0 and old_text[before_start - 1] not in " \n":
            before_start -= 1

        after_start = old_end
        after_end = after_start
        while after_end < len(old_text) and old_text[after_end] not in " \n":
            after_end += 1

        old_fragment = old_text[before_start:after_end]
        new_fragment = new_text[before_start:before_start + (prefix_len - before_start) + len(new_changed) + (after_end - old_end)]
        # Simpler: just do the same slice from new_text with adjusted end
        new_fragment = new_text[before_start:after_end + len(new_changed)]

        if old_fragment:
            return [(old_fragment, new_fragment)]
        return []

    # For a replacement or deletion, the old_changed text itself may be searchable
    # Expand to word boundaries
    start = prefix_len
    while start > 0 and old_text[start - 1] not in " \n":
        start -= 1
    end = old_end
    while end < len(old_text) and old_text[end] not in " \n":
        end += 1

    old_fragment = old_text[start:end]
    new_fragment = old_fragment[:prefix_len - start] + new_changed + old_fragment[old_end - start:]

    if old_fragment and old_fragment != new_fragment:
        return [(old_fragment, new_fragment)]

    return []


def _word_wrap(text: str, max_width: float, font: "fitz.Font | None", font_size: float) -> list[str]:
    """Word-wrap text to fit within max_width.

    Uses font metrics for precise measurement when available,
    falls back to character-count estimate otherwise.

    Returns a list of lines (strings) that each fit within max_width.
    """
    words = text.split()
    if not words:
        return [""]

    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word

        if font:
            test_width = font.text_length(test_line, fontsize=font_size)
        else:
            test_width = len(test_line) * font_size * 0.5

        if test_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines
