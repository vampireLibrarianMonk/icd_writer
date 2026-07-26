"""Page classifier logic.

Analyzes each page of a PDF to determine its content type(s):
native text, scanned, table-heavy, diagram-heavy, cover, etc.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from src.models.document_ir import PageClassification, PageClassificationType


def classify_pages(pdf_path: Path | str) -> list[PageClassification]:
    """Classify each page of a PDF by content type.

    Uses heuristics based on:
    - Presence/absence of native text
    - Number and area of images
    - Number of vector drawing operations
    - Text density and structure

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of PageClassification, one per page.
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))

    results: list[PageClassification] = []

    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_number = page_idx + 1

            classifications: list[PageClassificationType] = []
            native_text_available = False
            ocr_required = False

            # Extract text and analyze
            text = page.get_text("text")
            text_dict = page.get_text("dict")
            page_rect = page.rect
            page_area = page_rect.width * page_rect.height

            # Check for native text
            text_stripped = text.strip()
            has_text = len(text_stripped) > 10

            # Count images
            image_list = page.get_images(full=True)
            image_count = len(image_list)

            # Estimate image coverage
            image_area_ratio = _estimate_image_area_ratio(page, page_area)

            # Count drawing operations (vector graphics)
            drawings = page.get_drawings()
            drawing_count = len(drawings)

            # Determine rotation
            rotation = page.rotation

            # Classification logic
            if has_text:
                native_text_available = True
            else:
                ocr_required = True

            # Large image covering most of the page suggests scanned content
            if image_area_ratio > 0.7 and not has_text:
                classifications.append(PageClassificationType.SCANNED)
                ocr_required = True
            elif has_text:
                classifications.append(PageClassificationType.NATIVE_DIGITAL_TEXT)

            # Mixed content: both significant text and large images
            if has_text and image_area_ratio > 0.3:
                classifications.append(PageClassificationType.MIXED_CONTENT)

            # Table detection heuristic: many horizontal/vertical lines
            if drawing_count > 20 and _has_grid_pattern(drawings):
                classifications.append(PageClassificationType.TABLE_HEAVY)

            # Diagram detection: moderate drawings, fewer grid patterns
            if drawing_count > 10 and not _has_grid_pattern(drawings) and image_count < 3:
                classifications.append(PageClassificationType.DIAGRAM_HEAVY)

            # Image-only page
            if image_count > 0 and not has_text and image_area_ratio > 0.8:
                if PageClassificationType.SCANNED not in classifications:
                    classifications.append(PageClassificationType.IMAGE_ONLY)

            # Cover page heuristic: first page, large text, centered
            if page_number == 1:
                classifications.append(PageClassificationType.COVER)

            # TOC detection: "Table of Contents" or "CONTENTS" in text
            text_upper = text_stripped.upper()
            if "TABLE OF CONTENTS" in text_upper or "CONTENTS" == text_upper[:8]:
                classifications.append(PageClassificationType.TABLE_OF_CONTENTS)

            # Requirements detection: "shall", "must" keywords in density
            shall_count = text_stripped.lower().count("shall")
            if shall_count >= 3:
                classifications.append(PageClassificationType.REQUIREMENTS)

            # Revision history detection
            if "REVISION HISTORY" in text_upper or "CHANGE LOG" in text_upper:
                classifications.append(PageClassificationType.REVISION_HISTORY)

            # Ensure at least one classification
            if not classifications:
                if has_text:
                    classifications.append(PageClassificationType.NATIVE_DIGITAL_TEXT)
                else:
                    classifications.append(PageClassificationType.SCANNED)
                    ocr_required = True

            # Compute confidence based on clarity of signals
            confidence = _compute_confidence(
                has_text, image_area_ratio, drawing_count, classifications
            )

            results.append(
                PageClassification(
                    page_number=page_number,
                    classifications=classifications,
                    native_text_available=native_text_available,
                    ocr_required=ocr_required,
                    rotation_degrees=float(rotation),
                    confidence=confidence,
                )
            )
    finally:
        doc.close()

    return results


def _estimate_image_area_ratio(page: fitz.Page, page_area: float) -> float:
    """Estimate the fraction of the page covered by images."""
    if page_area == 0:
        return 0.0

    total_image_area = 0.0
    image_list = page.get_images(full=True)

    for img in image_list:
        # Get image bounding boxes from page content
        xref = img[0]
        try:
            rects = page.get_image_rects(xref)
            for rect in rects:
                total_image_area += rect.width * rect.height
        except Exception:
            continue

    return min(total_image_area / page_area, 1.0)


def _has_grid_pattern(drawings: list) -> bool:
    """Detect if drawings form a grid/table pattern (many orthogonal lines)."""
    if not drawings:
        return False

    horizontal_lines = 0
    vertical_lines = 0

    for drawing in drawings:
        items = drawing.get("items", [])
        for item in items:
            if item[0] == "l":  # line
                p1, p2 = item[1], item[2]
                dx = abs(p2.x - p1.x)
                dy = abs(p2.y - p1.y)
                # Horizontal line
                if dy < 2 and dx > 20:
                    horizontal_lines += 1
                # Vertical line
                elif dx < 2 and dy > 20:
                    vertical_lines += 1

    # A grid has multiple horizontal AND vertical lines
    return horizontal_lines >= 3 and vertical_lines >= 3


def _compute_confidence(
    has_text: bool,
    image_area_ratio: float,
    drawing_count: int,
    classifications: list[PageClassificationType],
) -> float:
    """Compute classification confidence score."""
    # Strong signals give higher confidence
    if len(classifications) == 1:
        if has_text and image_area_ratio < 0.1:
            return 0.95
        if not has_text and image_area_ratio > 0.8:
            return 0.90
    # Multiple classifications indicate ambiguity
    if len(classifications) >= 3:
        return 0.70
    return 0.85
