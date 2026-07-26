"""OCR pipeline orchestrator.

Coordinates the multi-model OCR pipeline for scanned/flattened PDFs:
1. Extract page images
2. Classify each page (Bedrock vision)
3. Run Textract on all pages (primary OCR)
4. Run Rekognition on diagram regions (secondary)
5. Merge results with ensemble resolution
6. Disambiguate conflicts (Bedrock Claude)
7. Estimate font sizes
8. Produce Document IR (same schema as native pipeline)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import fitz

from src.models.common import BoundingBox, DocumentMetadata, Provenance
from src.models.document_ir import (
    DocumentIR,
    PageClassification,
    PageClassificationType,
    PageInfo,
    TextBlock,
    TextStyle,
)
from src.ocr.bedrock_client import classify_page, disambiguate_text
from src.ocr.cost_tracker import CostTracker
from src.ocr.ensemble import (
    EnsembleResult,
    ReviewFlag,
    estimate_font_size,
    merge_detections,
)
from src.ocr.rekognition_client import run_rekognition_text
from src.ocr.textract_client import (
    TextractPageResult,
    extract_page_image,
    run_textract_tables,
    run_textract_text,
)
from src.ingestion.pdf_reader import compute_sha256


def ocr_ingest(
    pdf_path: Path | str,
    region: str = "us-east-1",
    use_rekognition: bool = True,
    use_bedrock_classify: bool = True,
    use_bedrock_disambiguate: bool = True,
    dpi: int = 300,
) -> tuple[DocumentIR, CostTracker, list[ReviewFlag]]:
    """Run the full OCR pipeline on a scanned/flattened PDF.

    Args:
        pdf_path: Path to the image-only PDF.
        region: AWS region for API calls.
        use_rekognition: Whether to run Rekognition as secondary detector.
        use_bedrock_classify: Whether to use Bedrock for page classification.
        use_bedrock_disambiguate: Whether to use Claude for conflict resolution.
        dpi: Resolution for page image extraction.

    Returns:
        Tuple of (DocumentIR, CostTracker, list of ReviewFlags).
    """
    pdf_path = Path(pdf_path)
    cost_tracker = CostTracker()
    all_review_flags: list[ReviewFlag] = []

    # Open document for metadata
    doc = fitz.open(str(pdf_path))
    num_pages = len(doc)
    sha256 = compute_sha256(pdf_path)

    metadata = DocumentMetadata(
        filename=pdf_path.name,
        sha256=sha256,
        page_count=num_pages,
        title=doc.metadata.get("title") or None,
        author=doc.metadata.get("author") or None,
        file_size_bytes=pdf_path.stat().st_size,
    )

    pages: list[PageInfo] = []

    for page_idx in range(num_pages):
        page_number = page_idx + 1
        page = doc[page_idx]
        page_width = page.rect.width
        page_height = page.rect.height

        # Step 1: Extract page image
        image_bytes = extract_page_image(str(pdf_path), page_number, dpi=dpi)

        # Step 2: Classify page (optional, uses Bedrock)
        page_type = "text"
        has_tables = False
        has_diagrams = False
        diagram_regions: list[tuple[float, float, float, float]] = []

        if use_bedrock_classify:
            classification = classify_page(
                image_bytes, page_number, page_width, page_height,
                cost_tracker, region=region,
            )
            page_type = classification.page_type
            has_tables = classification.has_tables
            has_diagrams = classification.has_diagrams
            diagram_regions = classification.diagram_regions

        # Step 3: Run Textract (primary OCR)
        textract_result = run_textract_text(
            image_bytes, page_number, page_width, page_height,
            cost_tracker, region=region,
        )

        # Step 4: Run Textract table analysis if tables detected
        tables = []
        if has_tables:
            tables = run_textract_tables(
                image_bytes, page_number, page_width, page_height,
                cost_tracker, region=region,
            )

        # Step 5: Run Rekognition on diagram regions (optional)
        rekognition_words = []
        if use_rekognition and has_diagrams:
            rekognition_words = run_rekognition_text(
                image_bytes, page_number, page_width, page_height,
                cost_tracker, region=region,
            )

        # Step 6: Ensemble merge
        ensemble = merge_detections(
            textract_result.words,
            rekognition_words,
            page_number,
            page_width,
            page_height,
        )

        # Step 7: Disambiguate conflicts (optional, uses Claude)
        if use_bedrock_disambiguate:
            for flag in ensemble.review_flags:
                if flag.reason == "Model disagreement" and len(flag.candidates) > 1:
                    try:
                        best_text, conf = disambiguate_text(
                            image_bytes,
                            flag.candidates,
                            flag.bbox,
                            page_number,
                            cost_tracker,
                            region=region,
                        )
                        # Update the word with the resolved text
                        for word in ensemble.words:
                            if (
                                abs(word.x0 - flag.bbox[0]) < 2
                                and abs(word.y0 - flag.bbox[1]) < 2
                            ):
                                word.text = best_text
                                word.confidence = conf * 100
                                break
                    except Exception as e:
                        # If disambiguation fails, keep the Textract result
                        flag.reason = f"Model disagreement (disambiguation failed: {e})"

        all_review_flags.extend(ensemble.review_flags)

        # Step 8: Estimate font size
        font_size = estimate_font_size(ensemble.words)

        # Step 9: Convert to Document IR text blocks
        text_blocks = _words_to_text_blocks(
            ensemble.words, page_number, font_size
        )

        # Build page classification
        classifications = [PageClassificationType.NATIVE_DIGITAL_TEXT]
        if page_type == "table" or has_tables:
            classifications.append(PageClassificationType.TABLE_HEAVY)
        if page_type == "diagram" or has_diagrams:
            classifications.append(PageClassificationType.DIAGRAM_HEAVY)

        page_classification = PageClassification(
            page_number=page_number,
            classifications=classifications,
            native_text_available=False,
            ocr_required=True,
            confidence=0.85,
        )

        pages.append(
            PageInfo(
                page_number=page_number,
                width_pt=page_width,
                height_pt=page_height,
                classification=page_classification,
                text_blocks=text_blocks,
            )
        )

    doc.close()

    # Build provenance
    provenance = Provenance(
        source_document=metadata.filename,
        source_sha256=sha256,
        page=0,
        extraction_engine="ocr_ensemble",
        extraction_engine_version="textract+rekognition+bedrock",
        extraction_confidence=0.0,
        extraction_timestamp=datetime.now(timezone.utc),
    )

    document_ir = DocumentIR(
        metadata=metadata,
        pages=pages,
        provenance=provenance,
    )

    return document_ir, cost_tracker, all_review_flags


def _words_to_text_blocks(
    words: list, page_number: int, font_size: float
) -> list[TextBlock]:
    """Convert OCR words into TextBlock objects grouped by line.

    Groups words into lines based on vertical proximity,
    then creates a TextBlock for each line.
    """
    if not words:
        return []

    # Sort words by y-position then x-position
    sorted_words = sorted(words, key=lambda w: (w.y0, w.x0))

    # Group into lines (words within font_size * 0.5 of each other vertically)
    lines: list[list] = []
    current_line: list = [sorted_words[0]]
    line_y = sorted_words[0].y0

    for word in sorted_words[1:]:
        if abs(word.y0 - line_y) < font_size * 0.5:
            current_line.append(word)
        else:
            lines.append(current_line)
            current_line = [word]
            line_y = word.y0

    if current_line:
        lines.append(current_line)

    # Convert each line to a TextBlock
    text_blocks = []
    for block_idx, line_words in enumerate(lines):
        # Sort words in line by x position
        line_words.sort(key=lambda w: w.x0)

        text = " ".join(w.text for w in line_words)
        if not text.strip():
            continue

        x0 = min(w.x0 for w in line_words)
        y0 = min(w.y0 for w in line_words)
        x1 = max(w.x1 for w in line_words)
        y1 = max(w.y1 for w in line_words)

        avg_confidence = sum(w.confidence for w in line_words) / len(line_words)

        block = TextBlock(
            id=f"block-p{page_number:02d}-b{block_idx:02d}",
            block_type="paragraph",
            page=page_number,
            bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
            text_verbatim=text,
            reading_order=block_idx,
            style=TextStyle(font_size_pt=font_size),
            confidence=avg_confidence / 100.0,
            is_ocr=True,
        )
        text_blocks.append(block)

    return text_blocks
