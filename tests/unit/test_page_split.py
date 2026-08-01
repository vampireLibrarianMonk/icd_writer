"""Unit tests for page split (overflow → new page creation).

Tests the Phase 6 page extension logic:
- split_page_on_overflow moves overflowing paragraphs to a new page
- reflow_and_split combines reflow + split in one call
- Page renumbering works correctly after insertion
- Headers/footers are NOT moved
- Non-paragraph blocks (headings) are NOT moved in Phase 1
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
from src.reflow import (
    PageSplitResult,
    ReflowResult,
    reflow_and_split,
    reflow_page,
    split_page_on_overflow,
)

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"


def _make_doc_ir(pages: list[PageInfo]) -> DocumentIR:
    """Create a minimal DocumentIR for testing."""
    return DocumentIR(
        metadata=DocumentMetadata(
            filename="test.pdf",
            sha256="abc123",
            page_count=len(pages),
            file_size_bytes=1000,
        ),
        pages=pages,
    )


def _make_page(page_number: int, blocks: list[TextBlock], width: float = 612.0, height: float = 792.0) -> PageInfo:
    """Create a PageInfo with given blocks."""
    return PageInfo(
        page_number=page_number,
        width_pt=width,
        height_pt=height,
        classification=PageClassification(
            page_number=page_number,
            classifications=[PageClassificationType.NATIVE_DIGITAL_TEXT],
            native_text_available=True,
        ),
        text_blocks=blocks,
    )


def _make_block(block_id: str, y0: float, y1: float, text: str = "Test text",
                block_type: str = "paragraph", page: int = 1) -> TextBlock:
    """Create a TextBlock at a given vertical position."""
    return TextBlock(
        id=block_id,
        block_type=block_type,
        page=page,
        bbox=BoundingBox(x0=72.0, y0=y0, x1=540.0, y1=y1),
        text_verbatim=text,
        reading_order=0,
        style=TextStyle(font_name="Helvetica", font_size_pt=10.0, bold=False, italic=False),
        confidence=1.0,
        is_ocr=False,
    )


# -----------------------------------------------------------------
# split_page_on_overflow tests
# -----------------------------------------------------------------

class TestSplitPageOnOverflow:
    """Test split_page_on_overflow directly."""

    def test_no_overflow_no_split(self):
        """If no blocks overflow, no split occurs."""
        blocks = [
            _make_block("b1", 72, 100, "First paragraph"),
            _make_block("b2", 110, 140, "Second paragraph"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)
        assert result.split_occurred is False
        assert doc.page_count == 1

    def test_overflow_creates_new_page(self):
        """Blocks past the bottom margin get moved to a new page."""
        # Page height 792, bottom margin 72 → content_bottom = 720
        blocks = [
            _make_block("b1", 72, 200, "First paragraph (stays)"),
            _make_block("b2", 400, 600, "Second paragraph (stays)"),
            _make_block("b3", 725, 780, "Third paragraph (overflows)"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 1
        assert result.new_page_number == 2
        assert doc.page_count == 2

        # Original page should have 2 blocks
        assert len(doc.pages[0].text_blocks) == 2
        # New page should have 1 block
        assert len(doc.pages[1].text_blocks) == 1
        # The moved block starts at the top margin
        moved_block = doc.pages[1].text_blocks[0]
        assert moved_block.bbox.y0 == 72.0  # top margin
        assert moved_block.page == 2

    def test_multiple_blocks_overflow(self):
        """Multiple overflowing blocks all move to the new page."""
        blocks = [
            _make_block("b1", 72, 200, "Stays on page 1"),
            _make_block("b2", 721, 738, "Overflows - first"),
            _make_block("b3", 725, 740, "Overflows - second"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 2
        assert doc.page_count == 2
        assert len(doc.pages[0].text_blocks) == 1
        assert len(doc.pages[1].text_blocks) == 2

    def test_straddling_block_moves(self):
        """A block that straddles the boundary (starts above, ends below) gets moved."""
        # content_bottom = 720
        blocks = [
            _make_block("b1", 72, 200, "Stays"),
            _make_block("b2", 700, 750, "Straddles boundary"),  # starts at 700, ends at 750
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 1
        assert len(doc.pages[0].text_blocks) == 1
        assert len(doc.pages[1].text_blocks) == 1

    def test_headers_not_moved(self):
        """Header blocks (y0 < 60) are never moved even if technically overflow."""
        blocks = [
            _make_block("header", 10, 40, "Page Header", block_type="header"),
            _make_block("b1", 72, 200, "Body content"),
            _make_block("b2", 725, 780, "Overflows"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        # Header stays on page 1
        page1_types = [b.block_type for b in doc.pages[0].text_blocks]
        assert "header" in page1_types
        assert len(doc.pages[0].text_blocks) == 2  # header + b1

    def test_heading_blocks_moved_on_overflow(self):
        """Heading blocks ARE moved when they overflow."""
        blocks = [
            _make_block("b1", 72, 200, "Body paragraph"),
            _make_block("h1", 725, 740, "3.5 Section Title", block_type="heading"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 1

    def test_new_page_has_correct_dimensions(self):
        """The new page inherits width and height from the source page."""
        blocks = [
            _make_block("b1", 72, 200, "Stays"),
            _make_block("b2", 725, 780, "Overflows"),
        ]
        page = _make_page(1, blocks, width=595.0, height=842.0)  # A4
        doc = _make_doc_ir([page])

        split_page_on_overflow(doc, 1)

        assert doc.pages[1].width_pt == 595.0
        assert doc.pages[1].height_pt == 842.0

    def test_moved_blocks_preserve_horizontal_position(self):
        """Blocks keep their x0/x1 coordinates when moved."""
        block = _make_block("b1", 725, 780, "Overflows")
        block.bbox = BoundingBox(x0=100.0, y0=725, x1=400.0, y1=780)
        page = _make_page(1, [block])
        doc = _make_doc_ir([page])

        split_page_on_overflow(doc, 1)

        moved = doc.pages[1].text_blocks[0]
        assert moved.bbox.x0 == 100.0
        assert moved.bbox.x1 == 400.0


# -----------------------------------------------------------------
# Page renumbering tests
# -----------------------------------------------------------------

class TestPageRenumbering:
    """Test that page insertion correctly renumbers subsequent pages."""

    def test_subsequent_pages_renumbered(self):
        """Pages after the insertion point get incremented page numbers."""
        pages = [
            _make_page(1, [_make_block("p1b1", 72, 200, "Page 1 content")]),
            _make_page(2, [_make_block("p2b1", 72, 200, "Page 2 content")]),
            _make_page(3, [_make_block("p3b1", 72, 200, "Page 3 content")]),
        ]
        doc = _make_doc_ir(pages)

        # Force overflow on page 1
        doc.pages[0].text_blocks.append(
            _make_block("overflow", 725, 780, "This overflows")
        )
        split_page_on_overflow(doc, 1)

        assert doc.page_count == 4
        assert doc.pages[0].page_number == 1
        assert doc.pages[1].page_number == 2  # new page
        assert doc.pages[2].page_number == 3  # was page 2
        assert doc.pages[3].page_number == 4  # was page 3

    def test_block_page_references_updated(self):
        """Blocks on renumbered pages have their .page field updated."""
        pages = [
            _make_page(1, [
                _make_block("p1b1", 72, 200, "Stays"),
                _make_block("p1b2", 725, 780, "Overflows"),
            ]),
            _make_page(2, [_make_block("p2b1", 72, 200, "Page 2 block", page=2)]),
        ]
        doc = _make_doc_ir(pages)

        split_page_on_overflow(doc, 1)

        # Page 3 (originally page 2) — block should say page 3
        assert doc.pages[2].text_blocks[0].page == 3


# -----------------------------------------------------------------
# reflow_and_split combined tests
# -----------------------------------------------------------------

class TestReflowAndSplit:
    """Test the combined reflow + split operation."""

    def test_small_edit_no_split(self):
        """A small text change that doesn't overflow doesn't create a new page."""
        blocks = [
            _make_block("b1", 72, 100, "Short text"),
            _make_block("b2", 110, 140, "Another block"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        # Small edit
        doc.pages[0].text_blocks[0].text_verbatim = "Slightly longer text here"
        result = reflow_and_split(doc, 1, "b1")

        assert result.page_added is False
        assert result.new_page_number is None
        assert doc.page_count == 1

    def test_massive_expansion_triggers_split(self):
        """Expanding text massively triggers page split."""
        blocks = [
            _make_block("b1", 72, 100, "Short"),
            _make_block("b2", 110, 140, "Second block"),
            _make_block("b3", 150, 180, "Third block"),
            _make_block("b4", 650, 700, "Near bottom"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        # Massive expansion of first block
        doc.pages[0].text_blocks[0].text_verbatim = "Expanded requirement. " * 80
        result = reflow_and_split(doc, 1, "b1")

        assert result.page_added is True
        assert result.new_page_number == 2
        assert doc.page_count == 2
        # Overflow should be resolved (0)
        assert result.overflow_pt == 0.0

    def test_split_result_fields(self):
        """ReflowResult has correct page_added and new_page_number fields."""
        blocks = [
            _make_block("b1", 72, 100, "Short"),
            _make_block("b2", 680, 710, "Near bottom"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        # Expand b1 enough to push b2 past the boundary
        doc.pages[0].text_blocks[0].text_verbatim = "Long requirement text. " * 50
        result = reflow_and_split(doc, 1, "b1")

        assert result.page_added is True
        assert result.new_page_number == 2
        assert result.overflowing_blocks == []  # Resolved


# -----------------------------------------------------------------
# Real document tests
# -----------------------------------------------------------------

@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestPageSplitOnRealDoc:
    """Page split on the HSI Spectrometer ICD."""

    @pytest.fixture
    def doc_ir(self):
        from src.pipeline import process_pdf
        return process_pdf(HSI_PDF)

    def test_massive_edit_creates_page(self, doc_ir):
        """Massively expanding a block on a real document creates a new page."""
        original_page_count = doc_ir.page_count
        page = doc_ir.pages[3]  # Page 4
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y0)
        body_blocks = [b for b in blocks if 60 <= b.bbox.y0 <= page.height_pt - 72]

        if not body_blocks:
            pytest.skip("No body blocks on page 4")

        # Massive expansion
        body_blocks[0].text_verbatim = "The spectrometer shall maintain thermal equilibrium. " * 100
        result = reflow_and_split(doc_ir, 4, body_blocks[0].id)

        assert result.page_added is True
        assert doc_ir.page_count == original_page_count + 1
        # New page should have content
        new_page = doc_ir.pages[4]  # The inserted page
        assert len(new_page.text_blocks) > 0

    def test_no_overflow_no_extra_pages(self, doc_ir):
        """Normal-sized edits don't add pages."""
        original_page_count = doc_ir.page_count
        page = doc_ir.pages[0]
        if not page.text_blocks:
            pytest.skip("No blocks on page 1")

        block = page.text_blocks[0]
        block.text_verbatim = "Minor edit."
        result = reflow_and_split(doc_ir, 1, block.id)

        assert result.page_added is False
        assert doc_ir.page_count == original_page_count


# -----------------------------------------------------------------
# Phase 2: List items and tables
# -----------------------------------------------------------------

class TestListItemOverflow:
    """Test that list_item blocks are moved like paragraphs."""

    def test_list_item_moves_on_overflow(self):
        """list_item blocks past the margin are moved to new page."""
        blocks = [
            _make_block("b1", 72, 200, "Paragraph stays"),
            _make_block("li1", 721, 735, "1. First list item", block_type="list_item"),
            _make_block("li2", 730, 742, "2. Second list item", block_type="list_item"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 2
        assert doc.page_count == 2
        # Both list items moved
        new_page_types = [b.block_type for b in doc.pages[1].text_blocks]
        assert new_page_types == ["list_item", "list_item"]

    def test_caption_moves_on_overflow(self):
        """caption blocks past the margin are moved to new page."""
        blocks = [
            _make_block("b1", 72, 200, "Body content"),
            _make_block("cap1", 730, 745, "Figure 3: System diagram", block_type="caption"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 1
        assert doc.pages[1].text_blocks[0].block_type == "caption"

    def test_heading_moves_on_overflow(self):
        """Headings ARE moved when they overflow."""
        blocks = [
            _make_block("b1", 72, 200, "Body"),
            _make_block("h1", 725, 740, "4.0 Next Section", block_type="heading"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)
        assert result.split_occurred is True
        assert result.blocks_moved == 1

    def test_mixed_types_overflow(self):
        """Mix of paragraphs and list items all move correctly."""
        blocks = [
            _make_block("b1", 72, 200, "Body stays"),
            _make_block("p1", 722, 735, "Paragraph overflows"),
            _make_block("li1", 725, 738, "- Item one", block_type="list_item"),
            _make_block("li2", 730, 742, "- Item two", block_type="list_item"),
        ]
        page = _make_page(1, blocks)
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 3
        new_types = [b.block_type for b in doc.pages[1].text_blocks]
        assert "paragraph" in new_types
        assert new_types.count("list_item") == 2


class TestTableOverflow:
    """Test that TableBlock objects are moved when they overflow."""

    def _make_table(self, table_id: str, y0: float, y1: float, page: int = 1):
        """Create a minimal TableBlock for testing."""
        from src.models.document_ir import TableBlock, TableColumn, TableRow, TableCell
        return TableBlock(
            id=table_id,
            page=page,
            bbox=BoundingBox(x0=72.0, y0=y0, x1=540.0, y1=y1),
            columns=[TableColumn(id="col1", title="Column 1")],
            rows=[TableRow(id="row1", cells={"col1": TableCell(value="data")})],
            confidence=1.0,
        )

    def test_table_overflow_moves_to_new_page(self):
        """A table past the bottom margin gets moved."""
        blocks = [_make_block("b1", 72, 200, "Body text")]
        page = _make_page(1, blocks)
        page.tables = [self._make_table("t1", 725, 790)]
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.tables_moved == 1
        assert doc.page_count == 2
        assert len(doc.pages[0].tables) == 0
        assert len(doc.pages[1].tables) == 1
        # Table repositioned at top margin
        assert doc.pages[1].tables[0].bbox.y0 == 72.0

    def test_table_straddling_boundary_moves(self):
        """A table that starts above boundary but extends below gets moved."""
        blocks = [_make_block("b1", 72, 200, "Body")]
        page = _make_page(1, blocks)
        page.tables = [self._make_table("t1", 700, 780)]  # starts at 700, ends at 780
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.tables_moved == 1

    def test_table_within_bounds_stays(self):
        """A table fully within bounds is not moved."""
        blocks = [_make_block("b1", 72, 200, "Body")]
        page = _make_page(1, blocks)
        page.tables = [self._make_table("t1", 400, 600)]
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is False
        assert len(doc.pages[0].tables) == 1

    def test_table_and_text_both_overflow(self):
        """Both text blocks and tables overflow — all moved."""
        blocks = [
            _make_block("b1", 72, 200, "Stays"),
            _make_block("b2", 730, 750, "Paragraph overflows"),
        ]
        page = _make_page(1, blocks)
        page.tables = [self._make_table("t1", 755, 810)]
        doc = _make_doc_ir([page])

        result = split_page_on_overflow(doc, 1)

        assert result.split_occurred is True
        assert result.blocks_moved == 1
        assert result.tables_moved == 1
        assert len(doc.pages[1].text_blocks) == 1
        assert len(doc.pages[1].tables) == 1

    def test_table_preserves_content(self):
        """Moved table preserves its rows and columns."""
        blocks = [_make_block("b1", 72, 200, "Body")]
        page = _make_page(1, blocks)
        table = self._make_table("t1", 725, 790)
        page.tables = [table]
        doc = _make_doc_ir([page])

        split_page_on_overflow(doc, 1)

        moved_table = doc.pages[1].tables[0]
        assert len(moved_table.columns) == 1
        assert len(moved_table.rows) == 1
        assert moved_table.rows[0].cells["col1"].value == "data"

    def test_table_page_reference_updated(self):
        """Moved table has its .page field updated to new page number."""
        blocks = [_make_block("b1", 72, 200, "Body")]
        page = _make_page(1, blocks)
        page.tables = [self._make_table("t1", 725, 790)]
        doc = _make_doc_ir([page])

        split_page_on_overflow(doc, 1)

        assert doc.pages[1].tables[0].page == 2
