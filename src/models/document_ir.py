"""Document Intermediate Representation (Document IR).

Represents the physical layout of the original document: pages, blocks,
coordinates, fonts, tables, images, and reading order.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.models.common import BoundingBox, DocumentMetadata, Provenance


class PageClassificationType(str, Enum):
    """Classification types for PDF pages."""

    NATIVE_DIGITAL_TEXT = "native_digital_text"
    SCANNED = "scanned"
    MIXED_CONTENT = "mixed_content"
    TABLE_HEAVY = "table_heavy"
    DIAGRAM_HEAVY = "diagram_heavy"
    DRAWING_HEAVY = "drawing_heavy"
    IMAGE_ONLY = "image_only"
    COVER = "cover"
    REVISION_HISTORY = "revision_history"
    TABLE_OF_CONTENTS = "table_of_contents"
    REQUIREMENTS = "requirements"
    APPENDIX = "appendix"


class PageClassification(BaseModel):
    """Classification result for a single page."""

    page_number: int
    classifications: list[PageClassificationType]
    native_text_available: bool = True
    ocr_required: bool = False
    rotation_degrees: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class TextStyle(BaseModel):
    """Typography information for a text element."""

    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[str] = None  # hex color


class TextBlock(BaseModel):
    """A block of text with position and style information."""

    id: str
    block_type: str = "paragraph"  # paragraph, heading, caption, footer, header, list_item
    page: int
    bbox: BoundingBox
    text_verbatim: str
    text_normalized: Optional[str] = None
    reading_order: int = 0
    style: Optional[TextStyle] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    is_ocr: bool = False


class TableCell(BaseModel):
    """A single cell in a table."""

    value: str
    row_span: int = 1
    col_span: int = 1
    bbox: Optional[BoundingBox] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class TableColumn(BaseModel):
    """Definition of a table column."""

    id: str
    title: str


class TableRow(BaseModel):
    """A row in the table, mapping column IDs to cells."""

    id: str
    cells: dict[str, TableCell]


class TableBlock(BaseModel):
    """A table extracted from the document."""

    id: str
    caption: Optional[str] = None
    page: int
    bbox: BoundingBox
    columns: list[TableColumn]
    rows: list[TableRow]
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    spans_pages: bool = False
    continuation_of: Optional[str] = None  # ID of table this continues


class FigureBlock(BaseModel):
    """A figure or image extracted from the document."""

    id: str
    page: int
    bbox: BoundingBox
    caption: Optional[str] = None
    figure_type: str = "raster"  # raster, vector, diagram, chart
    image_path: Optional[str] = None  # path to extracted image file
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class PageInfo(BaseModel):
    """Complete information for a single page."""

    page_number: int
    width_pt: float
    height_pt: float
    classification: PageClassification
    text_blocks: list[TextBlock] = Field(default_factory=list)
    tables: list[TableBlock] = Field(default_factory=list)
    figures: list[FigureBlock] = Field(default_factory=list)


class DocumentIR(BaseModel):
    """Document Intermediate Representation.

    The physical document model: pages, layout, text, tables, figures,
    coordinates, fonts, and reading order. This preserves the original
    document structure with full provenance.
    """

    metadata: DocumentMetadata
    pages: list[PageInfo] = Field(default_factory=list)
    provenance: Optional[Provenance] = None

    @property
    def page_count(self) -> int:
        return len(self.pages)
