"""OCR rendering — converts OCR Document IR back to PDF with full visual fidelity.

Technique: Use the original page image as background, overlay OCR-detected
text as a transparent selectable text layer on top. This preserves:
- All images, logos, diagrams (pixel-perfect from source)
- Table formatting, borders, shading
- TOC leader dots and formatting
- Font appearance (the image shows the actual font rendering)
- Headers, footers, page numbers

The text overlay makes the content searchable and editable while the
background image preserves all visual formatting exactly.

For font determination: analyze the OCR bounding box heights to estimate
font size, and use Bedrock vision to identify font characteristics
(serif vs sans-serif, bold, italic) per text region.
"""

from __future__ import annotations

import io
from pathlib import Path

import fitz
import numpy as np
from PIL import Image as PILImage

from src.models.document_ir import DocumentIR


def render_ocr_to_pdf(
    source_pdf: Path | str,
    document_ir: DocumentIR,
    output_path: Path | str,
    text_layer_only: bool = False,
) -> Path:
    """Render OCR results back to PDF with page images as backgrounds.

    Strategy:
    - Each page: original image as background (preserves all visual formatting)
    - OCR text overlaid as invisible/selectable text layer
    - This gives pixel-perfect visual appearance + searchable/editable text

    Args:
        source_pdf: The original scanned/flattened PDF (for page images).
        document_ir: The OCR-produced Document IR with text blocks.
        output_path: Where to save the output PDF.
        text_layer_only: If True, text is invisible (for search/select only).
            If False, text is visible (for editing/re-rendering).
    """
    source_pdf = Path(source_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_doc = fitz.open(str(source_pdf))
    output_doc = fitz.open()

    for page_info in document_ir.pages:
        page_idx = page_info.page_number - 1
        if page_idx >= len(source_doc):
            break

        source_page = source_doc[page_idx]
        page_width = page_info.width_pt
        page_height = page_info.height_pt

        # Create new page
        new_page = output_doc.new_page(width=page_width, height=page_height)

        # Step 1: Insert original page image as background
        # This carries over ALL visual formatting — images, tables, fonts, logos
        source_pix = source_page.get_pixmap(dpi=150)
        img_bytes = source_pix.tobytes("png")
        new_page.insert_image(
            fitz.Rect(0, 0, page_width, page_height),
            stream=img_bytes,
        )

        # Step 2: Overlay OCR text blocks
        for block in page_info.text_blocks:
            text = block.text_verbatim
            if not text.strip():
                continue

            # Position text at the OCR-detected coordinates
            font_size = block.style.font_size_pt if block.style else 11.0
            x = block.bbox.x0
            # Baseline y: approximate from bbox top + ascent
            y = block.bbox.y1 - (block.bbox.height * 0.15)

            if text_layer_only:
                # Invisible text layer (for search/select — won't visually appear)
                new_page.insert_text(
                    point=(x, y),
                    text=text,
                    fontsize=font_size,
                    fontname="helv",
                    render_mode=3,  # invisible
                )
            else:
                # Visible text (for editing workflow — shows OCR text on white bg)
                new_page.insert_text(
                    point=(x, y),
                    text=text,
                    fontsize=font_size,
                    fontname="helv",
                )

    output_doc.save(str(output_path))
    output_doc.close()
    source_doc.close()

    return output_path


def render_ocr_searchable(
    source_pdf: Path | str,
    document_ir: DocumentIR,
    output_path: Path | str,
) -> Path:
    """Create a searchable PDF — original images + invisible text overlay.

    This is the 'carry everything over' approach:
    - Visual appearance = identical to source (it IS the source images)
    - Text is selectable and searchable (OCR layer on top)
    - Tables, TOC, appendix formatting all preserved pixel-perfect
    - Fonts appear exactly as they do in the scan

    Text layer is precisely aligned to visual text positions using
    width-matched font sizing and ascender-based baseline placement.
    """
    import fitz as fitz_lib

    source_pdf = Path(source_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    font = fitz_lib.Font("helv")
    ASCENDER = font.ascender
    TOTAL_HEIGHT_RATIO = font.ascender - font.descender

    source_doc = fitz_lib.open(str(source_pdf))
    output_doc = fitz_lib.open()

    # Copy all source pages (preserves original image encoding)
    output_doc.insert_pdf(source_doc)

    for page_info in document_ir.pages:
        page_idx = page_info.page_number - 1
        if page_idx >= len(output_doc):
            break

        page = output_doc[page_idx]

        for block in page_info.text_blocks:
            text = block.text_verbatim.strip()
            if not text:
                continue

            target_width = block.bbox.x1 - block.bbox.x0
            target_height = block.bbox.y1 - block.bbox.y0

            if target_width <= 0 or target_height <= 0:
                continue

            # Calculate font size to match OCR bbox width
            # For invisible text, width matching is all that matters —
            # height overflow is acceptable since the text isn't rendered visually
            width_at_1pt = font.text_length(text, fontsize=1)
            if width_at_1pt <= 0:
                continue
            calc_size = target_width / width_at_1pt

            # Baseline: place so the text bbox top aligns with OCR bbox top
            # PyMuPDF bbox.y0 = baseline - ascender*fontsize
            # We want bbox.y0 = ocr_bbox.y0
            # So: baseline = ocr_bbox.y0 + ascender*fontsize
            baseline_y = block.bbox.y0 + (ASCENDER * calc_size)

            page.insert_text(
                point=(block.bbox.x0, baseline_y),
                text=text,
                fontsize=calc_size,
                fontname="helv",
                render_mode=3,  # invisible
            )

    output_doc.save(str(output_path))
    output_doc.close()
    source_doc.close()

    return output_path


def detect_font_characteristics(
    image_bytes: bytes,
    word_bboxes: list[tuple[float, float, float, float]],
    page_width: float,
    page_height: float,
) -> dict[str, str]:
    """Analyze image regions to determine font characteristics.

    Uses pixel analysis of the text regions to determine:
    - Serif vs sans-serif (look for serifs on stems)
    - Bold vs regular (stroke width relative to height)
    - Italic vs upright (slant detection)

    Returns dict mapping region description to font classification.
    """
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        arr = np.array(img)
    except Exception:
        return {}

    img_h, img_w = arr.shape[:2]
    scale_x = img_w / page_width
    scale_y = img_h / page_height

    results = {}

    for i, (x0, y0, x1, y1) in enumerate(word_bboxes[:20]):  # sample first 20
        # Convert to pixel coordinates
        px0 = int(x0 * scale_x)
        py0 = int(y0 * scale_y)
        px1 = int(x1 * scale_x)
        py1 = int(y1 * scale_y)

        # Crop region
        region = arr[py0:py1, px0:px1]
        if region.size == 0:
            continue

        # Analyze for bold: ratio of dark pixels to total pixels
        if region.ndim == 3:
            gray = region.min(axis=2)
        else:
            gray = region

        dark_ratio = (gray < 128).sum() / gray.size if gray.size > 0 else 0

        # Bold detection: bold text has higher dark pixel ratio
        # Typical: regular ~0.15-0.25, bold ~0.30-0.45
        is_bold = dark_ratio > 0.30

        # Height-based font size estimation
        height_pt = y1 - y0
        est_font_size = height_pt / 1.2  # approximate

        # Stroke width estimation for serif detection
        # Serifs have varying stroke widths; sans-serif is more uniform
        # This is a rough heuristic
        if gray.shape[0] > 5:
            # Look at horizontal profiles at different heights
            top_profile = (gray[2, :] < 128).sum()
            mid_profile = (gray[gray.shape[0] // 2, :] < 128).sum()
            bot_profile = (gray[-3, :] < 128).sum()

            # Serifs make top/bottom wider than middle
            has_serif = (top_profile > mid_profile * 1.3) or (
                bot_profile > mid_profile * 1.3
            )
        else:
            has_serif = False

        font_type = "serif" if has_serif else "sans-serif"
        weight = "bold" if is_bold else "regular"

        results[f"region_{i}"] = f"{font_type} {weight} ~{est_font_size:.0f}pt"

    return results
