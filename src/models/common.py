"""Common types shared across Document IR and ICD IR."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Bounding box coordinates in points (PDF coordinate system)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height


class SourceReference(BaseModel):
    """Reference back to the original source location."""

    page: int
    block_id: Optional[str] = None
    bbox: Optional[BoundingBox] = None


class Provenance(BaseModel):
    """Full provenance record for any extracted element."""

    source_document: str
    source_sha256: str
    page: int
    bbox: Optional[BoundingBox] = None
    extraction_engine: str
    extraction_engine_version: str
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    extraction_timestamp: datetime
    reviewer: Optional[str] = None
    human_verified: bool = False


class ExtractionConfidence(str, Enum):
    """Confidence level classification."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


class DocumentMetadata(BaseModel):
    """Top-level metadata for a source document."""

    filename: str
    sha256: str
    page_count: int
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    creation_date: Optional[datetime] = None
    modification_date: Optional[datetime] = None
    file_size_bytes: int = 0
