"""Page element extraction from PDF.

Reads a PDF page and produces a list of PageElements (text, images,
lines, rects, paths) with exact coordinates and styling.
"""

from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image as PILImage

from src.models.common import BoundingBox
from src.rendering.elements import (
    ImageElement,
    LineElement,
    PageElement,
    PathElement,
    RectElement,
    TextElement,
)


def extract_page_elements(
    pdf_path: Path | str, page_number: int
) -> tuple[float, float, list[PageElement]]:
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

    _extract_drawings(page, elements)
    _extract_images(doc, page, elements)
    _extract_text(page, elements)

    doc.close()
    return page_width, page_height, elements


def _color_to_hex(color: tuple | None) -> str | None:
    """Convert a color tuple (0-1 floats) to hex."""
    if color is None:
        return None
    if len(color) == 3:
        r, g, b = color
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    return "#000000"


def _extract_drawings(page: fitz.Page, elements: list[PageElement]) -> None:
    """Extract drawings (lines, rects, curves) from the page."""
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
            _build_path_element(items, fill_color, stroke_color, line_width, elements)
        elif len(items) == 1:
            item = items[0]
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                elements.append(
                    LineElement(
                        x1=p1.x,
                        y1=p1.y,
                        x2=p2.x,
                        y2=p2.y,
                        color=stroke_color or "#000000",
                        width=line_width,
                    )
                )
            elif item[0] == "re":
                rect = item[1]
                elements.append(
                    RectElement(
                        bbox=BoundingBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1),
                        fill_color=fill_color,
                        stroke_color=stroke_color,
                        stroke_width=line_width,
                    )
                )


def _build_path_element(
    items: list,
    fill_color: str | None,
    stroke_color: str | None,
    line_width: float,
    elements: list[PageElement],
) -> None:
    """Build an SVG path from drawing items, handling discontinuities."""
    path_parts = []
    last_end = None

    for item in items:
        if item[0] == "l":
            p1, p2 = item[1], item[2]
            if last_end is None or abs(p1.x - last_end[0]) > 0.5 or abs(p1.y - last_end[1]) > 0.5:
                path_parts.append(f"M {p1.x:.2f} {p1.y:.2f}")
            path_parts.append(f"L {p2.x:.2f} {p2.y:.2f}")
            last_end = (p2.x, p2.y)
        elif item[0] == "c":
            p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
            if last_end is None or abs(p1.x - last_end[0]) > 0.5 or abs(p1.y - last_end[1]) > 0.5:
                path_parts.append(f"M {p1.x:.2f} {p1.y:.2f}")
            path_parts.append(
                f"C {p2.x:.2f} {p2.y:.2f} {p3.x:.2f} {p3.y:.2f} {p4.x:.2f} {p4.y:.2f}"
            )
            last_end = (p4.x, p4.y)
        elif item[0] == "re":
            rect = item[1]
            path_parts.append(f"M {rect.x0:.2f} {rect.y0:.2f}")
            path_parts.append(f"L {rect.x1:.2f} {rect.y0:.2f}")
            path_parts.append(f"L {rect.x1:.2f} {rect.y1:.2f}")
            path_parts.append(f"L {rect.x0:.2f} {rect.y1:.2f}")
            path_parts.append("Z")
            last_end = (rect.x0, rect.y0)

    if path_parts:
        svg_path = " ".join(path_parts)
        elements.append(
            PathElement(
                svg_path=svg_path,
                fill_color=fill_color,
                stroke_color=stroke_color,
                stroke_width=line_width,
            )
        )


def _extract_images(doc: fitz.Document, page: fitz.Page, elements: list[PageElement]) -> None:
    """Extract images from the page with border detection and filtering."""
    image_list = page.get_images(full=True)
    for img_info in image_list:
        xref = img_info[0]
        try:
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            rect = rects[0]
            img = doc.extract_image(xref)
            if not img:
                continue

            bbox = BoundingBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)
            image_bytes = img["image"]

            # Filter: skip solid-black narrow images (connector artifacts)
            if bbox.width < 10 or bbox.height < 10:
                if _is_solid_black(image_bytes):
                    continue

            # Process: crop borders from diagram element images
            if bbox.width < 250 and bbox.height < 60:
                result = _crop_borders(image_bytes, bbox)
                if result:
                    image_bytes, bbox = result

            mime = f"image/{img['ext']}"
            elements.append(ImageElement(bbox=bbox, image_data=image_bytes, mime_type=mime))
        except Exception:
            continue


def _is_solid_black(image_bytes: bytes) -> bool:
    """Check if an image is entirely solid black."""
    try:
        pil_img = PILImage.open(io.BytesIO(image_bytes))
        arr = np.array(pil_img)
        if arr.ndim >= 2:
            rgb = arr[:, :, :3] if arr.ndim == 3 else arr
            return rgb.max() < 30
    except Exception:
        pass
    return False


def _crop_borders(image_bytes: bytes, bbox: BoundingBox) -> tuple[bytes, BoundingBox] | None:
    """Crop black borders from a diagram element image.

    Only crops if the interior is light (mean > 128). Dark-interior
    images (backgrounds for white text) are left untouched.

    Returns:
        Tuple of (new_image_bytes, new_bbox) or None if no cropping needed.
    """
    try:
        pil_img = PILImage.open(io.BytesIO(image_bytes))
        arr = np.array(pil_img)
        if arr.ndim < 3 or arr.shape[0] <= 10 or arr.shape[1] <= 10:
            return None

        h, w = arr.shape[0], arr.shape[1]
        mid_row, mid_col = h // 2, w // 2

        # Detect border width on each side
        top_b = _measure_border(arr, mid_col, "top")
        bot_b = _measure_border(arr, mid_col, "bottom")
        left_b = _measure_border(arr, mid_row, "left")
        right_b = _measure_border(arr, mid_row, "right")

        if left_b <= 2 and right_b <= 2 and top_b <= 2 and bot_b <= 2:
            return None

        # Check interior brightness
        cropped = arr[top_b : h - bot_b, left_b : w - right_b]
        if cropped.shape[0] <= 2 or cropped.shape[1] <= 2:
            return None

        interior_mean = cropped[:, :, :3].mean()
        if interior_mean <= 128:
            return None  # Dark interior — don't crop

        # Crop and adjust bbox
        px_to_pt_x = bbox.width / w
        px_to_pt_y = bbox.height / h

        new_bbox = BoundingBox(
            x0=bbox.x0 + left_b * px_to_pt_x,
            y0=bbox.y0 + top_b * px_to_pt_y,
            x1=bbox.x1 - right_b * px_to_pt_x,
            y1=bbox.y1 - bot_b * px_to_pt_y,
        )

        cropped_pil = PILImage.fromarray(cropped)
        buf = io.BytesIO()
        cropped_pil.save(buf, format="PNG")
        return buf.getvalue(), new_bbox

    except Exception:
        return None


def _measure_border(arr: np.ndarray, mid: int, side: str) -> int:
    """Measure the black border width on one side of an image."""
    h, w = arr.shape[0], arr.shape[1]
    count = 0

    if side == "top":
        for row in range(h):
            if arr[row, mid, :3].max() < 30:
                count += 1
            else:
                break
    elif side == "bottom":
        for row in range(h - 1, -1, -1):
            if arr[row, mid, :3].max() < 30:
                count += 1
            else:
                break
    elif side == "left":
        for col in range(w):
            if arr[mid, col, :3].max() < 30:
                count += 1
            else:
                break
    elif side == "right":
        for col in range(w - 1, -1, -1):
            if arr[mid, col, :3].max() < 30:
                count += 1
            else:
                break

    return count


def _extract_text(page: fitz.Page, elements: list[PageElement]) -> None:
    """Extract text spans with character-level positioning."""
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

                r = (color_int >> 16) & 0xFF
                g = (color_int >> 8) & 0xFF
                b = color_int & 0xFF
                color_hex = f"#{r:02x}{g:02x}{b:02x}"

                char_positions = [c["origin"][0] for c in chars] if chars else None
                baseline_y = span.get("origin", (0, 0))[1]
                ascender = span.get("ascender", 0.0)
                descender = span.get("descender", 0.0)

                elements.append(
                    TextElement(
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
                    )
                )
