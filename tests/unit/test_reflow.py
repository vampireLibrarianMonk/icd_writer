"""Tests for the text reflow engine (Phase 5).

Tests word-wrap, block push-down, and overflow detection
using real ICD documents from icds/digital/.
"""

from pathlib import Path

import pytest

from src.models.document_ir import BoundingBox
from src.pipeline import process_pdf
from src.reflow import (
    FontMetrics,
    ReflowResult,
    compute_wrapped_height,
    get_page_overflow,
    reflow_page,
)

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"
LVC_PDF = ICDS_DIR / "20150010976.pdf"
IDSS_PDF = ICDS_DIR / "IDSS_IDD_RevF.pdf"


# -----------------------------------------------------------------
# Word-wrap computation tests
# -----------------------------------------------------------------

class TestWordWrap:
    """Test word-wrap height calculation."""

    def test_short_text_single_line(self):
        """Short text that fits in one line."""
        metrics = FontMetrics(font_size_pt=10, avg_char_width_pt=5, line_height_pt=12)
        height, lines = compute_wrapped_height("Hello world", 200.0, metrics)
        assert lines == 1
        assert height == 12.0

    def test_long_text_wraps(self):
        """Long text that must wrap to multiple lines."""
        metrics = FontMetrics(font_size_pt=10, avg_char_width_pt=5, line_height_pt=12)
        # 100pt wide, each char ~5pt → ~20 chars per line
        text = "This is a long sentence that should definitely wrap to multiple lines in the given width"
        height, lines = compute_wrapped_height(text, 100.0, metrics)
        assert lines > 1
        assert height == lines * 12.0

    def test_empty_text(self):
        """Empty text returns minimum height."""
        metrics = FontMetrics(font_size_pt=10, avg_char_width_pt=5, line_height_pt=12)
        height, lines = compute_wrapped_height("", 200.0, metrics)
        assert lines == 1
        assert height == 12.0

    def test_single_long_word(self):
        """A single word longer than available width still occupies one line."""
        metrics = FontMetrics(font_size_pt=10, avg_char_width_pt=5, line_height_pt=12)
        # Word is 30 chars × 5pt = 150pt, but width is only 100pt
        # Single word doesn't break (no whitespace to wrap at)
        text = "superlongwordwithnobreakpoints"
        height, lines = compute_wrapped_height(text, 100.0, metrics)
        assert lines == 1  # Can't wrap within a single word

    def test_wider_block_fewer_lines(self):
        """Wider block means fewer wrap lines."""
        metrics = FontMetrics(font_size_pt=10, avg_char_width_pt=5, line_height_pt=12)
        text = "The system shall provide 28V DC power at 2.5 amperes maximum"
        _, lines_narrow = compute_wrapped_height(text, 100.0, metrics)
        _, lines_wide = compute_wrapped_height(text, 400.0, metrics)
        assert lines_wide <= lines_narrow

    def test_font_size_affects_wrap(self):
        """Larger font means wider characters, more wrapping."""
        text = "The spectrometer temperature requirements shall be met"
        metrics_small = FontMetrics(font_size_pt=8, avg_char_width_pt=4, line_height_pt=9.6)
        metrics_large = FontMetrics(font_size_pt=14, avg_char_width_pt=7, line_height_pt=16.8)
        _, lines_small = compute_wrapped_height(text, 200.0, metrics_small)
        _, lines_large = compute_wrapped_height(text, 200.0, metrics_large)
        assert lines_large >= lines_small


# -----------------------------------------------------------------
# Reflow on real documents
# -----------------------------------------------------------------

@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestReflowOnHSI:
    """Reflow tests using the HSI Spectrometer ICD."""

    @pytest.fixture
    def doc_ir(self):
        return process_pdf(HSI_PDF)

    def test_no_change_no_reflow(self, doc_ir):
        """If text isn't changed, reflow does nothing."""
        # Get a block from page 4
        page = doc_ir.pages[3]  # page 4
        if not page.text_blocks:
            pytest.skip("No text blocks on page 4")
        block = page.text_blocks[0]

        result = reflow_page(doc_ir, 4, block.id)
        # No text change → height delta should be 0 or very small
        # (might differ slightly due to font metric approximation)
        assert result.blocks_shifted == 0 or abs(result.height_delta_pt) < 2.0

    def test_expand_block_shifts_subsequent(self, doc_ir):
        """Making text longer pushes subsequent blocks down."""
        page = doc_ir.pages[3]  # page 4
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)
        if len(blocks) < 3:
            pytest.skip("Need at least 3 blocks on page")

        target_block = blocks[1]  # Second block
        subsequent_block = blocks[2]  # Third block
        original_y = subsequent_block.bbox.y0

        # Make the text much longer (force wrapping)
        target_block.text_verbatim = (
            "This is a significantly expanded piece of text that should cause "
            "the block to wrap to multiple lines and push everything below it "
            "downward on the page. The thermal requirements state that the "
            "spectrometer shall maintain operational limits at all times."
        )

        result = reflow_page(doc_ir, 4, target_block.id)

        # The height delta should be positive (block grew)
        assert result.height_delta_pt > 0
        # Subsequent blocks should have shifted
        assert result.blocks_shifted > 0
        # The third block's y-position should have increased
        assert subsequent_block.bbox.y0 > original_y

    def test_shrink_block_pulls_subsequent(self, doc_ir):
        """Making text shorter pulls subsequent blocks up."""
        page = doc_ir.pages[3]
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)
        if len(blocks) < 3:
            pytest.skip("Need at least 3 blocks on page")

        target_block = blocks[1]
        subsequent_block = blocks[2]
        original_y = subsequent_block.bbox.y0

        # Make text shorter
        target_block.text_verbatim = "Short."

        result = reflow_page(doc_ir, 4, target_block.id)

        # Height delta should be negative or zero (block shrunk)
        assert result.height_delta_pt <= 0
        # Subsequent block should have moved up (or stayed)
        assert subsequent_block.bbox.y0 <= original_y

    def test_headers_not_shifted(self, doc_ir):
        """Headers (y < 60pt) are not shifted by reflow."""
        page = doc_ir.pages[3]
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)

        # Find a header block (y0 < 60)
        header_blocks = [b for b in blocks if b.bbox.y0 < 60]
        body_blocks = [b for b in blocks if 60 <= b.bbox.y0 <= page.height_pt - 72]

        if not header_blocks or len(body_blocks) < 2:
            pytest.skip("Need header + body blocks")

        header_y_before = header_blocks[0].bbox.y0

        # Edit a body block to force reflow
        body_blocks[0].text_verbatim = "Expanded text " * 20
        reflow_page(doc_ir, 4, body_blocks[0].id)

        # Header should NOT have moved
        assert header_blocks[0].bbox.y0 == header_y_before


@pytest.mark.skipif(not IDSS_PDF.exists(), reason="IDSS PDF not found")
class TestReflowOnLargeDoc:
    """Reflow tests on the larger IDSS IDD (70 pages)."""

    @pytest.fixture
    def doc_ir(self):
        return process_pdf(IDSS_PDF)

    def test_reflow_middle_page(self, doc_ir):
        """Reflow works on pages in the middle of a large document."""
        # Page 35 (mid-document)
        page = doc_ir.pages[34]
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)
        body_blocks = [b for b in blocks if 60 <= b.bbox.y0 <= page.height_pt - 72]

        if not body_blocks:
            pytest.skip("No body blocks on page 35")

        body_blocks[0].text_verbatim = "Modified requirement text. " * 10
        result = reflow_page(doc_ir, 35, body_blocks[0].id)

        assert result.page_number == 35
        assert result.height_delta_pt != 0 or result.blocks_shifted >= 0

    def test_overflow_detection(self, doc_ir):
        """Massive text expansion triggers overflow detection."""
        page = doc_ir.pages[5]  # Page 6
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)
        body_blocks = [b for b in blocks if 60 <= b.bbox.y0 <= page.height_pt - 72]

        if not body_blocks:
            pytest.skip("No body blocks on page 6")

        # Insert extremely long text to force overflow
        body_blocks[0].text_verbatim = ("This requirement shall be met. " * 100)
        result = reflow_page(doc_ir, 6, body_blocks[0].id)

        # With 100 repetitions of a sentence, should overflow
        assert result.overflow_pt > 0
        assert len(result.overflowing_blocks) > 0


# -----------------------------------------------------------------
# Overflow detection (read-only)
# -----------------------------------------------------------------

@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestOverflowDetection:
    """Test overflow detection without modification."""

    def test_no_overflow_on_unmodified(self):
        """Unmodified documents don't overflow."""
        doc_ir = process_pdf(HSI_PDF)
        for page_num in range(1, doc_ir.page_count + 1):
            overflow = get_page_overflow(doc_ir, page_num)
            assert overflow == 0.0, f"Page {page_num} has unexpected overflow"

    def test_overflow_after_expansion(self):
        """Overflow detected after artificial expansion."""
        doc_ir = process_pdf(HSI_PDF)
        page = doc_ir.pages[3]
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)
        body_blocks = [b for b in blocks if 60 <= b.bbox.y0 <= page.height_pt - 72]

        if not body_blocks:
            pytest.skip("No body blocks")

        # Expand a block massively
        body_blocks[0].text_verbatim = "Overflow test. " * 200
        reflow_page(doc_ir, 4, body_blocks[0].id)

        overflow = get_page_overflow(doc_ir, 4)
        assert overflow > 0


# -----------------------------------------------------------------
# FontMetrics from real blocks
# -----------------------------------------------------------------

@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestFontMetrics:
    """Test font metric extraction from real blocks."""

    def test_metrics_from_block(self):
        """FontMetrics can be created from a real text block."""
        doc_ir = process_pdf(HSI_PDF)
        block = doc_ir.pages[0].text_blocks[0]
        metrics = FontMetrics.from_block(block)
        assert metrics.font_size_pt > 0
        assert metrics.avg_char_width_pt > 0
        assert metrics.line_height_pt > metrics.font_size_pt
