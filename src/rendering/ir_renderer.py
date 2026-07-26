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
    """Render a Document IR to PDF, using the same pipeline as direct rendering.

    For unedited blocks: uses exact character positions from source PDF.
    For edited blocks: re-renders with word-level positioning (same as pipeline).

    This ensures the export matches the pipeline quality, with edits applied.
    """
    from weasyprint import HTML

    from src.rendering.extract import extract_page_elements
    from src.rendering.elements import TextElement
    from src.rendering.renderer import render_page_to_html

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

        # Extract all elements from source PDF (full fidelity)
        page_width, page_height, elements = extract_page_elements(source_pdf, page_num)

        # Find edited blocks by comparing IR text to extracted text
        ir_texts = {b.id: b.text_verbatim for b in page_info.text_blocks}

        # Replace text in elements where the IR has been edited
        patched_elements = []
        for elem in elements:
            if isinstance(elem, TextElement):
                # Find matching IR block by position
                for block in page_info.text_blocks:
                    if (abs(block.bbox.x0 - elem.bbox.x0) < 1 and
                            abs(block.bbox.y0 - elem.bbox.y0) < 1):
                        if block.text_verbatim != elem.text:
                            # This block was edited — use IR text, lose char positions
                            elem = TextElement(
                                text=block.text_verbatim,
                                bbox=elem.bbox,
                                font_name=elem.font_name,
                                font_size_pt=elem.font_size_pt,
                                bold=elem.bold,
                                italic=elem.italic,
                                color=elem.color,
                                char_positions=None,  # will use word-level fallback
                            )
                        break
            patched_elements.append(elem)

        # Render with the pipeline renderer
        html_content = render_page_to_html(page_width, page_height, patched_elements)
        pdf_bytes = HTML(string=html_content).write_pdf()

        single_doc = fitz_lib.open(stream=pdf_bytes, filetype="pdf")
        output_doc.insert_pdf(single_doc)
        single_doc.close()

    output_doc.save(str(output_path))
    output_doc.close()

    return output_path
