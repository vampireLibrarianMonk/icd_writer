"""Render from Document IR (for edited documents).

Unlike render_pages_to_pdf which re-extracts from the source PDF,
this renders from the in-memory Document IR — reflecting any edits
made by the user.
"""

from __future__ import annotations

from pathlib import Path

import fitz as fitz_lib

from src.models.common import BoundingBox
from src.models.document_ir import DocumentIR
from src.rendering.elements import (
    ImageElement,
    PageElement,
    TextElement,
)
from src.rendering.extract import extract_page_elements
from src.rendering.renderer import render_page_to_html


def render_ir_to_pdf(
    document_ir: DocumentIR,
    source_pdf: Path | str,
    output_path: Path | str,
    pages: list[int] | None = None,
) -> Path:
    """Render a Document IR to PDF, using source PDF for images/drawings.

    The text comes from the IR (reflecting edits). Images and vector
    graphics come from the source PDF (unchanged). This allows text
    edits to appear in the output while preserving all other elements.

    Args:
        document_ir: The (possibly edited) Document IR.
        source_pdf: Original PDF for images/drawings.
        output_path: Where to save the output PDF.
        pages: Optional list of 1-based page numbers to render.
            If None, renders all pages.

    Returns:
        Path to the output PDF.
    """
    from weasyprint import HTML

    source_pdf = Path(source_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if pages is None:
        pages = list(range(1, document_ir.page_count + 1))

    output_doc = fitz_lib.open()

    for page_num in pages:
        page_idx = page_num - 1
        if page_idx >= len(document_ir.pages):
            continue

        page_info = document_ir.pages[page_idx]
        page_width = page_info.width_pt
        page_height = page_info.height_pt

        # Get non-text elements (images, drawings) from source PDF
        _, _, source_elements = extract_page_elements(source_pdf, page_num)
        non_text_elements = [
            e for e in source_elements if not isinstance(e, TextElement)
        ]

        # Build text elements from the IR (reflects edits)
        text_elements: list[PageElement] = []
        for block in page_info.text_blocks:
            text_elements.append(
                TextElement(
                    text=block.text_verbatim,
                    bbox=block.bbox,
                    font_name=block.style.font_name or "Times New Roman"
                    if block.style
                    else "Times New Roman",
                    font_size_pt=block.style.font_size_pt
                    if block.style
                    else 11.0,
                    bold=block.style.bold if block.style else False,
                    italic=block.style.italic if block.style else False,
                    color="#000000",
                    char_positions=None,  # Will use fallback word positioning
                )
            )

        # Combine: non-text first (background), then text on top
        all_elements = non_text_elements + text_elements

        # Render to HTML then PDF
        html_content = render_page_to_html(page_width, page_height, all_elements)
        pdf_bytes = HTML(string=html_content).write_pdf()

        single_doc = fitz_lib.open(stream=pdf_bytes, filetype="pdf")
        output_doc.insert_pdf(single_doc)
        single_doc.close()

    output_doc.save(str(output_path))
    output_doc.close()

    return output_path
