"""Page renderer — converts Document IR back to PDF via HTML/CSS.

This module takes extracted Document IR (text blocks, images, lines) and
renders them using absolute positioning in HTML/CSS, then converts to PDF
via WeasyPrint. The goal is pixel-faithful reproduction of the original page.
"""

from __future__ import annotations

import base64
from pathlib import Path

import fitz  # PyMuPDF

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
        char_positions: list[float] | None = None,  # x-position of each char
        baseline_y: float | None = None,  # y-coordinate of the text baseline
        ascender: float = 0.0,  # ascender ratio (ascender * font_size = ascent in pt)
        descender: float = 0.0,  # descender ratio
    ):
        self.text = text
        self.bbox = bbox
        self.font_name = font_name
        self.font_size_pt = font_size_pt
        self.bold = bold
        self.italic = italic
        self.color = color
        self.char_positions = char_positions  # enables exact kerning
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
        svg_path: str,  # SVG path data string (M, L, C, Z commands)
        fill_color: str | None = None,
        stroke_color: str | None = None,
        stroke_width: float = 1.0,
    ):
        self.svg_path = svg_path
        self.fill_color = fill_color
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width


def extract_page_elements(pdf_path: Path | str, page_number: int) -> tuple[float, float, list[PageElement]]:
    """Extract all renderable elements from a PDF page.

    Returns:
        Tuple of (page_width_pt, page_height_pt, elements)
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]

    page_width = page.rect.width
    page_height = page.rect.height
    elements: list[PageElement] = []

    # 1. Extract drawings (lines, rects, curves) — render behind text
    drawings = page.get_drawings()
    for drawing in drawings:
        color = drawing.get("color")
        fill = drawing.get("fill")
        stroke_color = _color_to_hex(color) if color else None
        fill_color = _color_to_hex(fill) if fill else None
        line_width = drawing.get("width", 1.0)

        items = drawing.get("items", [])
        has_curves = any(item[0] == "c" for item in items)

        if has_curves or len(items) > 1:
            # Build an SVG path from all items in this drawing
            path_parts = []
            last_end = None  # track the endpoint of the previous segment
            for item in items:
                if item[0] == "l":  # line segment
                    p1, p2 = item[1], item[2]
                    # Check if we need a new moveto (discontinuity)
                    if last_end is None or abs(p1.x - last_end[0]) > 0.5 or abs(p1.y - last_end[1]) > 0.5:
                        path_parts.append(f"M {p1.x:.2f} {p1.y:.2f}")
                    path_parts.append(f"L {p2.x:.2f} {p2.y:.2f}")
                    last_end = (p2.x, p2.y)
                elif item[0] == "c":  # cubic bezier curve
                    p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                    # Check if we need a new moveto (discontinuity)
                    if last_end is None or abs(p1.x - last_end[0]) > 0.5 or abs(p1.y - last_end[1]) > 0.5:
                        path_parts.append(f"M {p1.x:.2f} {p1.y:.2f}")
                    path_parts.append(
                        f"C {p2.x:.2f} {p2.y:.2f} {p3.x:.2f} {p3.y:.2f} {p4.x:.2f} {p4.y:.2f}"
                    )
                    last_end = (p4.x, p4.y)
                elif item[0] == "re":  # rectangle as part of a path
                    rect = item[1]
                    path_parts.append(f"M {rect.x0:.2f} {rect.y0:.2f}")
                    path_parts.append(f"L {rect.x1:.2f} {rect.y0:.2f}")
                    path_parts.append(f"L {rect.x1:.2f} {rect.y1:.2f}")
                    path_parts.append(f"L {rect.x0:.2f} {rect.y1:.2f}")
                    path_parts.append("Z")
                    last_end = (rect.x0, rect.y0)

            if path_parts:
                svg_path = " ".join(path_parts)
                elements.append(PathElement(
                    svg_path=svg_path,
                    fill_color=fill_color,
                    stroke_color=stroke_color,
                    stroke_width=line_width,
                ))
        elif len(items) == 1:
            item = items[0]
            if item[0] == "l":  # single line
                p1, p2 = item[1], item[2]
                elements.append(LineElement(
                    x1=p1.x, y1=p1.y, x2=p2.x, y2=p2.y,
                    color=stroke_color or "#000000",
                    width=line_width,
                ))
            elif item[0] == "re":  # single rectangle
                rect = item[1]
                elements.append(RectElement(
                    bbox=BoundingBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1),
                    fill_color=fill_color,
                    stroke_color=stroke_color,
                    stroke_width=line_width,
                ))

    # 2. Extract images
    image_list = page.get_images(full=True)
    for img_info in image_list:
        xref = img_info[0]
        try:
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            rect = rects[0]
            # Extract image data
            img = doc.extract_image(xref)
            if img:
                bbox = BoundingBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)

                # Skip solid-black narrow images that are connector line artifacts.
                # These are redundant with stroked line drawings and render too thick
                # when scaled as images.
                if bbox.width < 10 or bbox.height < 10:
                    # Check if image is solid black (connector artifact)
                    from PIL import Image as PILImage
                    import io
                    try:
                        pil_img = PILImage.open(io.BytesIO(img["image"]))
                        arr = __import__("numpy").array(pil_img)
                        # If all pixels are very dark, skip it
                        if arr.ndim >= 2:
                            rgb = arr[:, :, :3] if arr.ndim == 3 else arr
                            if rgb.max() < 30:
                                continue  # solid black artifact, skip
                    except Exception:
                        pass

                # For small diagram element images with black borders, crop the
                # border pixels from the source image before embedding. This prevents
                # thick black bands where adjacent boxes overlap. The visual border
                # is provided by the container rectangle strokes in the drawing layer.
                if bbox.width < 250 and bbox.height < 60:
                    from PIL import Image as PILImage
                    import io
                    try:
                        pil_img = PILImage.open(io.BytesIO(img["image"]))
                        arr = __import__("numpy").array(pil_img)
                        if arr.ndim >= 3 and arr.shape[0] > 10 and arr.shape[1] > 10:
                            # Detect border width on each side
                            h, w = arr.shape[0], arr.shape[1]
                            mid_row, mid_col = h // 2, w // 2

                            top_b = 0
                            for row in range(h):
                                if arr[row, mid_col, :3].max() < 30:
                                    top_b += 1
                                else:
                                    break

                            bot_b = 0
                            for row in range(h - 1, -1, -1):
                                if arr[row, mid_col, :3].max() < 30:
                                    bot_b += 1
                                else:
                                    break

                            left_b = 0
                            for col in range(w):
                                if arr[mid_row, col, :3].max() < 30:
                                    left_b += 1
                                else:
                                    break

                            right_b = 0
                            for col in range(w - 1, -1, -1):
                                if arr[mid_row, col, :3].max() < 30:
                                    right_b += 1
                                else:
                                    break

                            # If image has borders, crop them and adjust bbox.
                            # Only crop if the INTERIOR is light (white/gray fill
                            # with dark border). If interior is also dark, this is
                            # a filled dark element (e.g., background for white text)
                            # and should not be cropped.
                            if left_b > 2 or right_b > 2 or top_b > 2 or bot_b > 2:
                                # Check interior brightness
                                cropped = arr[top_b:h - bot_b, left_b:w - right_b]
                                if cropped.shape[0] > 2 and cropped.shape[1] > 2:
                                    interior_mean = cropped[:, :, :3].mean()
                                    if interior_mean > 128:
                                        # Light interior — safe to crop borders
                                        px_to_pt_x = bbox.width / w
                                        px_to_pt_y = bbox.height / h
                                        bbox = BoundingBox(
                                            x0=bbox.x0 + left_b * px_to_pt_x,
                                            y0=bbox.y0 + top_b * px_to_pt_y,
                                            x1=bbox.x1 - right_b * px_to_pt_x,
                                            y1=bbox.y1 - bot_b * px_to_pt_y,
                                        )
                                        # Re-encode cropped image
                                        cropped_pil = PILImage.fromarray(cropped)
                                        buf = io.BytesIO()
                                        cropped_pil.save(buf, format="PNG")
                                        img["image"] = buf.getvalue()
                    except Exception:
                        pass

                mime = f"image/{img['ext']}"
                elements.append(ImageElement(bbox=bbox, image_data=img["image"], mime_type=mime))
        except Exception:
            continue

    # 3. Extract text spans with exact positioning (using rawdict for char-level data)
    text_dict = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                text = "".join(c["c"] for c in chars)
                if not text.strip():
                    continue

                bbox = BoundingBox(
                    x0=span["bbox"][0],
                    y0=span["bbox"][1],
                    x1=span["bbox"][2],
                    y1=span["bbox"][3],
                )

                font = span.get("font", "")
                size = span.get("size", 12.0)
                flags = span.get("flags", 0)
                color_int = span.get("color", 0)

                bold = bool(flags & (1 << 4)) or "bold" in font.lower()
                italic = bool(flags & (1 << 1)) or "italic" in font.lower()

                # Convert color int to hex
                r = (color_int >> 16) & 0xFF
                g = (color_int >> 8) & 0xFF
                b = color_int & 0xFF
                color_hex = f"#{r:02x}{g:02x}{b:02x}"

                # Extract character x-positions for exact kerning
                char_positions = [c["origin"][0] for c in chars] if chars else None

                # Get baseline and font metrics
                baseline_y = span.get("origin", (0, 0))[1]
                ascender = span.get("ascender", 0.0)
                descender = span.get("descender", 0.0)

                elements.append(TextElement(
                    text=text.rstrip(),
                    bbox=bbox,
                    font_name=font,
                    font_size_pt=size,
                    bold=bold,
                    italic=italic,
                    color=color_hex,
                    char_positions=char_positions,
                    baseline_y=baseline_y,
                    ascender=ascender,
                    descender=descender,
                ))

    doc.close()
    return page_width, page_height, elements


def _color_to_hex(color: tuple | None) -> str | None:
    """Convert a color tuple (0-1 floats) to hex."""
    if color is None:
        return None
    if len(color) == 3:
        r, g, b = color
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    return "#000000"


def _map_font_family(font_name: str) -> str:
    """Map PDF font names to CSS font families."""
    name_lower = font_name.lower()

    # Strip style suffixes for matching
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

    # Default: use the font name itself with a fallback
    return f"'{font_name}', sans-serif"


# Stroke width scale factor for rendering. PDF stroke widths include antialiased
# spread; the visually correct rendered width is approximately 50% of the stated
# value. Empirically determined via alpha loop across page types.
_STROKE_WIDTH_SCALE = 0.50


def _scale_stroke_width(width: float) -> float:
    """Apply stroke width scaling for visual fidelity."""
    return width * _STROKE_WIDTH_SCALE

# Vertical offset ratios: the gap between CSS 'top' and where the glyph actually
# renders in WeasyPrint. Measured empirically per font family.
# offset_pt = ratio * font_size_pt
# To compensate: css_top = pdf_bbox_y0 - offset_pt
_FONT_TOP_OFFSET_RATIO: dict[str, float] = {
    "arial": 0.1533,
    "helvetica": 0.1533,
    "times new roman": 0.1833,
    "times": 0.1833,
    "courier new": 0.1533,
    "courier": 0.1533,
}


def _get_font_top_offset(font_name: str, font_size_pt: float) -> float:
    """Get the vertical correction offset for a font in WeasyPrint.

    WeasyPrint places the top of the glyph below the CSS 'top' value
    by a font-specific amount. This returns the offset to subtract from
    bbox.y0 to get the correct CSS top value.
    """
    name_lower = font_name.lower()
    base = name_lower.replace(",bold", "").replace(",italic", "").replace(",bolditalic", "")
    base = base.replace("-bold", "").replace("-italic", "").replace("-bolditalic", "")

    for key, ratio in _FONT_TOP_OFFSET_RATIO.items():
        if key in base:
            return ratio * font_size_pt

    # Default: use Arial's ratio as a reasonable fallback
    return 0.155 * font_size_pt


def render_page_to_html(
    page_width: float,
    page_height: float,
    elements: list[PageElement],
) -> str:
    """Render page elements to HTML with absolute positioning.

    Uses CSS absolute positioning to place every element at its exact
    PDF coordinate. This produces a faithful visual reproduction.
    """
    html_parts = [
        '<!DOCTYPE html>',
        '<html>',
        '<head>',
        '<meta charset="utf-8">',
        '<style>',
        f'@page {{ size: {page_width}pt {page_height}pt; margin: 0; }}',
        f'body {{ margin: 0; padding: 0; width: {page_width}pt; height: {page_height}pt; position: relative; overflow: hidden; }}',
        '.page { position: relative; width: 100%; height: 100%; }',
        '</style>',
        '</head>',
        '<body>',
        '<div class="page">',
    ]

    for i, elem in enumerate(elements):
        if isinstance(elem, LineElement):
            # Render lines using absolutely-positioned divs with borders
            # Apply stroke width scaling for visual fidelity
            render_width = _scale_stroke_width(elem.width)
            dx = elem.x2 - elem.x1
            dy = elem.y2 - elem.y1
            if abs(dy) < 1:
                # Horizontal line
                left = min(elem.x1, elem.x2)
                top = elem.y1 - render_width / 2
                width = abs(dx)
                html_parts.append(
                    f'<div style="position:absolute; left:{left}pt; top:{top}pt; '
                    f'width:{width}pt; height:{render_width}pt; '
                    f'background-color:{elem.color};"></div>'
                )
            elif abs(dx) < 1:
                # Vertical line
                left = elem.x1 - render_width / 2
                top = min(elem.y1, elem.y2)
                height = abs(dy)
                html_parts.append(
                    f'<div style="position:absolute; left:{left}pt; top:{top}pt; '
                    f'width:{render_width}pt; height:{height}pt; '
                    f'background-color:{elem.color};"></div>'
                )
            else:
                # Angled line — use SVG as fallback
                html_parts.append(
                    f'<svg style="position:absolute; left:0; top:0; width:{page_width}pt; height:{page_height}pt; pointer-events:none;" '
                    f'viewBox="0 0 {page_width} {page_height}">'
                    f'<line x1="{elem.x1}" y1="{elem.y1}" x2="{elem.x2}" y2="{elem.y2}" '
                    f'stroke="{elem.color}" stroke-width="{render_width}"/>'
                    f'</svg>'
                )
        elif isinstance(elem, RectElement):
            render_stroke = _scale_stroke_width(elem.stroke_width or 1.0)
            style = (
                f'position:absolute; '
                f'left:{elem.bbox.x0}pt; top:{elem.bbox.y0}pt; '
                f'width:{elem.bbox.width}pt; height:{elem.bbox.height}pt; '
            )
            if elem.fill_color:
                style += f'background-color:{elem.fill_color}; '
            if elem.stroke_color:
                style += f'border:{render_stroke}pt solid {elem.stroke_color}; box-sizing:border-box; '
            html_parts.append(f'<div style="{style}"></div>')
        elif isinstance(elem, PathElement):
            # Render complex paths using inline SVG
            render_stroke = _scale_stroke_width(elem.stroke_width or 1.0)
            fill_attr = f'fill="{elem.fill_color}"' if elem.fill_color else 'fill="none"'
            stroke_attr = f'stroke="{elem.stroke_color}" stroke-width="{render_stroke}"' if elem.stroke_color else 'stroke="none"'
            html_parts.append(
                f'<svg style="position:absolute; left:0; top:0; width:{page_width}pt; height:{page_height}pt; pointer-events:none;" '
                f'viewBox="0 0 {page_width} {page_height}" xmlns="http://www.w3.org/2000/svg">'
                f'<path d="{elem.svg_path}" {fill_attr} {stroke_attr}/>'
                f'</svg>'
            )
        elif isinstance(elem, ImageElement):
            b64 = base64.b64encode(elem.image_data).decode("ascii")
            style = (
                f'position:absolute; '
                f'left:{elem.bbox.x0}pt; top:{elem.bbox.y0}pt; '
                f'width:{elem.bbox.width}pt; height:{elem.bbox.height}pt; '
            )
            html_parts.append(
                f'<img style="{style}" src="data:{elem.mime_type};base64,{b64}"/>'
            )
        elif isinstance(elem, TextElement):
            font_family = _map_font_family(elem.font_name)
            font_weight = "bold" if elem.bold else "normal"
            font_style = "italic" if elem.italic else "normal"

            # Position text at the PDF bbox top coordinate.
            top_y = elem.bbox.y0
            text_content = elem.text.rstrip()

            if not text_content:
                continue

            # Word-level positioning: split text at spaces and position each word
            # at its exact PDF x-coordinate. This prevents column bleed by ensuring
            # each word starts where the PDF says it should, with overflow:hidden
            # clipping any glyph-width overrun before the next word starts.
            if elem.char_positions and len(elem.char_positions) >= len(text_content):
                # Split into words and find each word's start position and width
                words = []
                word_start = 0
                i = 0
                while i < len(text_content):
                    if text_content[i] == ' ':
                        if i > word_start:
                            words.append((word_start, i))
                        word_start = i + 1
                    i += 1
                if word_start < len(text_content):
                    words.append((word_start, len(text_content)))

                for word_idx, (ws, we) in enumerate(words):
                    word = text_content[ws:we]
                    word_x = elem.char_positions[ws]

                    # Word width: from this word's start to next word's start (or bbox end)
                    if word_idx < len(words) - 1:
                        next_ws = words[word_idx + 1][0]
                        word_max_x = elem.char_positions[next_ws]
                    else:
                        word_max_x = elem.bbox.x1

                    word_width = word_max_x - word_x

                    # Font size for rendering — use original PDF size.
                    # overflow:hidden handles any glyph overrun from font metric
                    # differences between the original and system fonts.
                    render_font_size = elem.font_size_pt

                    escaped_word = (
                        word
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    style = (
                        f'position:absolute; '
                        f'left:{word_x}pt; top:{top_y}pt; '
                        f'width:{word_width}pt; '
                        f'overflow:hidden; '
                        f'font-family:{font_family}; '
                        f'font-size:{render_font_size}pt; '
                        f'font-weight:{font_weight}; '
                        f'font-style:{font_style}; '
                        f'color:{elem.color}; '
                        f'white-space:pre; '
                        f'line-height:{elem.font_size_pt}pt; '
                        f'height:{elem.bbox.height}pt; '
                        f'margin:0; padding:0; '
                    )
                    html_parts.append(f'<span style="{style}">{escaped_word}</span>')
            else:
                # Fallback: render full span with bbox-width clipping
                escaped_text = (
                    text_content
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                style = (
                    f'position:absolute; '
                    f'left:{elem.bbox.x0}pt; top:{top_y}pt; '
                    f'width:{elem.bbox.width}pt; '
                    f'overflow:hidden; '
                    f'font-family:{font_family}; '
                    f'font-size:{elem.font_size_pt}pt; '
                    f'font-weight:{font_weight}; '
                    f'font-style:{font_style}; '
                    f'color:{elem.color}; '
                    f'white-space:pre; '
                    f'line-height:{elem.font_size_pt}pt; '
                    f'height:{elem.bbox.height}pt; '
                    f'margin:0; padding:0; '
                )
                html_parts.append(f'<span style="{style}">{escaped_text}</span>')

    html_parts.extend([
        '</div>',
        '</body>',
        '</html>',
    ])

    return "\n".join(html_parts)


def render_page_to_pdf(
    pdf_path: Path | str,
    page_number: int,
    output_path: Path | str,
) -> Path:
    """Render a single page from PDF through the IR back to a new PDF.

    Pipeline: PDF → extract elements → HTML/CSS → WeasyPrint → PDF

    Args:
        pdf_path: Source PDF path.
        page_number: 1-based page number.
        output_path: Where to save the regenerated PDF.

    Returns:
        Path to the output PDF.
    """
    from weasyprint import HTML

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract
    page_width, page_height, elements = extract_page_elements(pdf_path, page_number)

    # Render to HTML
    html_content = render_page_to_html(page_width, page_height, elements)

    # Save intermediate HTML for inspection
    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    # Convert to PDF
    html_doc = HTML(string=html_content)
    html_doc.write_pdf(str(output_path))

    return output_path


def render_pages_to_pdf(
    pdf_path: Path | str,
    page_numbers: list[int],
    output_path: Path | str,
) -> Path:
    """Render multiple pages from a PDF into a single multi-page output PDF.

    Each page is extracted independently and combined into a single document.

    Args:
        pdf_path: Source PDF path.
        page_numbers: List of 1-based page numbers to render (in order).
        output_path: Where to save the regenerated multi-page PDF.

    Returns:
        Path to the output PDF.
    """
    from weasyprint import HTML

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Strategy: render each page to its own PDF, then merge with PyMuPDF.
    # This avoids WeasyPrint multi-page CSS issues and guarantees each page
    # renders identically to the single-page path.
    import fitz as fitz_lib

    output_doc = fitz_lib.open()

    for page_num in page_numbers:
        # Extract and render single page
        page_width, page_height, elements = extract_page_elements(pdf_path, page_num)
        html_content = render_page_to_html(page_width, page_height, elements)

        # Render to PDF bytes
        html_doc = HTML(string=html_content)
        pdf_bytes = html_doc.write_pdf()

        # Open the single-page PDF and insert into output
        single_doc = fitz_lib.open(stream=pdf_bytes, filetype="pdf")
        output_doc.insert_pdf(single_doc)
        single_doc.close()

    output_doc.save(str(output_path))
    output_doc.close()

    # Save the HTML for the last page as reference
    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    return output_path
