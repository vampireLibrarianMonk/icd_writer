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

        # Find the text on the page
        instances = page.search_for(old_text)
        if not instances:
            logger.warning(f"patch_page: '{old_text[:30]}...' not found on page {page_number}")
            continue

        rect = instances[0]

        # Get font info from the original span
        font_name, font_size, baseline_y, bold, italic, color = _extract_font_info(page, rect, old_text)

        # Determine alignment: table cell (centered) or paragraph (left-aligned)
        alignment = _detect_alignment(page, rect, old_text)

        if alignment == "center":
            # TABLE CELL: redact just the text rect, center the new text
            page.add_redact_annot(rect, fill=(1, 1, 1))
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
                    fallback_font = fitz.Font(fontname=builtin)
                    new_width = fallback_font.text_length(new_text, fontsize=font_size)
                    insert_x = original_center_x - new_width / 2
                except Exception:
                    insert_x = rect.x0
                page.insert_text(
                    fitz.Point(insert_x, baseline_y), new_text,
                    fontname=builtin, fontsize=font_size, color=color,
                )
        else:
            # PARAGRAPH TEXT: always redact the full line and reinsert
            # with the replacement applied. This preserves justification
            # and avoids overflow or gaps.
            _patch_paragraph_line(page, rect, old_text, new_text,
                                  font_name, font_size, bold, italic, color)

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

        instances = page.search_for(old_text)
        if not instances:
            logger.warning(f"patch_page_to_pdf: '{old_text[:30]}...' not found on page {page_number}")
            continue

        rect = instances[0]
        font_name, font_size, baseline_y, bold, italic, color = _extract_font_info(page, rect, old_text)

        # Determine alignment
        alignment = _detect_alignment(page, rect, old_text)

        if alignment == "center":
            # TABLE CELL: redact just the text rect, center the new text
            page.add_redact_annot(rect, fill=(1, 1, 1))
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
                    fallback_font = fitz.Font(fontname=builtin)
                    new_width = fallback_font.text_length(new_text, fontsize=font_size)
                    insert_x = original_center_x - new_width / 2
                except Exception:
                    insert_x = rect.x0
                page.insert_text(
                    fitz.Point(insert_x, baseline_y), new_text,
                    fontname=builtin, fontsize=font_size, color=color,
                )
        else:
            # PARAGRAPH TEXT: always redact the full line and reinsert
            _patch_paragraph_line(page, rect, old_text, new_text,
                                  font_name, font_size, bold, italic, color)

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
    """Patch paragraph text by reflowing the entire paragraph block.

    Finds the PDF block containing the old text, redacts it, and retypesets
    the full paragraph with the edit applied using insert_textbox with justify.
    This produces natural word-wrap and proper justification.
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
        if old_text in block_text:
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

    # Get block geometry
    block_bbox = target_block["bbox"]
    block_rect = fitz.Rect(block_bbox)

    # Apply the text replacement to the full block text
    new_block_text = target_block_text.replace(old_text, new_text, 1)

    # Compute line height from original
    num_lines = len(target_block["lines"])
    line_height = block_rect.height / num_lines if num_lines > 0 else font_size * 1.2

    # Get the first line's baseline for correct vertical positioning
    first_origin = target_block["lines"][0]["spans"][0].get("origin", (0, 0))
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

    # Word-wrap the new text to fit within content_width
    wrapped_lines = _word_wrap(new_block_text.strip(), content_width, measure_font, font_size)

    # Insert each line at the correct y-position (matching original line spacing)
    for i, line_text in enumerate(wrapped_lines):
        y = first_baseline_y + i * line_height
        page.insert_text(
            fitz.Point(block_rect.x0, y),
            line_text,
            fontname=builtin,
            fontsize=font_size,
            color=color,
        )


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

    # Collect centers of other spans in a vertical band (same column, ±50pt vertically)
    nearby_centers = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span["bbox"]
                span_center_y = (bbox[1] + bbox[3]) / 2
                span_center_x = (bbox[0] + bbox[2]) / 2
                # Same vertical region (±50pt) and similar horizontal zone (±80pt of our center)
                if (abs(span_center_y - target_y) < 50
                        and abs(span_center_x - target_center) < 80
                        and bbox != (rect.x0, rect.y0, rect.x1, rect.y1)):
                    nearby_centers.append(span_center_x)

    if not nearby_centers:
        return "left"

    # Count how many nearby spans share our center (within 5pt)
    matching = sum(1 for c in nearby_centers if abs(c - target_center) < 5)

    # If 2+ neighbors share the same center → table column (center-aligned)
    if matching >= 2:
        return "center"

    return "left"


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

        if block_id not in block_edits:
            block_edits[block_id] = {"old_text": old_text, "new_text": new_text, "block_id": block_id}
        else:
            block_edits[block_id]["new_text"] = new_text

    # Convert full-block edits to specific text fragment diffs
    result = []
    for edit in block_edits.values():
        old_full = edit["old_text"]
        new_full = edit["new_text"]
        if old_full == new_full:
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
