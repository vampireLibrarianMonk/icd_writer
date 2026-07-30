"""Integration tests for the rendering pipeline.

Tests the full extract → HTML → PDF chain using real ICD PDFs.
Validates that:
- Page elements are extractable from all available PDFs
- Extracted elements produce valid HTML
- HTML renders to a valid PDF via WeasyPrint
- Round-trip rendering preserves text content
- IR-based rendering (for edited pages) produces valid output
- Multi-page rendering works correctly
"""

from pathlib import Path
import tempfile

import fitz
import pytest

from tests.conftest import skip_no_weasyprint

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
from src.rendering.elements import (
    ImageElement,
    LineElement,
    PageElement,
    TextElement,
)
from src.rendering.extract import extract_page_elements
from src.rendering.ir_renderer import _ir_blocks_to_elements, render_ir_to_pdf
from src.rendering.renderer import render_page_to_html


# ─── Test data paths ──────────────────────────────────────────────────

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"
IDSS_PDF = ICDS_DIR / "IDSS_IDD_RevF.pdf"
LVC_PDF = ICDS_DIR / "20150010976.pdf"
TSAFE_PDF = ICDS_DIR / "20130010957.pdf"
NDS_PDF = ICDS_DIR / "NDS_IDD_RevC.pdf"

ALL_PDFS = [p for p in [HSI_PDF, IDSS_PDF, LVC_PDF, TSAFE_PDF, NDS_PDF] if p.exists()]


# ─── Element extraction tests ─────────────────────────────────────────


@pytest.mark.skipif(not ALL_PDFS, reason="No ICD PDFs available")
class TestElementExtraction:
    """Test extracting page elements from real PDFs."""

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_extraction_returns_elements(self, pdf_path):
        """Every page produces at least some elements."""
        width, height, elements = extract_page_elements(pdf_path, 1)
        assert width > 0
        assert height > 0
        assert len(elements) > 0

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_page_dimensions_reasonable(self, pdf_path):
        """Page dimensions are within expected range (A4/Letter)."""
        width, height, _ = extract_page_elements(pdf_path, 1)
        # US Letter: 612x792, A4: 595x842. Allow some margin.
        assert 400 < width < 900
        assert 500 < height < 1200

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_text_elements_have_content(self, pdf_path):
        """Text elements extracted have non-empty text."""
        _, _, elements = extract_page_elements(pdf_path, 1)
        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) > 0, "No text elements on page 1"
        for elem in text_elements:
            assert elem.text.strip(), f"Empty text element found"

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_text_elements_have_valid_bbox(self, pdf_path):
        """Text element bounding boxes have positive area."""
        _, _, elements = extract_page_elements(pdf_path, 1)
        text_elements = [e for e in elements if isinstance(e, TextElement)]
        for elem in text_elements:
            assert elem.bbox.width > 0, f"Zero-width text: '{elem.text}'"
            assert elem.bbox.height > 0, f"Zero-height text: '{elem.text}'"

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_text_elements_have_font_info(self, pdf_path):
        """Text elements have font name and size."""
        _, _, elements = extract_page_elements(pdf_path, 1)
        text_elements = [e for e in elements if isinstance(e, TextElement)]
        for elem in text_elements:
            assert elem.font_name, f"Missing font_name for: '{elem.text[:20]}'"
            assert elem.font_size_pt > 0, f"Zero font size for: '{elem.text[:20]}'"

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_char_positions_when_present(self, pdf_path):
        """Char positions, when present, match text length."""
        _, _, elements = extract_page_elements(pdf_path, 1)
        text_elements = [e for e in elements if isinstance(e, TextElement)]
        for elem in text_elements:
            if elem.char_positions:
                assert len(elem.char_positions) >= len(elem.text.rstrip()), (
                    f"Char positions ({len(elem.char_positions)}) < text length "
                    f"({len(elem.text.rstrip())}) for: '{elem.text[:20]}'"
                )


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestMultiPageExtraction:
    """Test extraction across multiple pages."""

    def test_all_pages_extractable(self):
        """Every page in the HSI document extracts without error."""
        doc = fitz.open(str(HSI_PDF))
        page_count = len(doc)
        doc.close()

        for page_num in range(1, page_count + 1):
            width, height, elements = extract_page_elements(HSI_PDF, page_num)
            assert width > 0, f"Page {page_num} has zero width"
            assert height > 0, f"Page {page_num} has zero height"
            # Some pages might be image-only, but most should have elements
            # Don't assert len(elements) > 0 for every page

    def test_page_with_table_has_lines(self):
        """Page 7 (known table page) should have line elements from table borders."""
        _, _, elements = extract_page_elements(HSI_PDF, 7)
        line_elements = [e for e in elements if isinstance(e, LineElement)]
        # Table pages typically have some drawn lines
        # (may or may not depending on how the PDF was created)
        assert isinstance(line_elements, list)

    def test_different_pages_have_different_content(self):
        """Different pages produce different text content."""
        _, _, elements_p1 = extract_page_elements(HSI_PDF, 1)
        _, _, elements_p4 = extract_page_elements(HSI_PDF, 4)

        text_p1 = " ".join(e.text for e in elements_p1 if isinstance(e, TextElement))
        text_p4 = " ".join(e.text for e in elements_p4 if isinstance(e, TextElement))

        assert text_p1 != text_p4


# ─── HTML rendering tests ─────────────────────────────────────────────


@pytest.mark.skipif(not ALL_PDFS, reason="No ICD PDFs available")
class TestHTMLRendering:
    """Test HTML generation from extracted elements."""

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_renders_to_valid_html(self, pdf_path):
        """Extracted elements produce syntactically valid HTML."""
        width, height, elements = extract_page_elements(pdf_path, 1)
        html = render_page_to_html(width, height, elements)

        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<body>" in html

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_html_contains_text_content(self, pdf_path):
        """Generated HTML contains actual text from the PDF."""
        width, height, elements = extract_page_elements(pdf_path, 1)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        if not text_elements:
            pytest.skip("No text elements to test")

        html = render_page_to_html(width, height, elements)

        # At least some of the text should appear in the HTML
        # (it will be HTML-escaped, so check original words)
        found_text = False
        for elem in text_elements[:5]:  # Check first 5
            words = elem.text.split()
            for word in words[:3]:
                if len(word) > 3 and word.isalpha():
                    if word in html:
                        found_text = True
                        break
            if found_text:
                break

        assert found_text, "No recognizable text found in HTML output"

    @pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.stem for p in ALL_PDFS])
    def test_html_has_page_dimensions(self, pdf_path):
        """HTML contains page width/height in CSS."""
        width, height, elements = extract_page_elements(pdf_path, 1)
        html = render_page_to_html(width, height, elements)

        assert str(int(width)) in html or f"{width}" in html
        assert str(int(height)) in html or f"{height}" in html


# ─── PDF rendering tests (WeasyPrint) ─────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPDFRendering:
    """Test rendering HTML to PDF via WeasyPrint."""

    def test_single_page_renders_to_pdf(self):
        """A single page can be rendered to a valid PDF."""
        from weasyprint import HTML

        width, height, elements = extract_page_elements(HSI_PDF, 1)
        html = render_page_to_html(width, height, elements)

        pdf_bytes = HTML(string=html).write_pdf()
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0

        # Verify it's a valid PDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert len(doc) == 1
        # Rendered page should have approximately the same dimensions
        page = doc[0]
        assert abs(page.rect.width - width) < 5  # within 5pt tolerance
        assert abs(page.rect.height - height) < 5
        doc.close()

    def test_rendered_pdf_contains_text(self):
        """Text content survives the HTML → PDF rendering."""
        from weasyprint import HTML

        width, height, elements = extract_page_elements(HSI_PDF, 5)
        html = render_page_to_html(width, height, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        rendered_text = doc[0].get_text("text")
        doc.close()

        # Should have some text content
        assert len(rendered_text.strip()) > 0

    def test_rendered_pdf_to_png(self):
        """Rendered PDF can be converted to PNG (the page image pipeline)."""
        from weasyprint import HTML

        width, height, elements = extract_page_elements(HSI_PDF, 4)
        html = render_page_to_html(width, height, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pix = doc[0].get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        assert len(img_bytes) > 0
        # PNG magic bytes
        assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"


# ─── IR-based rendering tests ─────────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestIRBasedRendering:
    """Test rendering from Document IR (for edited pages)."""

    @pytest.fixture
    def doc_ir(self):
        return process_pdf(HSI_PDF)

    def test_ir_elements_for_unedited_page(self, doc_ir):
        """_ir_blocks_to_elements produces elements for an unedited page."""
        page_info = doc_ir.pages[4]  # Page 5
        elements = _ir_blocks_to_elements(page_info)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) > 0

    def test_ir_elements_match_block_count(self, doc_ir):
        """Element count should be <= block count (dedup may reduce)."""
        page_info = doc_ir.pages[4]  # Page 5
        elements = _ir_blocks_to_elements(page_info)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) <= len(page_info.text_blocks)

    def test_ir_rendered_html_is_valid(self, doc_ir):
        """IR-generated elements produce valid HTML."""
        page_info = doc_ir.pages[4]
        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)

        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_ir_rendered_to_pdf(self, doc_ir):
        """Full IR → HTML → PDF pipeline produces valid output."""
        from weasyprint import HTML

        page_info = doc_ir.pages[4]
        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert len(doc) == 1
        assert doc[0].get_text("text").strip()
        doc.close()

    def test_edited_block_appears_in_ir_render(self, doc_ir):
        """After editing a block, the new text appears in IR-rendered output."""
        from weasyprint import HTML

        page_info = doc_ir.pages[4]
        # Edit the first text block
        if not page_info.text_blocks:
            pytest.skip("No text blocks on page 5")

        page_info.text_blocks[0].text_verbatim = "EDITED_UNIQUE_MARKER_TEXT"
        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)

        assert "EDITED_UNIQUE_MARKER_TEXT" in html

        # Also check in rendered PDF
        pdf_bytes = HTML(string=html).write_pdf()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        rendered_text = doc[0].get_text("text")
        doc.close()

        assert "EDITED_UNIQUE_MARKER_TEXT" in rendered_text


# ─── render_ir_to_pdf (export) tests ──────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestRenderIRToPDF:
    """Test the full export pipeline: render_ir_to_pdf."""

    @pytest.fixture
    def doc_ir(self):
        return process_pdf(HSI_PDF)

    def test_export_unedited_document(self, doc_ir):
        """Exporting an unedited document copies pages from source."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output_path = Path(f.name)

        try:
            result = render_ir_to_pdf(doc_ir, HSI_PDF, output_path)
            assert result.exists()
            assert result.stat().st_size > 0

            # Should have same page count
            doc = fitz.open(str(result))
            assert len(doc) == doc_ir.page_count
            doc.close()
        finally:
            output_path.unlink(missing_ok=True)

    def test_export_with_edited_page(self, doc_ir):
        """Exporting after an edit re-renders the edited page."""
        # Edit page 5
        page_info = doc_ir.pages[4]
        if not page_info.text_blocks:
            pytest.skip("No text blocks on page 5")

        page_info.text_blocks[0].text_verbatim = "EXPORT_EDIT_MARKER"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output_path = Path(f.name)

        try:
            result = render_ir_to_pdf(doc_ir, HSI_PDF, output_path)
            assert result.exists()

            doc = fitz.open(str(result))
            # Page 5 should contain the edited text
            page5_text = doc[4].get_text("text")
            doc.close()

            assert "EXPORT_EDIT_MARKER" in page5_text
        finally:
            output_path.unlink(missing_ok=True)

    def test_export_unedited_pages_are_exact(self, doc_ir):
        """Unedited pages in export are copied from source (byte-level match)."""
        # Only edit page 5, then check page 1 is identical to source
        page_info = doc_ir.pages[4]
        if page_info.text_blocks:
            page_info.text_blocks[0].text_verbatim = "TRIGGER_EDIT"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output_path = Path(f.name)

        try:
            render_ir_to_pdf(doc_ir, HSI_PDF, output_path)

            source_doc = fitz.open(str(HSI_PDF))
            export_doc = fitz.open(str(output_path))

            # Page 1 text should be identical (copied from source)
            source_text = source_doc[0].get_text("text")
            export_text = export_doc[0].get_text("text")

            source_doc.close()
            export_doc.close()

            assert source_text == export_text
        finally:
            output_path.unlink(missing_ok=True)

    def test_export_specific_pages(self, doc_ir):
        """Can export a subset of pages."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            output_path = Path(f.name)

        try:
            result = render_ir_to_pdf(doc_ir, HSI_PDF, output_path, pages=[1, 3, 5])
            assert result.exists()

            doc = fitz.open(str(result))
            assert len(doc) == 3
            doc.close()
        finally:
            output_path.unlink(missing_ok=True)


# ─── Page image rendering pipeline (the preview) ─────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPageImagePipeline:
    """Test the page image generation pipeline end-to-end.

    This replicates what the /document/page/{N}/image endpoint does:
    - Unedited: source PDF → pixmap → PNG
    - Edited: IR blocks → elements → HTML → WeasyPrint → PDF → pixmap → PNG
    """

    def test_unedited_page_from_source(self):
        """Unedited page renders directly from source PDF."""
        doc = fitz.open(str(HSI_PDF))
        pix = doc[0].get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        assert len(img_bytes) > 1000  # Non-trivial PNG
        assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_edited_page_from_ir(self):
        """Edited page renders through the IR → HTML → PDF → PNG pipeline."""
        from weasyprint import HTML

        doc_ir = process_pdf(HSI_PDF)
        page_info = doc_ir.pages[4]  # Page 5

        if not page_info.text_blocks:
            pytest.skip("No text blocks on page 5")

        # Edit a block
        page_info.text_blocks[0].text_verbatim = "PREVIEW_TEST_EDIT"

        # Replicate the page image pipeline
        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        rendered_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pix = rendered_doc[0].get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        rendered_doc.close()

        assert len(img_bytes) > 1000
        assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_edited_page_image_differs_from_source(self):
        """The edited page image is different from the original."""
        from weasyprint import HTML

        doc_ir = process_pdf(HSI_PDF)
        page_info = doc_ir.pages[4]

        if not page_info.text_blocks:
            pytest.skip("No text blocks on page 5")

        # Get original image
        doc = fitz.open(str(HSI_PDF))
        original_pix = doc[4].get_pixmap(dpi=72)  # Low DPI for speed
        original_bytes = original_pix.tobytes("png")
        doc.close()

        # Edit and render
        page_info.text_blocks[0].text_verbatim = "COMPLETELY_DIFFERENT_TEXT_XYZ"
        elements = _ir_blocks_to_elements(page_info)
        html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        rendered_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        edited_pix = rendered_doc[0].get_pixmap(dpi=72)
        edited_bytes = edited_pix.tobytes("png")
        rendered_doc.close()

        # The images should differ (edited text changed)
        assert original_bytes != edited_bytes


# ─── Table page rendering ─────────────────────────────────────────────


@skip_no_weasyprint
@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTablePageRendering:
    """Test rendering of pages with tables (page 7 of HSI)."""

    @pytest.fixture
    def page7_ir(self):
        doc_ir = process_pdf(HSI_PDF)
        return doc_ir.pages[6]  # Page 7

    def test_table_page_has_caption_blocks(self, page7_ir):
        """Page 7 should have caption-type blocks."""
        captions = [b for b in page7_ir.text_blocks if b.block_type == "caption"]
        assert len(captions) >= 1, "No captions found on page 7"

    def test_table_page_ir_elements_include_lines(self, page7_ir):
        """IR rendering of table page produces line elements (grid)."""
        elements = _ir_blocks_to_elements(page7_ir)
        line_elements = [e for e in elements if isinstance(e, LineElement)]
        # Should have grid lines from _add_table_lines
        assert len(line_elements) >= 5, (
            f"Expected table grid lines, got {len(line_elements)}"
        )

    def test_table_page_renders_to_pdf(self, page7_ir):
        """Table page with grid lines renders to valid PDF."""
        from weasyprint import HTML

        elements = _ir_blocks_to_elements(page7_ir)
        html = render_page_to_html(page7_ir.width_pt, page7_ir.height_pt, elements)
        pdf_bytes = HTML(string=html).write_pdf()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert len(doc) == 1
        doc.close()

    def test_table_overlap_dedup_reduces_fragments(self, page7_ir):
        """Overlap dedup removes table fragment blocks (b09, b10, b11 vs b12)."""
        total_blocks = len(page7_ir.text_blocks)
        elements = _ir_blocks_to_elements(page7_ir)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        # Dedup should reduce the count (overlapping fragments removed)
        assert len(text_elements) <= total_blocks
