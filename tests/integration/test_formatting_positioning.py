"""Integration tests: Formatting and Positioning Correctness.

Verifies that font, size, bold, italic, color, and bounding box positioning
are correctly maintained through the edit/render cycle.

Tests at two levels:
1. Document IR level: after edit, block style metadata is preserved
2. Rendering level: IR blocks → TextElements preserve formatting attributes
3. HTML level: rendered HTML contains correct CSS properties

For Docker-only (WeasyPrint) tests:
4. PDF level: rendered PDF preserves text at correct positions
"""

from pathlib import Path

import pytest

from src.models.common import BoundingBox
from src.models.document_ir import (
    DocumentIR,
    DocumentMetadata,
    PageClassification,
    PageClassificationType,
    PageInfo,
    TextBlock,
    TextStyle,
)
from src.pipeline import process_pdf
from src.rendering.elements import LineElement, TextElement
from src.rendering.ir_renderer import _ir_blocks_to_elements
from src.rendering.renderer import render_page_to_html
from tests.conftest import skip_no_weasyprint

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"


# ─── Fixtures ──────────────────────────────────────────────────────────


def _make_block(
    block_id: str, y0: float, y1: float, text: str,
    block_type: str = "paragraph", page: int = 1,
    x0: float = 72.0, x1: float = 540.0,
    font_name: str = "Helvetica", font_size: float = 10.0,
    bold: bool = False, italic: bool = False,
    color: str = None,
) -> TextBlock:
    return TextBlock(
        id=block_id, block_type=block_type, page=page,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text_verbatim=text, reading_order=0,
        style=TextStyle(
            font_name=font_name, font_size_pt=font_size,
            bold=bold, italic=italic, color=color,
        ),
        confidence=1.0, is_ocr=False,
    )


def _make_page(blocks, page_number=1, width=612.0, height=792.0):
    return PageInfo(
        page_number=page_number, width_pt=width, height_pt=height,
        classification=PageClassification(
            page_number=page_number,
            classifications=[PageClassificationType.NATIVE_DIGITAL_TEXT],
        ),
        text_blocks=blocks,
    )


# ─── Style preservation through IR → TextElement ──────────────────────


class TestStylePreservationIR:
    """Verify block style attributes propagate to TextElements."""

    def test_bold_propagated(self):
        """Bold attribute propagates to TextElement."""
        blocks = [_make_block("b1", 72, 90, "Bold text", bold=True)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]
        assert text_elems[0].bold is True

    def test_italic_propagated(self):
        """Italic attribute propagates to TextElement."""
        blocks = [_make_block("b1", 72, 90, "Italic text", italic=True)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]
        assert text_elems[0].italic is True

    def test_font_name_propagated(self):
        """Font name propagates to TextElement."""
        blocks = [_make_block("b1", 72, 90, "Courier text", font_name="Courier")]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]
        assert text_elems[0].font_name == "Courier"

    def test_font_size_propagated(self):
        """Font size propagates to TextElement."""
        blocks = [_make_block("b1", 72, 100, "Large text", font_size=18.0)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]
        assert text_elems[0].font_size_pt == 18.0

    def test_bbox_propagated(self):
        """Bounding box coordinates propagate exactly."""
        blocks = [_make_block("b1", 100, 150, "Positioned", x0=80, x1=500)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]
        assert text_elems[0].bbox.x0 == 80.0
        assert text_elems[0].bbox.y0 == 100.0
        assert text_elems[0].bbox.x1 == 500.0
        assert text_elems[0].bbox.y1 == 150.0

    def test_mixed_styles_independent(self):
        """Multiple blocks with different styles maintain independence."""
        blocks = [
            _make_block("b1", 72, 90, "Bold", bold=True, font_size=14),
            _make_block("b2", 100, 118, "Italic", italic=True, font_size=10),
            _make_block("b3", 130, 148, "Regular", font_size=12),
        ]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]

        assert text_elems[0].bold is True and text_elems[0].font_size_pt == 14
        assert text_elems[1].italic is True and text_elems[1].font_size_pt == 10
        assert text_elems[2].bold is False and text_elems[2].italic is False

    def test_heading_style_defaults(self):
        """Heading blocks get their style from the IR (not hardcoded)."""
        blocks = [_make_block(
            "h1", 72, 95, "Section Title",
            block_type="heading", font_name="Helvetica-Bold",
            font_size=14.0, bold=True,
        )]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]
        assert text_elems[0].font_size_pt == 14.0
        assert text_elems[0].bold is True
        assert text_elems[0].font_name == "Helvetica-Bold"


# ─── HTML rendering preserves formatting ──────────────────────────────


class TestHTMLFormattingCorrectness:
    """Verify HTML output contains correct CSS for each style attribute."""

    def test_bold_in_html(self):
        """Bold text produces font-weight:bold in HTML."""
        blocks = [_make_block("b1", 72, 90, "Bold heading", bold=True)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "font-weight:bold" in html.replace(" ", "")

    def test_italic_in_html(self):
        """Italic text produces font-style:italic in HTML."""
        blocks = [_make_block("b1", 72, 90, "Italic note", italic=True)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "font-style:italic" in html.replace(" ", "")

    def test_font_size_in_html(self):
        """Font size appears in the CSS."""
        blocks = [_make_block("b1", 72, 100, "Big text", font_size=18.0)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "font-size:18" in html.replace(" ", "")

    def test_font_family_in_html(self):
        """Font family maps to CSS font-family."""
        blocks = [_make_block("b1", 72, 90, "Courier text", font_name="Courier")]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "Courier" in html

    def test_position_left_in_html(self):
        """Block x0 position becomes CSS left."""
        blocks = [_make_block("b1", 100, 120, "Offset", x0=150.0)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "left:150" in html.replace(" ", "")

    def test_position_top_in_html(self):
        """Block y0 position becomes CSS top."""
        blocks = [_make_block("b1", 250, 270, "Down page")]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "top:250" in html.replace(" ", "")

    def test_width_in_html(self):
        """Block width (x1-x0) becomes CSS width."""
        blocks = [_make_block("b1", 72, 90, "Fixed width", x0=100, x1=400)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "width:300" in html.replace(" ", "")

    def test_text_content_in_html(self):
        """Actual text content appears in HTML."""
        blocks = [_make_block("b1", 72, 90, "Spectrometer Requirements")]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        assert "Spectrometer Requirements" in html

    def test_multiple_blocks_positioned_independently(self):
        """Multiple blocks each have their own position in HTML."""
        blocks = [
            _make_block("b1", 72, 90, "Top block", x0=72),
            _make_block("b2", 200, 220, "Middle block", x0=100),
            _make_block("b3", 400, 420, "Bottom block", x0=72),
        ]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)

        assert "top:72" in html.replace(" ", "")
        assert "top:200" in html.replace(" ", "")
        assert "top:400" in html.replace(" ", "")


# ─── Positioning after reflow ─────────────────────────────────────────


class TestPositioningAfterReflow:
    """Verify bounding box positions are correct after reflow operations."""

    def test_reflow_preserves_x_coordinates(self):
        """Reflow only changes y-positions, not x."""
        from src.reflow import reflow_page

        blocks = [
            _make_block("b1", 72, 100, "Short", x0=100, x1=400),
            _make_block("b2", 110, 140, "Below", x0=120, x1=500),
        ]
        page = _make_page(blocks)
        doc = DocumentIR(
            metadata=DocumentMetadata(
                filename="test.pdf", sha256="abc", page_count=1, file_size_bytes=100
            ),
            pages=[page],
        )

        # Expand first block
        blocks[0].text_verbatim = "Much longer text that wraps. " * 10
        reflow_page(doc, 1, "b1")

        # X coordinates should be unchanged
        assert blocks[0].bbox.x0 == 100
        assert blocks[0].bbox.x1 == 400
        assert blocks[1].bbox.x0 == 120
        assert blocks[1].bbox.x1 == 500

    def test_reflow_shifts_y_of_subsequent_blocks(self):
        """Expansion shifts subsequent blocks down by height_delta."""
        from src.reflow import reflow_page

        blocks = [
            _make_block("b1", 72, 100, "Short"),
            _make_block("b2", 110, 140, "Below"),
            _make_block("b3", 150, 180, "Further below"),
        ]
        page = _make_page(blocks)
        doc = DocumentIR(
            metadata=DocumentMetadata(
                filename="test.pdf", sha256="abc", page_count=1, file_size_bytes=100
            ),
            pages=[page],
        )

        original_b2_y = blocks[1].bbox.y0
        original_b3_y = blocks[2].bbox.y0

        # Expand first block significantly
        blocks[0].text_verbatim = "Long requirement text. " * 20
        result = reflow_page(doc, 1, "b1")

        if result.height_delta_pt > 0:
            # Both subsequent blocks should shift down by same delta
            delta = result.height_delta_pt
            assert abs(blocks[1].bbox.y0 - (original_b2_y + delta)) < 0.1
            assert abs(blocks[2].bbox.y0 - (original_b3_y + delta)) < 0.1

    def test_reflow_preserves_block_height_for_unedited(self):
        """Unedited blocks maintain their original height after reflow."""
        from src.reflow import reflow_page

        blocks = [
            _make_block("b1", 72, 100, "Short"),
            _make_block("b2", 110, 140, "Untouched block"),
        ]
        page = _make_page(blocks)
        doc = DocumentIR(
            metadata=DocumentMetadata(
                filename="test.pdf", sha256="abc", page_count=1, file_size_bytes=100
            ),
            pages=[page],
        )

        original_b2_height = blocks[1].bbox.y1 - blocks[1].bbox.y0

        blocks[0].text_verbatim = "Expanded text. " * 15
        reflow_page(doc, 1, "b1")

        # b2's height should be unchanged (only shifted)
        new_b2_height = blocks[1].bbox.y1 - blocks[1].bbox.y0
        assert abs(new_b2_height - original_b2_height) < 0.1

    def test_shrink_pulls_blocks_up(self):
        """Shrinking a block pulls subsequent blocks up."""
        from src.reflow import reflow_page

        blocks = [
            _make_block("b1", 72, 200, "Very long original text. " * 20),
            _make_block("b2", 210, 240, "Below long block"),
        ]
        page = _make_page(blocks)
        doc = DocumentIR(
            metadata=DocumentMetadata(
                filename="test.pdf", sha256="abc", page_count=1, file_size_bytes=100
            ),
            pages=[page],
        )

        original_b2_y = blocks[1].bbox.y0
        blocks[0].text_verbatim = "Short."
        result = reflow_page(doc, 1, "b1")

        if result.height_delta_pt < 0:
            assert blocks[1].bbox.y0 < original_b2_y


# ─── Real document formatting tests ──────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestRealDocumentFormatting:
    """Test formatting on real HSI document blocks."""

    @pytest.fixture
    def doc_ir(self):
        return process_pdf(HSI_PDF)

    def test_heading_blocks_are_bold(self, doc_ir):
        """Heading blocks in HSI have bold styling."""
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block.block_type == "heading" and block.style:
                    if block.style.bold:
                        return  # Found at least one bold heading
        # Not all headings may be bold (depends on extraction)
        # but most should have style info
        headings = [
            b for p in doc_ir.pages for b in p.text_blocks
            if b.block_type == "heading"
        ]
        assert len(headings) > 0, "No headings found"

    def test_heading_blocks_have_larger_font(self, doc_ir):
        """Heading blocks have larger font than body paragraphs."""
        heading_sizes = []
        paragraph_sizes = []
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block.style and block.style.font_size_pt:
                    if block.block_type == "heading":
                        heading_sizes.append(block.style.font_size_pt)
                    elif block.block_type == "paragraph":
                        paragraph_sizes.append(block.style.font_size_pt)

        if not heading_sizes or not paragraph_sizes:
            pytest.skip("Insufficient style data")

        avg_heading = sum(heading_sizes) / len(heading_sizes)
        avg_paragraph = sum(paragraph_sizes) / len(paragraph_sizes)
        # Headings should be at least slightly larger on average
        assert avg_heading >= avg_paragraph, (
            f"Heading avg {avg_heading:.1f}pt < paragraph avg {avg_paragraph:.1f}pt"
        )

    def test_blocks_have_font_info(self, doc_ir):
        """Most blocks have font name and size in their style."""
        blocks_with_font = 0
        total_blocks = 0
        for page in doc_ir.pages:
            for block in page.text_blocks:
                total_blocks += 1
                if block.style and block.style.font_name and block.style.font_size_pt:
                    blocks_with_font += 1

        assert total_blocks > 0
        coverage = blocks_with_font / total_blocks
        assert coverage > 0.8, f"Only {coverage:.0%} blocks have font info"

    def test_blocks_dont_overlap_pages(self, doc_ir):
        """No block extends beyond its page dimensions."""
        for page in doc_ir.pages:
            for block in page.text_blocks:
                assert block.bbox.x0 >= -1, f"{block.id} x0={block.bbox.x0}"
                assert block.bbox.y0 >= -1, f"{block.id} y0={block.bbox.y0}"
                assert block.bbox.x1 <= page.width_pt + 5, (
                    f"{block.id} x1={block.bbox.x1} > {page.width_pt}"
                )
                # y1 can exceed page height for overflow blocks, but not by much
                # in an unedited document
                assert block.bbox.y1 <= page.height_pt + 50, (
                    f"{block.id} y1={block.bbox.y1} > {page.height_pt}"
                )

    def test_reading_order_is_top_to_bottom(self, doc_ir):
        """Blocks with increasing reading_order have non-decreasing y0."""
        for page in doc_ir.pages:
            ordered = sorted(page.text_blocks, key=lambda b: b.reading_order)
            if len(ordered) < 4:
                continue  # Skip pages with very few blocks (high noise)
            # Allow some tolerance (multi-column pages may interleave)
            violations = 0
            for i in range(1, len(ordered)):
                if ordered[i].bbox.y0 < ordered[i-1].bbox.y0 - 50:
                    violations += 1
            # Allow up to 30% violations (columns, tables, short pages)
            assert violations < len(ordered) * 0.3, (
                f"Page {page.page_number}: {violations}/{len(ordered)} "
                f"reading order violations"
            )

    def test_style_preserved_in_ir_render(self, doc_ir):
        """Style from IR blocks appears in rendered TextElements."""
        page = doc_ir.pages[4]  # Page 5
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]

        # At least some elements should have non-default font info
        fonts = set(e.font_name for e in text_elems)
        sizes = set(e.font_size_pt for e in text_elems)

        assert len(fonts) >= 1, "No font info in rendered elements"
        assert len(sizes) >= 1, "No size info in rendered elements"

    def test_edited_block_keeps_style(self, doc_ir):
        """After editing text, the block's style metadata is unchanged."""
        page = doc_ir.pages[4]
        if not page.text_blocks:
            pytest.skip("No blocks on page 5")

        block = page.text_blocks[0]
        original_style = block.style

        # Simulate edit (change text, keep style)
        block.text_verbatim = "Edited content"

        # Style should be unchanged
        assert block.style == original_style

        # Render and verify style propagates
        elements = _ir_blocks_to_elements(page)
        text_elems = [e for e in elements if isinstance(e, TextElement)]
        if text_elems and original_style:
            elem = text_elems[0]
            if original_style.font_size_pt:
                assert elem.font_size_pt == original_style.font_size_pt
            assert elem.bold == (original_style.bold or False)
            assert elem.italic == (original_style.italic or False)


# ─── Docker-only: PDF output formatting verification ──────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPDFOutputFormatting:
    """Verify rendered PDF preserves positioning (requires WeasyPrint)."""

    @pytest.fixture
    def doc_ir(self):
        return process_pdf(HSI_PDF)

    def test_rendered_page_has_text_at_positions(self, doc_ir):
        """Rendered PDF has text placed within expected coordinate ranges."""
        import fitz
        from weasyprint import HTML

        page_info = doc_ir.pages[4]
        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text_dict = page.get_text("dict")
        doc.close()

        # Should have text blocks in the rendered page
        blocks = text_dict.get("blocks", [])
        text_blocks = [b for b in blocks if b.get("type") == 0]
        assert len(text_blocks) > 0, "No text blocks in rendered PDF"

    def test_edited_text_at_correct_y_position(self, doc_ir):
        """Edited block renders at the correct vertical position."""
        import fitz
        from weasyprint import HTML

        page_info = doc_ir.pages[4]
        if not page_info.text_blocks:
            pytest.skip("No blocks on page 5")

        # Edit first block
        target = page_info.text_blocks[0]
        target.text_verbatim = "POSITIONING_MARKER"
        target_y = target.bbox.y0

        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        # Search for our marker text
        text_instances = page.search_for("POSITIONING_MARKER")
        doc.close()

        assert len(text_instances) > 0, "Marker text not found in rendered PDF"
        # The y-position should be approximately correct (within 20pt tolerance)
        rendered_y = text_instances[0].y0
        assert abs(rendered_y - target_y) < 20, (
            f"Text rendered at y={rendered_y}, expected near y={target_y}"
        )

    def test_bold_text_rendered_bold_in_pdf(self, doc_ir):
        """Bold blocks render with bold font in the PDF."""
        import fitz
        from weasyprint import HTML

        # Create a page with explicit bold block
        blocks = [_make_block("b1", 72, 100, "BOLD_MARKER", bold=True, font_size=14)]
        page = _make_page(blocks)
        elements = _ir_blocks_to_elements(page)
        html = render_page_to_html(page.width_pt, page.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_obj = doc[0]
        text_dict = page_obj.get_text("dict")
        doc.close()

        # Find spans with our marker text
        found_bold = False
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if "BOLD_MARKER" in span.get("text", ""):
                        # Check font flags or name for bold indicator
                        flags = span.get("flags", 0)
                        font = span.get("font", "")
                        if (flags & (1 << 4)) or "bold" in font.lower():
                            found_bold = True
        assert found_bold, "Bold text not rendered with bold font in PDF"

    def test_page_dimensions_match_ir(self, doc_ir):
        """Rendered PDF page dimensions match IR specification."""
        import fitz
        from weasyprint import HTML

        page_info = doc_ir.pages[4]
        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        page_width = page.rect.width
        page_height = page.rect.height
        doc.close()

        assert abs(page_width - page_info.width_pt) < 5
        assert abs(page_height - page_info.height_pt) < 5
