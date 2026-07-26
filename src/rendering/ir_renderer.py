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
    """Render a Document IR to PDF with selective re-rendering.

    Only pages with edits get re-rendered through HTML/CSS/WeasyPrint.
    Unchanged pages are copied directly from the source PDF (instant,
    pixel-perfect). This makes export fast for large documents where
    only 1-2 pages were modified.

    Args:
        document_ir: The (possibly edited) Document IR.
        source_pdf: Original PDF for unchanged pages and element extraction.
        output_path: Where to save the output PDF.
        pages: Optional list of 1-based page numbers to include.
            If None, includes all pages.

    Returns:
        Path to the output PDF.
    """
    from weasyprint import HTML

    from src.rendering.elements import TextElement
    from src.rendering.extract import extract_page_elements
    from src.rendering.renderer import render_page_to_html

    source_pdf = Path(source_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if pages is None:
        pages = list(range(1, document_ir.page_count + 1))

    # Determine which pages have edits by comparing IR text to source
    edited_pages = _find_edited_pages(document_ir, source_pdf, pages)

    source_doc = fitz_lib.open(str(source_pdf))
    output_doc = fitz_lib.open()

    for page_num in pages:
        page_idx = page_num - 1

        if page_num in edited_pages:
            # Re-render this page (has edits)
            page_info = document_ir.pages[page_idx]
            page_width, page_height, elements = extract_page_elements(
                source_pdf, page_num
            )

            # Patch edited text blocks
            patched_elements = []
            for elem in elements:
                if isinstance(elem, TextElement):
                    for block in page_info.text_blocks:
                        if (
                            abs(block.bbox.x0 - elem.bbox.x0) < 1
                            and abs(block.bbox.y0 - elem.bbox.y0) < 1
                        ):
                            if block.text_verbatim != elem.text:
                                elem = TextElement(
                                    text=block.text_verbatim,
                                    bbox=elem.bbox,
                                    font_name=elem.font_name,
                                    font_size_pt=elem.font_size_pt,
                                    bold=elem.bold,
                                    italic=elem.italic,
                                    color=elem.color,
                                    char_positions=None,
                                )
                            break
                patched_elements.append(elem)

            html_content = render_page_to_html(
                page_width, page_height, patched_elements
            )
            pdf_bytes = HTML(string=html_content).write_pdf()

            single_doc = fitz_lib.open(stream=pdf_bytes, filetype="pdf")
            output_doc.insert_pdf(single_doc)
            single_doc.close()
        else:
            # Copy page directly from source (no edits — pixel-perfect, instant)
            output_doc.insert_pdf(source_doc, from_page=page_idx, to_page=page_idx)

    output_doc.save(str(output_path))
    output_doc.close()
    source_doc.close()

    return output_path


def _find_edited_pages(
    document_ir: DocumentIR, source_pdf: Path, pages: list[int]
) -> set[int]:
    """Determine which pages have been edited by comparing IR to source.

    Compares the IR text blocks against freshly extracted text from the
    source PDF. Any page where text differs has been edited.
    """
    import fitz

    edited: set[int] = set()
    doc = fitz.open(str(source_pdf))

    for page_num in pages:
        page_idx = page_num - 1
        if page_idx >= len(document_ir.pages) or page_idx >= len(doc):
            continue

        # Get source text
        source_text = doc[page_idx].get_text("text")

        # Get IR text for this page
        ir_text = "\n".join(
            b.text_verbatim for b in document_ir.pages[page_idx].text_blocks
        )

        # Normalize and compare
        if " ".join(source_text.split()) != " ".join(ir_text.split()):
            edited.add(page_num)

    doc.close()
    return edited
