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

    Used for pages that have no source PDF equivalent (created by page split)
    or edited pages that need re-rendering.
    Filters out overlapping blocks to prevent visual corruption.
    """
    from src.rendering.elements import TextElement

    elements: list[PageElement] = []
    rendered_regions: list[tuple[float, float, float, float]] = []  # x0, y0, x1, y1

    for block in sorted(page_info.text_blocks, key=lambda b: (b.bbox.y0, b.bbox.x0)):
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

        # Skip blocks that significantly overlap an already-rendered region
        # (prevents table fragment duplication)
        bbox = block.bbox
        overlaps = False
        for (rx0, ry0, rx1, ry1) in rendered_regions:
            # Check if this block's center is inside an existing region
            center_y = (bbox.y0 + bbox.y1) / 2
            center_x = (bbox.x0 + bbox.x1) / 2
            if rx0 <= center_x <= rx1 and ry0 <= center_y <= ry1:
                overlaps = True
                break

        if overlaps:
            continue

        rendered_regions.append((bbox.x0, bbox.y0, bbox.x1, bbox.y1))

        # Check if this is a table data block (preceded by caption)
        is_table_block = _is_table_data_block(block, page_info)

        if is_table_block:
            # Split table text into per-cell TextElements aligned to grid
            cell_elements = _split_table_into_cells(block, font_name, font_size, bold, italic)
            elements.extend(cell_elements)
        else:
            elements.append(
                TextElement(
                    text=_format_block_text(block),
                    bbox=block.bbox,
                    font_name=font_name,
                    font_size_pt=font_size,
                    bold=bold,
                    italic=italic,
                    color="#000000",
                    char_positions=None,
                )
            )

    # Add table grid lines for table-data blocks
    _add_table_lines(page_info, elements)

    return elements


def _format_block_text(block) -> str:
    """Format block text for rendering. Plain text passthrough."""
    return block.text_verbatim


def _is_table_data_block(block, page_info) -> bool:
    """Check if a block is table data (paragraph preceded by a caption within 15pt).

    A table data block has:
    - block_type == "paragraph"
    - A caption block within 15pt above it
    - At least 2 newline-separated lines
    """
    if block.block_type != "paragraph":
        return False

    lines = [l for l in block.text_verbatim.split("\n") if l.strip()]
    if len(lines) < 2:
        return False

    # Check if preceded by a caption
    for other in page_info.text_blocks:
        if other.block_type == "caption":
            if other.bbox.y1 <= block.bbox.y0 and (block.bbox.y0 - other.bbox.y1) < 15:
                return True

    return False


def _split_table_into_cells(block, font_name: str, font_size: float,
                            bold: bool, italic: bool) -> list:
    """Split a table data block into per-cell TextElements.

    Parses newline-separated text into rows x columns and creates
    a TextElement for each cell, positioned within the grid.

    Assumes 2-column layout (key/value pairs) based on the common
    ICD table format: "Key\\nValue\\nKey\\nValue\\n..."
    """
    from src.rendering.elements import TextElement

    lines = [l for l in block.text_verbatim.split("\n") if l.strip()]
    if len(lines) < 2:
        # Fallback: single element
        return [TextElement(
            text=block.text_verbatim, bbox=block.bbox,
            font_name=font_name, font_size_pt=font_size,
            bold=bold, italic=italic, color="#000000", char_positions=None,
        )]

    x0 = block.bbox.x0
    x1 = block.bbox.x1
    y0 = block.bbox.y0
    y1 = block.bbox.y1
    mid_x = (x0 + x1) / 2
    block_height = y1 - y0
    num_rows = len(lines) // 2  # Assume pairs (key, value)
    if num_rows < 1:
        num_rows = len(lines)

    # Determine layout: even number of lines → 2-column table
    # Odd number → try single column
    elements = []

    if len(lines) % 2 == 0 and len(lines) >= 4:
        # 2-column layout: lines alternate key, value
        row_height = block_height / num_rows
        padding_x = 3.0  # Small padding from cell edge
        padding_y = 2.0  # Small padding from top of cell

        for row_idx in range(num_rows):
            key_line = lines[row_idx * 2]
            val_line = lines[row_idx * 2 + 1]
            row_y = y0 + row_idx * row_height + padding_y

            # Left column (key)
            elements.append(TextElement(
                text=key_line,
                bbox=BoundingBox(x0=x0 + padding_x, y0=row_y,
                                 x1=mid_x - padding_x, y1=row_y + font_size * 1.2),
                font_name=font_name, font_size_pt=font_size,
                bold=bold, italic=italic, color="#000000", char_positions=None,
            ))

            # Right column (value)
            elements.append(TextElement(
                text=val_line,
                bbox=BoundingBox(x0=mid_x + padding_x, y0=row_y,
                                 x1=x1 - padding_x, y1=row_y + font_size * 1.2),
                font_name=font_name, font_size_pt=font_size,
                bold=bold, italic=italic, color="#000000", char_positions=None,
            ))
    else:
        # Single-column fallback: one line per row
        row_height = block_height / len(lines)
        padding_x = 3.0
        padding_y = 2.0

        for row_idx, line in enumerate(lines):
            row_y = y0 + row_idx * row_height + padding_y
            elements.append(TextElement(
                text=line,
                bbox=BoundingBox(x0=x0 + padding_x, y0=row_y,
                                 x1=x1 - padding_x, y1=row_y + font_size * 1.2),
                font_name=font_name, font_size_pt=font_size,
                bold=bold, italic=italic, color="#000000", char_positions=None,
            ))

    return elements


def _add_table_lines(page_info, elements):
    """Add horizontal and vertical lines for table-like blocks.

    Detects blocks that are preceded by a caption and contain
    short newline-separated data (table cells). Draws grid lines.
    """
    from src.rendering.elements import LineElement

    blocks = sorted(page_info.text_blocks, key=lambda b: b.bbox.y0)

    for i, block in enumerate(blocks):
        # Identify table data blocks: paragraph type, preceded by a caption
        if block.block_type != "paragraph":
            continue

        # Check if previous block is a caption
        has_caption_above = False
        for prev in blocks:
            if prev.block_type == "caption" and prev.bbox.y1 <= block.bbox.y0 and (block.bbox.y0 - prev.bbox.y1) < 15:
                has_caption_above = True
                break

        if not has_caption_above:
            continue

        # This is a table data block — draw grid lines
        lines_in_block = [l for l in block.text_verbatim.split("\n") if l.strip()]
        if len(lines_in_block) < 2:
            continue

        x0 = block.bbox.x0
        x1 = block.bbox.x1
        y0 = block.bbox.y0
        y1 = block.bbox.y1
        line_height = (y1 - y0) / max(len(lines_in_block), 1)
        mid_x = (x0 + x1) / 2  # Column divider at midpoint

        # Top border
        elements.append(LineElement(x1=x0, y1=y0, x2=x1, y2=y0, color="#000000", width=0.75))
        # Bottom border
        elements.append(LineElement(x1=x0, y1=y1, x2=x1, y2=y1, color="#000000", width=0.75))
        # Left border
        elements.append(LineElement(x1=x0, y1=y0, x2=x0, y2=y1, color="#000000", width=0.75))
        # Right border
        elements.append(LineElement(x1=x1, y1=y0, x2=x1, y2=y1, color="#000000", width=0.75))
        # Column divider
        elements.append(LineElement(x1=mid_x, y1=y0, x2=mid_x, y2=y1, color="#000000", width=0.5))

        # Row dividers
        for row_idx in range(1, len(lines_in_block)):
            row_y = y0 + row_idx * line_height
            elements.append(LineElement(x1=x0, y1=row_y, x2=x1, y2=row_y, color="#888888", width=0.5))


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
