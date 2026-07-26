"""HTML/CSS rendering and PDF generation.

Converts PageElements into HTML with absolute positioning,
then renders to PDF via WeasyPrint.
"""

from __future__ import annotations

import base64
from pathlib import Path

import fitz as fitz_lib

from src.rendering.elements import (
    ImageElement,
    LineElement,
    PageElement,
    PathElement,
    RectElement,
    TextElement,
)
from src.rendering.extract import extract_page_elements

# Stroke width scale factor. PDF stroke widths include antialiased spread;
# rendering at 0.5x matches the original PDF viewer's visual output.
# Empirically determined via alpha loop on diagram-heavy pages.
_STROKE_WIDTH_SCALE = 0.50


def _scale_stroke_width(width: float) -> float:
    """Apply stroke width scaling for visual fidelity."""
    return width * _STROKE_WIDTH_SCALE


def _map_font_family(font_name: str) -> str:
    """Map PDF font names to CSS font families."""
    name_lower = font_name.lower()
    base = name_lower.replace(",bold", "").replace(",italic", "").replace(",bolditalic", "")
    base = base.replace("-bold", "").replace("-italic", "").replace("-bolditalic", "")

    if "arial" in base:
        return "Arial, Helvetica, sans-serif"
    if "helvetica" in base:
        return "Helvetica, Arial, sans-serif"
    if "calibri" in base:
        return "Carlito, Calibri, sans-serif"
    if "times" in base:
        return "'Times New Roman', Times, serif"
    if "cambria" in base:
        return "Caladea, Cambria, serif"
    if "courier" in base:
        return "'Courier New', Courier, monospace"
    if "symbol" in base:
        return "Symbol"

    return f"'{font_name}', sans-serif"


def render_page_to_html(
    page_width: float,
    page_height: float,
    elements: list[PageElement],
) -> str:
    """Render page elements to HTML with absolute positioning."""
    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '<meta charset="utf-8">',
        "<style>",
        f"@page {{ size: {page_width}pt {page_height}pt; margin: 0; }}",
        f"body {{ margin: 0; padding: 0; width: {page_width}pt; height: {page_height}pt; "
        f"position: relative; overflow: hidden; }}",
        ".page { position: relative; width: 100%; height: 100%; }",
        "</style>",
        "</head>",
        "<body>",
        '<div class="page">',
    ]

    for elem in elements:
        if isinstance(elem, LineElement):
            _render_line(elem, page_width, page_height, html_parts)
        elif isinstance(elem, RectElement):
            _render_rect(elem, html_parts)
        elif isinstance(elem, PathElement):
            _render_path(elem, page_width, page_height, html_parts)
        elif isinstance(elem, ImageElement):
            _render_image(elem, html_parts)
        elif isinstance(elem, TextElement):
            _render_text(elem, html_parts)

    html_parts.extend(["</div>", "</body>", "</html>"])
    return "\n".join(html_parts)


def _render_line(
    elem: LineElement, page_width: float, page_height: float, html_parts: list[str]
) -> None:
    """Render a line element."""
    render_width = _scale_stroke_width(elem.width)
    dx = elem.x2 - elem.x1
    dy = elem.y2 - elem.y1

    if abs(dy) < 1:
        left = min(elem.x1, elem.x2)
        top = elem.y1 - render_width / 2
        width = abs(dx)
        html_parts.append(
            f'<div style="position:absolute; left:{left}pt; top:{top}pt; '
            f"width:{width}pt; height:{render_width}pt; "
            f'background-color:{elem.color};"></div>'
        )
    elif abs(dx) < 1:
        left = elem.x1 - render_width / 2
        top = min(elem.y1, elem.y2)
        height = abs(dy)
        html_parts.append(
            f'<div style="position:absolute; left:{left}pt; top:{top}pt; '
            f"width:{render_width}pt; height:{height}pt; "
            f'background-color:{elem.color};"></div>'
        )
    else:
        html_parts.append(
            f'<svg style="position:absolute; left:0; top:0; width:{page_width}pt; '
            f'height:{page_height}pt; pointer-events:none;" '
            f'viewBox="0 0 {page_width} {page_height}">'
            f'<line x1="{elem.x1}" y1="{elem.y1}" x2="{elem.x2}" y2="{elem.y2}" '
            f'stroke="{elem.color}" stroke-width="{render_width}"/>'
            f"</svg>"
        )


def _render_rect(elem: RectElement, html_parts: list[str]) -> None:
    """Render a rectangle element."""
    render_stroke = _scale_stroke_width(elem.stroke_width or 1.0)
    style = (
        f"position:absolute; "
        f"left:{elem.bbox.x0}pt; top:{elem.bbox.y0}pt; "
        f"width:{elem.bbox.width}pt; height:{elem.bbox.height}pt; "
    )
    if elem.fill_color:
        style += f"background-color:{elem.fill_color}; "
    if elem.stroke_color:
        style += f"border:{render_stroke}pt solid {elem.stroke_color}; box-sizing:border-box; "
    html_parts.append(f'<div style="{style}"></div>')


def _render_path(
    elem: PathElement, page_width: float, page_height: float, html_parts: list[str]
) -> None:
    """Render an SVG path element."""
    render_stroke = _scale_stroke_width(elem.stroke_width or 1.0)
    fill_attr = f'fill="{elem.fill_color}"' if elem.fill_color else 'fill="none"'
    stroke_attr = (
        f'stroke="{elem.stroke_color}" stroke-width="{render_stroke}"'
        if elem.stroke_color
        else 'stroke="none"'
    )
    html_parts.append(
        f'<svg style="position:absolute; left:0; top:0; width:{page_width}pt; '
        f'height:{page_height}pt; pointer-events:none;" '
        f'viewBox="0 0 {page_width} {page_height}" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{elem.svg_path}" {fill_attr} {stroke_attr}/>'
        f"</svg>"
    )


def _render_image(elem: ImageElement, html_parts: list[str]) -> None:
    """Render an image element."""
    b64 = base64.b64encode(elem.image_data).decode("ascii")
    style = (
        f"position:absolute; "
        f"left:{elem.bbox.x0}pt; top:{elem.bbox.y0}pt; "
        f"width:{elem.bbox.width}pt; height:{elem.bbox.height}pt; "
    )
    html_parts.append(f'<img style="{style}" src="data:{elem.mime_type};base64,{b64}"/>')


def _render_text(elem: TextElement, html_parts: list[str]) -> None:
    """Render a text element with word-level positioning."""
    font_family = _map_font_family(elem.font_name)
    font_weight = "bold" if elem.bold else "normal"
    font_style = "italic" if elem.italic else "normal"
    top_y = elem.bbox.y0
    text_content = elem.text.rstrip()

    if not text_content:
        return

    # Font size for rendering
    render_font_size = elem.font_size_pt

    if elem.char_positions and len(elem.char_positions) >= len(text_content):
        # Word-level positioning with overflow:hidden
        words = _split_words(text_content)

        for word_idx, (ws, we) in enumerate(words):
            word = text_content[ws:we]
            word_x = elem.char_positions[ws]

            if word_idx < len(words) - 1:
                next_ws = words[word_idx + 1][0]
                word_max_x = elem.char_positions[next_ws]
            else:
                word_max_x = elem.bbox.x1

            word_width = word_max_x - word_x
            escaped_word = word.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            style = (
                f"position:absolute; "
                f"left:{word_x}pt; top:{top_y}pt; "
                f"width:{word_width}pt; "
                f"overflow:hidden; "
                f"font-family:{font_family}; "
                f"font-size:{render_font_size}pt; "
                f"font-weight:{font_weight}; "
                f"font-style:{font_style}; "
                f"color:{elem.color}; "
                f"white-space:pre; "
                f"line-height:{elem.font_size_pt}pt; "
                f"height:{elem.bbox.height}pt; "
                f"margin:0; padding:0; "
            )
            html_parts.append(f'<span style="{style}">{escaped_word}</span>')
    else:
        # Fallback: render full span
        escaped_text = text_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        style = (
            f"position:absolute; "
            f"left:{elem.bbox.x0}pt; top:{top_y}pt; "
            f"width:{elem.bbox.width}pt; "
            f"overflow:hidden; "
            f"font-family:{font_family}; "
            f"font-size:{render_font_size}pt; "
            f"font-weight:{font_weight}; "
            f"font-style:{font_style}; "
            f"color:{elem.color}; "
            f"white-space:pre; "
            f"line-height:{elem.font_size_pt}pt; "
            f"height:{elem.bbox.height}pt; "
            f"margin:0; padding:0; "
        )
        html_parts.append(f'<span style="{style}">{escaped_text}</span>')


def _split_words(text: str) -> list[tuple[int, int]]:
    """Split text into word (start, end) index pairs."""
    words = []
    word_start = 0
    for i in range(len(text)):
        if text[i] == " ":
            if i > word_start:
                words.append((word_start, i))
            word_start = i + 1
    if word_start < len(text):
        words.append((word_start, len(text)))
    return words


def render_page_to_pdf(
    pdf_path: Path | str,
    page_number: int,
    output_path: Path | str,
) -> Path:
    """Render a single page from PDF through the IR back to a new PDF.

    Pipeline: PDF → extract elements → HTML/CSS → WeasyPrint → PDF
    """
    from weasyprint import HTML

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height, elements = extract_page_elements(pdf_path, page_number)
    html_content = render_page_to_html(page_width, page_height, elements)

    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    html_doc = HTML(string=html_content)
    html_doc.write_pdf(str(output_path))

    return output_path


def render_pages_to_pdf(
    pdf_path: Path | str,
    page_numbers: list[int],
    output_path: Path | str,
) -> Path:
    """Render multiple pages into a single multi-page PDF.

    Each page is rendered individually then merged via PyMuPDF.
    """
    from weasyprint import HTML

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_doc = fitz_lib.open()

    for page_num in page_numbers:
        page_width, page_height, elements = extract_page_elements(pdf_path, page_num)
        html_content = render_page_to_html(page_width, page_height, elements)

        html_doc = HTML(string=html_content)
        pdf_bytes = html_doc.write_pdf()

        single_doc = fitz_lib.open(stream=pdf_bytes, filetype="pdf")
        output_doc.insert_pdf(single_doc)
        single_doc.close()

    output_doc.save(str(output_path))
    output_doc.close()

    # Save HTML for last page as reference
    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    return output_path
