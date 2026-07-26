"""Renderable page element models.

These represent the visual elements extracted from a PDF page,
ready to be rendered back to HTML/CSS.
"""

from __future__ import annotations

from src.models.common import BoundingBox


class PageElement:
    """Base class for renderable page elements."""

    pass


class TextElement(PageElement):
    """A text span to render at exact coordinates."""

    def __init__(
        self,
        text: str,
        bbox: BoundingBox,
        font_name: str,
        font_size_pt: float,
        bold: bool = False,
        italic: bool = False,
        color: str = "#000000",
        char_positions: list[float] | None = None,
        baseline_y: float | None = None,
        ascender: float = 0.0,
        descender: float = 0.0,
    ):
        self.text = text
        self.bbox = bbox
        self.font_name = font_name
        self.font_size_pt = font_size_pt
        self.bold = bold
        self.italic = italic
        self.color = color
        self.char_positions = char_positions
        self.baseline_y = baseline_y
        self.ascender = ascender
        self.descender = descender


class ImageElement(PageElement):
    """An image to render at exact coordinates."""

    def __init__(self, bbox: BoundingBox, image_data: bytes, mime_type: str = "image/png"):
        self.bbox = bbox
        self.image_data = image_data
        self.mime_type = mime_type


class LineElement(PageElement):
    """A drawn line."""

    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "#000000",
        width: float = 1.0,
    ):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color
        self.width = width


class RectElement(PageElement):
    """A rectangle (filled or stroked)."""

    def __init__(
        self,
        bbox: BoundingBox,
        fill_color: str | None = None,
        stroke_color: str | None = None,
        stroke_width: float = 1.0,
    ):
        self.bbox = bbox
        self.fill_color = fill_color
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width


class PathElement(PageElement):
    """An SVG path (supports lines, curves, and complex shapes)."""

    def __init__(
        self,
        svg_path: str,
        fill_color: str | None = None,
        stroke_color: str | None = None,
        stroke_width: float = 1.0,
    ):
        self.svg_path = svg_path
        self.fill_color = fill_color
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width
