"""Unit tests for the HTML/CSS renderer module.

Tests:
- render_page_to_html: produces valid HTML with absolute positioning
- _render_text: TextElement → positioned spans (word-level and fallback)
- _render_line: horizontal, vertical, and diagonal lines
- _render_rect: rectangles with fill/stroke
- _render_path: SVG path elements
- _render_image: base64-encoded images
- _map_font_family: PDF font name → CSS font-family mapping
- _split_words: word boundary detection
"""

import base64
import re

import pytest

from src.models.common import BoundingBox
from src.rendering.elements import (
    ImageElement,
    LineElement,
    PathElement,
    RectElement,
    TextElement,
)
from src.rendering.renderer import (
    _map_font_family,
    _split_words,
    render_page_to_html,
)


# ─── Fixtures ──────────────────────────────────────────────────────────


def _text_elem(
    text: str = "Hello",
    x0: float = 72.0,
    y0: float = 100.0,
    x1: float = 200.0,
    y1: float = 112.0,
    font_name: str = "Helvetica",
    font_size: float = 10.0,
    bold: bool = False,
    italic: bool = False,
    color: str = "#000000",
    char_positions: list[float] | None = None,
) -> TextElement:
    return TextElement(
        text=text,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        font_name=font_name,
        font_size_pt=font_size,
        bold=bold,
        italic=italic,
        color=color,
        char_positions=char_positions,
    )


def _line_elem(
    x1: float = 72.0,
    y1: float = 100.0,
    x2: float = 540.0,
    y2: float = 100.0,
    color: str = "#000000",
    width: float = 1.0,
) -> LineElement:
    return LineElement(x1=x1, y1=y1, x2=x2, y2=y2, color=color, width=width)


def _rect_elem(
    x0: float = 72.0,
    y0: float = 100.0,
    x1: float = 200.0,
    y1: float = 150.0,
    fill_color: str | None = "#ffffff",
    stroke_color: str | None = "#000000",
    stroke_width: float = 1.0,
) -> RectElement:
    return RectElement(
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        fill_color=fill_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
    )


def _path_elem(
    svg_path: str = "M 72 100 L 200 100 L 200 150 Z",
    fill_color: str | None = None,
    stroke_color: str | None = "#000000",
    stroke_width: float = 1.0,
) -> PathElement:
    return PathElement(
        svg_path=svg_path,
        fill_color=fill_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
    )


def _image_elem(
    x0: float = 72.0,
    y0: float = 100.0,
    x1: float = 200.0,
    y1: float = 200.0,
    mime_type: str = "image/png",
) -> ImageElement:
    # 1x1 pixel transparent PNG
    pixel_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return ImageElement(
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        image_data=pixel_data,
        mime_type=mime_type,
    )


# ─── render_page_to_html: structure ───────────────────────────────────


class TestRenderPageToHtmlStructure:
    """Test that render_page_to_html produces valid HTML structure."""

    def test_produces_valid_html_document(self):
        """Output is a complete HTML document with doctype, head, body."""
        html = render_page_to_html(612.0, 792.0, [])
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_page_size_in_css(self):
        """@page CSS rule contains the page dimensions."""
        html = render_page_to_html(612.0, 792.0, [])
        assert "612" in html
        assert "792" in html

    def test_body_dimensions_set(self):
        """Body has width and height set to page dimensions."""
        html = render_page_to_html(595.0, 842.0, [])
        assert "595" in html
        assert "842" in html

    def test_page_div_present(self):
        """A .page div wraps all elements."""
        html = render_page_to_html(612.0, 792.0, [])
        assert 'class="page"' in html

    def test_empty_elements_produces_empty_page(self):
        """No elements → HTML with empty page div (no spans/divs inside)."""
        html = render_page_to_html(612.0, 792.0, [])
        # Should not have any span or img elements
        assert "<span" not in html
        assert "<img" not in html


# ─── render_page_to_html: text rendering ──────────────────────────────


class TestRenderText:
    """Test text element rendering."""

    def test_text_element_produces_span(self):
        """A TextElement renders as a positioned <span>."""
        elem = _text_elem("Hello world")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<span" in html
        assert "Hello" in html

    def test_text_positioning(self):
        """Text span has correct left and top positioning."""
        elem = _text_elem("Test", x0=100.0, y0=200.0)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "left:100" in html.replace(" ", "")
        assert "top:200" in html.replace(" ", "")

    def test_font_family_applied(self):
        """Font family from TextElement is applied in CSS."""
        elem = _text_elem("Arial text", font_name="Arial")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "Arial" in html

    def test_font_size_applied(self):
        """Font size is applied in the style."""
        elem = _text_elem("Big text", font_size=18.0)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "18" in html

    def test_bold_weight(self):
        """Bold text gets font-weight: bold."""
        elem = _text_elem("Bold", bold=True)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "font-weight:bold" in html.replace(" ", "")

    def test_italic_style(self):
        """Italic text gets font-style: italic."""
        elem = _text_elem("Italic", italic=True)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "font-style:italic" in html.replace(" ", "")

    def test_color_applied(self):
        """Text color is applied."""
        elem = _text_elem("Red text", color="#ff0000")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "#ff0000" in html

    def test_html_entities_escaped(self):
        """Special HTML characters are properly escaped."""
        elem = _text_elem("a < b & c > d")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "&lt;" in html
        assert "&amp;" in html
        assert "&gt;" in html
        # Raw < and > should not appear in text content
        # (they appear in HTML tags, but not unescaped in text)

    def test_empty_text_not_rendered(self):
        """A TextElement with empty/whitespace text is not rendered."""
        elem = _text_elem("   ")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<span" not in html

    def test_word_level_positioning_with_char_positions(self):
        """When char_positions provided, text is split into per-word spans."""
        # "Hello world" → 2 words, each gets its own span
        elem = _text_elem(
            "Hello world",
            x0=72.0, y0=100.0, x1=200.0, y1=112.0,
            char_positions=[72.0, 77.0, 82.0, 87.0, 92.0, 97.0, 102.0, 107.0, 112.0, 117.0, 122.0],
        )
        html = render_page_to_html(612.0, 792.0, [elem])
        # Should have at least 2 spans (one per word)
        span_count = html.count("<span")
        assert span_count >= 2

    def test_fallback_rendering_without_char_positions(self):
        """Without char_positions, renders as single full-width span."""
        elem = _text_elem("Single span text", char_positions=None)
        html = render_page_to_html(612.0, 792.0, [elem])
        span_count = html.count("<span")
        assert span_count == 1

    def test_whitespace_pre_applied(self):
        """Text elements use white-space:pre to preserve spacing."""
        elem = _text_elem("Spaced text")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "white-space:pre" in html.replace(" ", "")

    def test_overflow_hidden_applied(self):
        """Text spans use overflow:hidden to clip to block width."""
        elem = _text_elem("Clipped text")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "overflow:hidden" in html.replace(" ", "")


# ─── render_page_to_html: line rendering ──────────────────────────────


class TestRenderLine:
    """Test line element rendering."""

    def test_horizontal_line_as_div(self):
        """A horizontal line (dy≈0) renders as a positioned div."""
        elem = _line_elem(x1=72, y1=100, x2=540, y2=100)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<div" in html
        assert "background-color" in html

    def test_vertical_line_as_div(self):
        """A vertical line (dx≈0) renders as a positioned div."""
        elem = _line_elem(x1=300, y1=72, x2=300, y2=720)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<div" in html

    def test_diagonal_line_as_svg(self):
        """A diagonal line renders as an SVG element."""
        elem = _line_elem(x1=72, y1=100, x2=540, y2=500)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<svg" in html
        assert "<line" in html

    def test_line_color_applied(self):
        """Line color is applied."""
        elem = _line_elem(color="#ff0000")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "#ff0000" in html

    def test_horizontal_line_dimensions(self):
        """Horizontal line div has correct width."""
        elem = _line_elem(x1=100, y1=200, x2=400, y2=200)
        html = render_page_to_html(612.0, 792.0, [elem])
        # Width should be 300pt
        assert "300" in html


# ─── render_page_to_html: rectangle rendering ─────────────────────────


class TestRenderRect:
    """Test rectangle element rendering."""

    def test_rect_rendered_as_div(self):
        """A RectElement renders as a positioned div."""
        elem = _rect_elem()
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<div" in html

    def test_rect_fill_color(self):
        """Rectangle fill color becomes background-color."""
        elem = _rect_elem(fill_color="#cccccc")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "#cccccc" in html
        assert "background-color" in html

    def test_rect_stroke_color(self):
        """Rectangle stroke becomes CSS border."""
        elem = _rect_elem(stroke_color="#0000ff")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "#0000ff" in html
        assert "border" in html

    def test_rect_positioning(self):
        """Rectangle uses bbox for position and size."""
        elem = _rect_elem(x0=100, y0=200, x1=300, y1=400)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "left:100" in html.replace(" ", "")
        assert "top:200" in html.replace(" ", "")
        assert "width:200" in html.replace(" ", "")
        assert "height:200" in html.replace(" ", "")


# ─── render_page_to_html: path rendering ──────────────────────────────


class TestRenderPath:
    """Test SVG path element rendering."""

    def test_path_rendered_as_svg(self):
        """A PathElement renders as an SVG."""
        elem = _path_elem("M 10 10 L 100 100")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<svg" in html
        assert "<path" in html

    def test_path_d_attribute(self):
        """The SVG path d attribute contains the path data."""
        path_data = "M 72 100 L 200 100 L 200 150 Z"
        elem = _path_elem(path_data)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert path_data in html

    def test_path_fill_color(self):
        """Path fill color is applied."""
        elem = _path_elem(fill_color="#ff9900")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "#ff9900" in html

    def test_path_stroke_color(self):
        """Path stroke color is applied."""
        elem = _path_elem(stroke_color="#003366")
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "#003366" in html

    def test_path_no_fill_uses_none(self):
        """Path without fill uses fill='none'."""
        elem = _path_elem(fill_color=None)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert 'fill="none"' in html

    def test_path_viewbox_matches_page(self):
        """SVG viewBox matches page dimensions."""
        elem = _path_elem()
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "0 0 612" in html
        assert "792" in html


# ─── render_page_to_html: image rendering ─────────────────────────────


class TestRenderImage:
    """Test image element rendering."""

    def test_image_rendered_as_img_tag(self):
        """An ImageElement renders as an <img> tag."""
        elem = _image_elem()
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "<img" in html

    def test_image_base64_encoded(self):
        """Image data is base64 encoded in src attribute."""
        elem = _image_elem()
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "base64" in html
        assert "data:image/png;base64," in html

    def test_image_positioning(self):
        """Image is absolutely positioned at bbox coordinates."""
        elem = _image_elem(x0=150, y0=250, x1=350, y1=450)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "left:150" in html.replace(" ", "")
        assert "top:250" in html.replace(" ", "")

    def test_image_dimensions(self):
        """Image has width and height from bbox."""
        elem = _image_elem(x0=100, y0=100, x1=300, y1=250)
        html = render_page_to_html(612.0, 792.0, [elem])
        assert "width:200" in html.replace(" ", "")
        assert "height:150" in html.replace(" ", "")


# ─── Element ordering ─────────────────────────────────────────────────


class TestElementOrdering:
    """Test that elements render in correct z-order."""

    def test_elements_render_in_input_order(self):
        """Elements appear in the HTML in the same order as the input list."""
        elements = [
            _line_elem(x1=72, y1=50, x2=540, y2=50),
            _rect_elem(x0=72, y0=100, x1=540, y1=200),
            _text_elem("Text on top", x0=72, y0=150),
        ]
        html = render_page_to_html(612.0, 792.0, elements)

        # Find positions of key markers
        line_pos = html.find("background-color:#000000")
        rect_pos = html.find("background-color:#ffffff")
        text_pos = html.find("Text on top")

        assert line_pos < rect_pos < text_pos

    def test_mixed_element_types(self):
        """All element types can be rendered together without errors."""
        elements = [
            _line_elem(),
            _rect_elem(),
            _path_elem(),
            _image_elem(),
            _text_elem("Mixed page"),
        ]
        html = render_page_to_html(612.0, 792.0, elements)
        assert "<svg" in html
        assert "<img" in html
        assert "<span" in html
        assert "Mixed page" in html


# ─── _map_font_family ─────────────────────────────────────────────────


class TestMapFontFamily:
    """Test PDF font name to CSS font-family mapping."""

    def test_arial(self):
        result = _map_font_family("Arial")
        assert "Arial" in result
        assert "sans-serif" in result

    def test_arial_bold(self):
        result = _map_font_family("Arial,Bold")
        assert "Arial" in result

    def test_helvetica(self):
        result = _map_font_family("Helvetica")
        assert "Helvetica" in result
        assert "sans-serif" in result

    def test_times_new_roman(self):
        result = _map_font_family("TimesNewRomanPSMT")
        assert "Times" in result
        assert "serif" in result

    def test_courier(self):
        result = _map_font_family("Courier")
        assert "Courier" in result
        assert "monospace" in result

    def test_calibri(self):
        result = _map_font_family("Calibri")
        assert "Calibri" in result or "Carlito" in result

    def test_cambria(self):
        result = _map_font_family("Cambria")
        assert "Cambria" in result or "Caladea" in result

    def test_unknown_font_quoted(self):
        """Unknown fonts are wrapped in quotes with sans-serif fallback."""
        result = _map_font_family("MyCustomFont")
        assert "MyCustomFont" in result
        assert "sans-serif" in result

    def test_symbol(self):
        result = _map_font_family("Symbol")
        assert "Symbol" in result


# ─── _split_words ─────────────────────────────────────────────────────


class TestSplitWords:
    """Test word boundary splitting."""

    def test_simple_words(self):
        result = _split_words("Hello world")
        assert result == [(0, 5), (6, 11)]

    def test_single_word(self):
        result = _split_words("Hello")
        assert result == [(0, 5)]

    def test_multiple_spaces(self):
        """Multiple spaces between words are handled."""
        result = _split_words("A  B")
        # "A" at 0-1, "B" at 3-4 (double space skips index 2)
        assert (0, 1) in result
        assert (3, 4) in result

    def test_empty_string(self):
        result = _split_words("")
        assert result == []

    def test_leading_space(self):
        result = _split_words(" Hello")
        assert result == [(1, 6)]

    def test_trailing_space(self):
        result = _split_words("Hello ")
        assert result == [(0, 5)]

    def test_many_words(self):
        result = _split_words("The quick brown fox jumps")
        assert len(result) == 5
        assert result[0] == (0, 3)  # "The"
        assert result[4] == (20, 25)  # "jumps"


# ─── Stroke width scaling ─────────────────────────────────────────────


class TestStrokeWidthScaling:
    """Test that stroke widths are scaled for visual fidelity."""

    def test_line_width_scaled(self):
        """Line widths in output are scaled (0.5x factor)."""
        elem = _line_elem(x1=72, y1=100, x2=540, y2=100, width=2.0)
        html = render_page_to_html(612.0, 792.0, [elem])
        # Rendered width should be 2.0 * 0.5 = 1.0pt
        # The div height represents the line thickness
        assert "height:1" in html.replace(" ", "") or "height:1.0" in html.replace(" ", "")

    def test_rect_border_width_scaled(self):
        """Rect border widths are scaled."""
        elem = _rect_elem(stroke_width=4.0)
        html = render_page_to_html(612.0, 792.0, [elem])
        # 4.0 * 0.5 = 2.0pt border
        assert "2" in html  # Should contain the scaled width
