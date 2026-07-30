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
    pixel-perfect). Pages that were created by page-split (no source)
    are rendered entirely from the Document IR.

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

    source_doc = fitz_lib.open(str(source_pdf))
    source_page_count = len(source_doc)

    # Determine which pages have edits (only for pages that exist in source)
    source_pages = [p for p in pages if p <= source_page_count]
    edited_pages = _find_edited_pages(document_ir, source_pdf, source_pages)

    output_doc = fitz_lib.open()

    for page_num in pages:
        page_idx = page_num - 1

        if page_num > source_page_count:
            # New page (created by page split) — render entirely from IR
            page_info = document_ir.pages[page_idx]
            elements = _ir_blocks_to_elements(page_info)
            html_content = render_page_to_html(
                page_info.width_pt, page_info.height_pt, elements
            )
            pdf_bytes = HTML(string=html_content).write_pdf()
            single_doc = fitz_lib.open(stream=pdf_bytes, filetype="pdf")
            output_doc.insert_pdf(single_doc)
            single_doc.close()

        elif page_num in edited_pages:
            # Re-render this page entirely from IR (has edits)
            page_info = document_ir.pages[page_idx]
            elements = _ir_blocks_to_elements(page_info)
            html_content = render_page_to_html(
                page_info.width_pt, page_info.height_pt, elements
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


def _ir_blocks_to_elements(page_info: "PageInfo") -> list["PageElement"]:
    """Convert Document IR text blocks to renderable TextElements.

    Used for pages that have no source PDF equivalent (created by page split).
    """
    from src.rendering.elements import TextElement

    elements: list[PageElement] = []

    for block in page_info.text_blocks:
        font_size = 10.0
        bold = False
        italic = False
        font_name = "Helvetica"

        if block.style:
            if block.style.font_size_pt:
                font_size = block.style.font_size_pt
            bold = block.style.bold
            italic = block.style.italic
            if block.style.font_name:
                font_name = block.style.font_name

        # For table-like blocks, expand bbox height to fit reformatted content
        formatted_text = _format_block_text(block)
        line_count = formatted_text.count("\n") + 1
        min_height = line_count * (font_size * 1.4)  # line height ~1.4x font size
        block_height = block.bbox.y1 - block.bbox.y0
        actual_height = max(block_height, min_height)

        elements.append(
            TextElement(
                text=formatted_text,
                bbox=BoundingBox(
                    x0=block.bbox.x0,
                    y0=block.bbox.y0,
                    x1=block.bbox.x1,
                    y1=block.bbox.y0 + actual_height,
                ),
                font_name=font_name,
                font_size_pt=font_size,
                bold=bold,
                italic=italic,
                color="#000000",
                char_positions=None,
            )
        )

    return elements


def _format_block_text(block) -> str:
    """Format block text for rendering.

    Detects table-like content (newline-separated key-value pairs)
    and formats it with spacing to approximate tabular layout.
    """
    text = block.text_verbatim
    lines = text.split("\n")

    # Detect table pattern: alternating key/value lines (short lines, no sentences)
    if len(lines) >= 4 and all(len(l.strip()) < 40 for l in lines if l.strip()):
        # Check if it looks like key-value pairs (even lines are keys, odd are values)
        # Or header row followed by data rows
        is_tabular = True
        for line in lines:
            if len(line.strip()) > 60:
                is_tabular = False
                break

        if is_tabular:
            # Format as aligned columns with padding
            formatted_lines = []
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line:
                    # Check if next line is a value (short, no colon)
                    if i + 1 < len(lines) and lines[i + 1].strip() and len(lines[i + 1].strip()) < 30:
                        formatted_lines.append(f"{line:30s} {lines[i + 1].strip()}")
                        i += 2
                        continue
                    formatted_lines.append(line)
                i += 1
            return "\n".join(formatted_lines)

    return text


def _find_edited_pages(
    document_ir: DocumentIR, source_pdf: Path, pages: list[int]
) -> set[int]:
    """Determine which pages have been edited by comparing IR to source.

    Compares the IR text blocks against freshly extracted text from the
    source PDF. Any page where text differs has been edited.
    Only checks pages that exist in both the IR and source PDF.
    """
    import fitz

    edited: set[int] = set()
    doc = fitz.open(str(source_pdf))
    source_page_count = len(doc)

    for page_num in pages:
        page_idx = page_num - 1
        if page_idx >= len(document_ir.pages) or page_idx >= source_page_count:
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
