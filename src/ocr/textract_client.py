"""AWS Textract client for text and table extraction.

Extracts words with bounding boxes and confidence scores,
plus table structures from scanned page images.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import fitz
from PIL import Image as PILImage

from src.ocr.cost_tracker import CostTracker


@dataclass
class OcrWord:
    """A word detected by OCR with position and confidence."""

    text: str
    x0: float  # left edge in points
    y0: float  # top edge in points
    x1: float  # right edge in points
    y1: float  # bottom edge in points
    confidence: float  # 0-100
    source: str = "textract"  # which model produced this


@dataclass
class OcrLine:
    """A line of text (sequence of words on the same baseline)."""

    words: list[OcrWord] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        if not self.words:
            return (0, 0, 0, 0)
        return (
            min(w.x0 for w in self.words),
            min(w.y0 for w in self.words),
            max(w.x1 for w in self.words),
            max(w.y1 for w in self.words),
        )


@dataclass
class OcrTableCell:
    """A cell in a detected table."""

    text: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    confidence: float = 0.0
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)


@dataclass
class OcrTable:
    """A table detected on the page."""

    cells: list[OcrTableCell] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    rows: int = 0
    cols: int = 0


@dataclass
class TextractPageResult:
    """Result from Textract for a single page."""

    page_number: int
    words: list[OcrWord] = field(default_factory=list)
    lines: list[OcrLine] = field(default_factory=list)
    tables: list[OcrTable] = field(default_factory=list)
    page_width_pt: float = 612.0
    page_height_pt: float = 792.0


def extract_page_image(pdf_path: str, page_number: int, dpi: int = 300) -> bytes:
    """Extract a page as a PNG image for OCR processing."""
    doc = fitz.open(pdf_path)
    page = doc[page_number - 1]
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def run_textract_text(
    image_bytes: bytes,
    page_number: int,
    page_width_pt: float,
    page_height_pt: float,
    cost_tracker: CostTracker,
    region: str = "us-east-1",
) -> TextractPageResult:
    """Run Textract DetectDocumentText on a page image.

    Returns words and lines with positions converted to points.
    """
    import boto3

    client = boto3.client("textract", region_name=region)

    response = client.detect_document_text(Document={"Bytes": image_bytes})

    cost_tracker.record(
        service="textract",
        operation="detect_document_text",
        page=page_number,
    )

    result = TextractPageResult(
        page_number=page_number,
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
    )

    # Parse blocks
    lines_map: dict[str, OcrLine] = {}

    for block in response.get("Blocks", []):
        block_type = block.get("BlockType")
        geometry = block.get("Geometry", {})
        bbox = geometry.get("BoundingBox", {})
        confidence = block.get("Confidence", 0.0)

        # Convert normalized coordinates (0-1) to points
        x0 = bbox.get("Left", 0) * page_width_pt
        y0 = bbox.get("Top", 0) * page_height_pt
        w = bbox.get("Width", 0) * page_width_pt
        h = bbox.get("Height", 0) * page_height_pt
        x1 = x0 + w
        y1 = y0 + h

        if block_type == "WORD":
            word = OcrWord(
                text=block.get("Text", ""),
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                confidence=confidence,
                source="textract",
            )
            result.words.append(word)

        elif block_type == "LINE":
            line = OcrLine(confidence=confidence)
            lines_map[block.get("Id", "")] = line
            result.lines.append(line)

    # Associate words with lines
    for block in response.get("Blocks", []):
        if block.get("BlockType") == "LINE":
            line_id = block.get("Id", "")
            if line_id in lines_map:
                relationships = block.get("Relationships", [])
                for rel in relationships:
                    if rel.get("Type") == "CHILD":
                        for child_id in rel.get("Ids", []):
                            # Find the word block
                            for word_block in response.get("Blocks", []):
                                if word_block.get("Id") == child_id:
                                    bbox_w = word_block.get("Geometry", {}).get(
                                        "BoundingBox", {}
                                    )
                                    wx0 = bbox_w.get("Left", 0) * page_width_pt
                                    wy0 = bbox_w.get("Top", 0) * page_height_pt
                                    ww = bbox_w.get("Width", 0) * page_width_pt
                                    wh = bbox_w.get("Height", 0) * page_height_pt
                                    word = OcrWord(
                                        text=word_block.get("Text", ""),
                                        x0=wx0,
                                        y0=wy0,
                                        x1=wx0 + ww,
                                        y1=wy0 + wh,
                                        confidence=word_block.get("Confidence", 0.0),
                                        source="textract",
                                    )
                                    lines_map[line_id].words.append(word)

    return result


def run_textract_tables(
    image_bytes: bytes,
    page_number: int,
    page_width_pt: float,
    page_height_pt: float,
    cost_tracker: CostTracker,
    region: str = "us-east-1",
) -> list[OcrTable]:
    """Run Textract AnalyzeDocument for table extraction.

    More expensive than detect_document_text but provides table structure.
    Only call this when tables are detected on the page.
    """
    import boto3

    client = boto3.client("textract", region_name=region)

    response = client.analyze_document(
        Document={"Bytes": image_bytes},
        FeatureTypes=["TABLES"],
    )

    cost_tracker.record(
        service="textract",
        operation="analyze_document",
        page=page_number,
    )

    tables: list[OcrTable] = []

    # Parse table blocks
    cells_by_table: dict[str, list[OcrTableCell]] = {}
    table_bboxes: dict[str, tuple[float, float, float, float]] = {}

    for block in response.get("Blocks", []):
        block_type = block.get("BlockType")
        geometry = block.get("Geometry", {})
        bbox = geometry.get("BoundingBox", {})

        x0 = bbox.get("Left", 0) * page_width_pt
        y0 = bbox.get("Top", 0) * page_height_pt
        w = bbox.get("Width", 0) * page_width_pt
        h = bbox.get("Height", 0) * page_height_pt

        if block_type == "TABLE":
            table_id = block.get("Id", "")
            table_bboxes[table_id] = (x0, y0, x0 + w, y0 + h)
            cells_by_table[table_id] = []

        elif block_type == "CELL":
            # Find which table this cell belongs to
            cell = OcrTableCell(
                text=block.get("Text", ""),
                row=block.get("RowIndex", 0),
                col=block.get("ColumnIndex", 0),
                row_span=block.get("RowSpan", 1),
                col_span=block.get("ColumnSpan", 1),
                confidence=block.get("Confidence", 0.0),
                bbox=(x0, y0, x0 + w, y0 + h),
            )
            # Associate with parent table
            for rel in block.get("Relationships", []):
                if rel.get("Type") == "CHILD":
                    # Get cell text from child WORD blocks
                    cell_text_parts = []
                    for child_id in rel.get("Ids", []):
                        for b in response.get("Blocks", []):
                            if b.get("Id") == child_id and b.get("BlockType") == "WORD":
                                cell_text_parts.append(b.get("Text", ""))
                    cell.text = " ".join(cell_text_parts)

            # Find parent table via relationships of TABLE blocks
            for table_id, _ in table_bboxes.items():
                for b in response.get("Blocks", []):
                    if b.get("Id") == table_id:
                        for rel in b.get("Relationships", []):
                            if rel.get("Type") == "CHILD":
                                if block.get("Id") in rel.get("Ids", []):
                                    cells_by_table.setdefault(table_id, []).append(cell)

    for table_id, cells in cells_by_table.items():
        if cells:
            max_row = max(c.row for c in cells)
            max_col = max(c.col for c in cells)
            tables.append(
                OcrTable(
                    cells=cells,
                    bbox=table_bboxes.get(table_id, (0, 0, 0, 0)),
                    rows=max_row,
                    cols=max_col,
                )
            )

    return tables
