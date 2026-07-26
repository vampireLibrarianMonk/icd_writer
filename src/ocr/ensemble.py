"""Ensemble resolution — combines results from multiple OCR models.

Merges word detections from Textract and Rekognition, resolves conflicts,
estimates font sizes, and flags low-confidence regions for human review.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.ocr.textract_client import OcrWord, OcrLine, OcrTable


# Confidence threshold below which we flag for human review
CONFIDENCE_THRESHOLD_LOW = 80.0
CONFIDENCE_THRESHOLD_FLAG = 60.0


@dataclass
class ReviewFlag:
    """A region flagged for human review due to low confidence or disagreement."""

    page: int
    bbox: tuple[float, float, float, float]
    reason: str
    candidates: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class EnsembleResult:
    """Combined result from all OCR models for a single page."""

    page_number: int
    words: list[OcrWord] = field(default_factory=list)
    lines: list[OcrLine] = field(default_factory=list)
    tables: list[OcrTable] = field(default_factory=list)
    review_flags: list[ReviewFlag] = field(default_factory=list)
    page_width_pt: float = 612.0
    page_height_pt: float = 792.0
    estimated_font_size_pt: float = 11.0


def merge_detections(
    textract_words: list[OcrWord],
    rekognition_words: list[OcrWord],
    page_number: int,
    page_width_pt: float,
    page_height_pt: float,
) -> EnsembleResult:
    """Merge word detections from multiple models.

    Strategy:
    1. Textract is primary (better positional accuracy for document text)
    2. Rekognition fills gaps (diagram labels, rotated text)
    3. Where both detect the same region with different text, flag for review
    """
    result = EnsembleResult(
        page_number=page_number,
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
    )

    # Start with all Textract words
    merged_words = list(textract_words)

    # For each Rekognition word, check if it overlaps with a Textract detection
    for rek_word in rekognition_words:
        overlap_found = False
        for txt_word in textract_words:
            if _bbox_overlap_ratio(
                (rek_word.x0, rek_word.y0, rek_word.x1, rek_word.y1),
                (txt_word.x0, txt_word.y0, txt_word.x1, txt_word.y1),
            ) > 0.5:
                overlap_found = True
                # Check if they agree
                if rek_word.text.lower() != txt_word.text.lower():
                    # Disagreement — flag for review if both are confident
                    if rek_word.confidence > 70 and txt_word.confidence > 70:
                        result.review_flags.append(
                            ReviewFlag(
                                page=page_number,
                                bbox=(rek_word.x0, rek_word.y0, rek_word.x1, rek_word.y1),
                                reason="Model disagreement",
                                candidates=[txt_word.text, rek_word.text],
                                confidence=min(txt_word.confidence, rek_word.confidence),
                            )
                        )
                break

        if not overlap_found:
            # Rekognition found something Textract missed — add it
            merged_words.append(rek_word)

    # Flag low-confidence words
    for word in merged_words:
        if word.confidence < CONFIDENCE_THRESHOLD_FLAG:
            result.review_flags.append(
                ReviewFlag(
                    page=page_number,
                    bbox=(word.x0, word.y0, word.x1, word.y1),
                    reason=f"Low confidence ({word.confidence:.0f}%)",
                    candidates=[word.text],
                    confidence=word.confidence,
                )
            )

    result.words = merged_words
    return result


def estimate_font_size(words: list[OcrWord]) -> float:
    """Estimate the dominant font size from word bounding box heights.

    Uses the median height of word bounding boxes as a proxy for font size.
    The relationship is approximately: font_size_pt ≈ bbox_height * 0.75
    (accounting for ascenders/descenders not filling the full bbox).
    """
    if not words:
        return 11.0

    heights = [w.y1 - w.y0 for w in words if (w.y1 - w.y0) > 3]
    if not heights:
        return 11.0

    # Sort and take median
    heights.sort()
    median_height = heights[len(heights) // 2]

    # Approximate font size from bbox height
    # Typical ratio: bbox_height ≈ 1.2 * font_size (due to line spacing)
    estimated_size = median_height / 1.2

    # Round to common font sizes
    common_sizes = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24]
    closest = min(common_sizes, key=lambda s: abs(s - estimated_size))

    return float(closest)


def _bbox_overlap_ratio(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    """Compute overlap ratio between two bounding boxes."""
    x_overlap = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    y_overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    overlap_area = x_overlap * y_overlap

    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    min_area = min(area_a, area_b)

    if min_area <= 0:
        return 0.0
    return overlap_area / min_area
