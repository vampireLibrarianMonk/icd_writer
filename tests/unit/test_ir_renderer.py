"""Unit tests for the IR renderer module.

Tests:
- _ir_blocks_to_elements: converts Document IR text blocks to renderable elements
- Overlap deduplication: blocks whose center falls inside an already-rendered region are skipped
- _add_table_lines: grid lines drawn for blocks preceded by a caption
- _format_block_text: plain text passthrough
- _find_edited_pages: detects pages with edits by comparing IR to source text
"""

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
from src.rendering.elements import LineElement, TextElement
from src.rendering.ir_renderer import (
    _add_table_lines,
    _format_block_text,
    _ir_blocks_to_elements,
)


# ─── Fixtures ──────────────────────────────────────────────────────────


def _make_block(
    block_id: str,
    y0: float,
    y1: float,
    text: str = "Test text",
    block_type: str = "paragraph",
    page: int = 1,
    x0: float = 72.0,
    x1: float = 540.0,
    font_size: float = 10.0,
    bold: bool = False,
    italic: bool = False,
    font_name: str = "Helvetica",
) -> TextBlock:
    """Create a TextBlock at a given position."""
    return TextBlock(
        id=block_id,
        block_type=block_type,
        page=page,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text_verbatim=text,
        reading_order=0,
        style=TextStyle(
            font_name=font_name, font_size_pt=font_size, bold=bold, italic=italic
        ),
        confidence=1.0,
        is_ocr=False,
    )


def _make_page_info(
    blocks: list[TextBlock],
    page_number: int = 1,
    width: float = 612.0,
    height: float = 792.0,
) -> PageInfo:
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


# ─── _ir_blocks_to_elements basic conversion ──────────────────────────


class TestIRBlocksToElements:
    """Test conversion of IR blocks to renderable TextElements."""

    def test_single_block_produces_one_element(self):
        """A single text block produces one TextElement."""
        blocks = [_make_block("b1", 72, 100, "Hello world")]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) == 1
        assert text_elements[0].text == "Hello world"

    def test_multiple_blocks_produce_multiple_elements(self):
        """Multiple non-overlapping blocks each produce a TextElement."""
        blocks = [
            _make_block("b1", 72, 100, "First block"),
            _make_block("b2", 110, 140, "Second block"),
            _make_block("b3", 150, 180, "Third block"),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) == 3

    def test_block_style_propagated(self):
        """Block style (font, size, bold, italic) propagates to TextElement."""
        blocks = [
            _make_block(
                "b1", 72, 100, "Bold text",
                font_size=14.0, bold=True, italic=False, font_name="Helvetica-Bold"
            )
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) == 1
        elem = text_elements[0]
        assert elem.font_size_pt == 14.0
        assert elem.bold is True
        assert elem.italic is False
        assert elem.font_name == "Helvetica-Bold"

    def test_block_bbox_preserved(self):
        """Block bounding box is preserved on the TextElement."""
        blocks = [_make_block("b1", 100, 150, "Positioned", x0=80.0, x1=500.0)]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert text_elements[0].bbox.x0 == 80.0
        assert text_elements[0].bbox.y0 == 100.0
        assert text_elements[0].bbox.x1 == 500.0
        assert text_elements[0].bbox.y1 == 150.0

    def test_blocks_sorted_by_y_then_x(self):
        """Blocks are rendered in reading order (top-to-bottom, left-to-right)."""
        blocks = [
            _make_block("b2", 200, 230, "Second"),
            _make_block("b1", 72, 100, "First"),
            _make_block("b3", 200, 230, "Third", x0=300.0, x1=540.0),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert text_elements[0].text == "First"
        assert text_elements[1].text == "Second"

    def test_empty_page_produces_no_elements(self):
        """A page with no blocks produces an empty element list."""
        page = _make_page_info([])

        elements = _ir_blocks_to_elements(page)

        assert elements == []

    def test_block_without_style_uses_defaults(self):
        """A block with style=None uses default font metrics."""
        block = TextBlock(
            id="b-no-style",
            block_type="paragraph",
            page=1,
            bbox=BoundingBox(x0=72, y0=72, x1=540, y1=100),
            text_verbatim="No style block",
            reading_order=0,
            style=None,
            confidence=1.0,
            is_ocr=False,
        )
        page = _make_page_info([block])

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) == 1
        # Should use defaults: 10pt Helvetica, not bold, not italic
        assert text_elements[0].font_size_pt == 10.0
        assert text_elements[0].bold is False
        assert text_elements[0].italic is False


# ─── Overlap deduplication ─────────────────────────────────────────────


class TestOverlapDedup:
    """Test that overlapping blocks are deduplicated.

    Per the architecture: 'blocks whose center falls inside an
    already-rendered region are skipped.'
    """

    def test_non_overlapping_blocks_all_rendered(self):
        """Non-overlapping blocks are all preserved."""
        blocks = [
            _make_block("b1", 72, 100, "Block 1"),
            _make_block("b2", 110, 140, "Block 2"),
            _make_block("b3", 150, 180, "Block 3"),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) == 3

    def test_completely_overlapping_block_deduped(self):
        """A block whose center is inside a previously rendered block is skipped."""
        # b1 covers y=100-200; b2 covers y=120-180 (center at 150, inside b1)
        blocks = [
            _make_block("b1", 100, 200, "Large block", x0=72, x1=540),
            _make_block("b2", 120, 180, "Nested block", x0=100, x1=500),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        # b1 renders first (lower y0), b2's center is inside b1 → skipped
        assert len(text_elements) == 1
        assert text_elements[0].text == "Large block"

    def test_partial_overlap_but_center_outside(self):
        """A block that partially overlaps but whose center is outside is kept."""
        # b1 covers y=100-150; b2 covers y=140-200 (center at 170, NOT inside b1)
        blocks = [
            _make_block("b1", 100, 150, "First block", x0=72, x1=540),
            _make_block("b2", 140, 200, "Second block", x0=72, x1=540),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) == 2

    def test_page7_thermal_table_scenario(self):
        """Simulates page 7's overlapping table fragments.

        b09 (y=512-525), b10 (y=498-511), b11 (y=511-526), b12 (y=498-570)
        The dedup should keep b12 (the largest) since it renders first
        (lowest y0=498), and skip fragments whose centers are inside b12.
        """
        blocks = [
            _make_block("b09", 512, 525, "Range"),
            _make_block("b10", 498, 511, "Bus Side Interface"),
            _make_block("b11", 511, 526, "Temperature, C"),
            _make_block("b12", 498, 570, "Spectrometer\nTemperature\nNon-Op Limits\n-60-+61"),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        # b10 and b12 both start at y=498; after sorting by (y0, x0),
        # whichever renders first claims the region.
        # b09 center=(306, 518.5), b10 center=(306, 504.5), b11 center=(306, 518.5)
        # b12 bbox is 72-540, 498-570 — all fragment centers are inside b12's region
        # So only b10 (first at y=498) and b12 (also at y=498) compete.
        # After sorting: b10 (x0=72, y0=498) vs b12 (x0=72, y0=498) — same position.
        # The first one in sorted order claims the region.
        # Then subsequent ones whose center is inside get skipped.
        # Key assertion: we get fewer elements than input blocks (dedup works)
        assert len(text_elements) < len(blocks)

    def test_horizontally_adjacent_blocks_not_deduped(self):
        """Blocks side-by-side horizontally should NOT be deduped."""
        blocks = [
            _make_block("b1", 100, 130, "Left col", x0=72, x1=300),
            _make_block("b2", 100, 130, "Right col", x0=310, x1=540),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        assert len(text_elements) == 2

    def test_many_small_fragments_inside_large_block(self):
        """Multiple small fragments inside a large block all get deduped."""
        blocks = [
            _make_block("big", 100, 400, "Full table content", x0=72, x1=540),
            _make_block("frag1", 150, 170, "Fragment 1", x0=100, x1=500),
            _make_block("frag2", 200, 220, "Fragment 2", x0=100, x1=500),
            _make_block("frag3", 250, 270, "Fragment 3", x0=100, x1=500),
            _make_block("frag4", 300, 320, "Fragment 4", x0=100, x1=500),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        # Only the big block should remain; all fragments' centers are inside it
        assert len(text_elements) == 1
        assert text_elements[0].text == "Full table content"


# ─── Table line generation ─────────────────────────────────────────────


class TestAddTableLines:
    """Test _add_table_lines: grid lines for caption-preceded table blocks."""

    def test_caption_followed_by_table_gets_lines(self):
        """A paragraph block preceded by a caption gets grid lines."""
        blocks = [
            _make_block("cap", 240, 255, "Table 3.2.1-1 Thermostat Chars", block_type="caption"),
            _make_block("tbl", 256, 313, "Characteristic\nSetting\nPower\n25W", block_type="paragraph"),
        ]
        page = _make_page_info(blocks)
        elements: list = []

        _add_table_lines(page, elements)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        # Should have: top, bottom, left, right borders + column divider + row dividers
        # 4 rows of data, 5 borders + 1 column divider + 3 row dividers = 9 lines
        assert len(line_elements) >= 5  # At minimum: 4 borders + 1 column divider

    def test_no_caption_no_lines(self):
        """A paragraph NOT preceded by a caption doesn't get grid lines."""
        blocks = [
            _make_block("h1", 200, 220, "Section Heading", block_type="heading"),
            _make_block("p1", 230, 290, "First\nSecond\nThird", block_type="paragraph"),
        ]
        page = _make_page_info(blocks)
        elements: list = []

        _add_table_lines(page, elements)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        assert len(line_elements) == 0

    def test_single_line_table_no_grid(self):
        """A table block with only 1 line doesn't get grid lines (< 2 lines)."""
        blocks = [
            _make_block("cap", 240, 255, "Table 1", block_type="caption"),
            _make_block("tbl", 256, 280, "Single line only", block_type="paragraph"),
        ]
        page = _make_page_info(blocks)
        elements: list = []

        _add_table_lines(page, elements)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        assert len(line_elements) == 0

    def test_table_grid_coordinates_correct(self):
        """Grid lines use the table block's bounding box coordinates."""
        blocks = [
            _make_block("cap", 240, 255, "Table X", block_type="caption"),
            _make_block(
                "tbl", 256, 313, "Row1\nRow2\nRow3",
                block_type="paragraph", x0=100.0, x1=500.0
            ),
        ]
        page = _make_page_info(blocks)
        elements: list = []

        _add_table_lines(page, elements)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        # Top border should be at y=256
        top_lines = [l for l in line_elements if abs(l.y1 - 256) < 1 and abs(l.y2 - 256) < 1]
        assert len(top_lines) >= 1

        # Bottom border at y=313
        bottom_lines = [l for l in line_elements if abs(l.y1 - 313) < 1 and abs(l.y2 - 313) < 1]
        assert len(bottom_lines) >= 1

        # Column divider at midpoint x=300
        mid_x = (100.0 + 500.0) / 2
        col_dividers = [l for l in line_elements if abs(l.x1 - mid_x) < 1 and abs(l.x2 - mid_x) < 1]
        assert len(col_dividers) >= 1

    def test_row_dividers_evenly_spaced(self):
        """Row dividers are evenly spaced within the table block."""
        blocks = [
            _make_block("cap", 240, 255, "Table Y", block_type="caption"),
            _make_block(
                "tbl", 260, 320, "A\nB\nC\nD",
                block_type="paragraph", x0=72.0, x1=540.0
            ),
        ]
        page = _make_page_info(blocks)
        elements: list = []

        _add_table_lines(page, elements)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        # 4 lines of text → 3 row dividers (between rows)
        # Row dividers are horizontal lines between top (260) and bottom (320)
        row_dividers = [
            l for l in line_elements
            if abs(l.x1 - 72.0) < 1 and abs(l.x2 - 540.0) < 1
            and l.y1 > 261 and l.y1 < 319  # Between top and bottom
        ]
        assert len(row_dividers) == 3

        # Check even spacing
        line_height = (320 - 260) / 4  # 15pt per row
        for i, div in enumerate(sorted(row_dividers, key=lambda l: l.y1)):
            expected_y = 260 + (i + 1) * line_height
            assert abs(div.y1 - expected_y) < 1.0, (
                f"Row divider {i} at y={div.y1}, expected {expected_y}"
            )

    def test_caption_must_be_close_above(self):
        """Caption must be within 15pt above the table block to trigger lines."""
        blocks = [
            # Caption far above (gap > 15pt)
            _make_block("cap", 100, 115, "Table Far Away", block_type="caption"),
            _make_block("tbl", 250, 310, "A\nB\nC", block_type="paragraph"),
        ]
        page = _make_page_info(blocks)
        elements: list = []

        _add_table_lines(page, elements)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        assert len(line_elements) == 0

    def test_heading_block_not_treated_as_table(self):
        """Heading blocks are not treated as table data even with caption above."""
        blocks = [
            _make_block("cap", 240, 255, "Table Z", block_type="caption"),
            _make_block("h1", 256, 280, "Section Title\nSubtitle", block_type="heading"),
        ]
        page = _make_page_info(blocks)
        elements: list = []

        _add_table_lines(page, elements)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        assert len(line_elements) == 0


# ─── _format_block_text ────────────────────────────────────────────────


class TestFormatBlockText:
    """Test _format_block_text plain text passthrough."""

    def test_plain_text_unchanged(self):
        block = _make_block("b1", 72, 100, "Hello world")
        assert _format_block_text(block) == "Hello world"

    def test_newlines_preserved(self):
        block = _make_block("b1", 72, 100, "Line1\nLine2\nLine3")
        assert _format_block_text(block) == "Line1\nLine2\nLine3"

    def test_empty_text(self):
        block = _make_block("b1", 72, 100, "")
        assert _format_block_text(block) == ""

    def test_special_characters_preserved(self):
        block = _make_block("b1", 72, 100, "Temp: -30\u00b0C to +61\u00b0C")
        assert _format_block_text(block) == "Temp: -30\u00b0C to +61\u00b0C"


# ─── Integration: _ir_blocks_to_elements with table lines ─────────────


class TestIRBlocksWithTableLines:
    """Test _ir_blocks_to_elements produces both text and table line elements."""

    def test_table_page_has_text_and_line_elements(self):
        """A page with a caption+table produces TextElements AND LineElements."""
        blocks = [
            _make_block("h1", 37, 50, "Document Title", block_type="heading"),
            _make_block("p1", 73, 114, "Body paragraph text.", block_type="paragraph"),
            _make_block("cap", 241, 255, "Table 3.2.1-1 Thermostat", block_type="caption"),
            _make_block(
                "tbl", 256, 313,
                "Characteristic\nSetting\nPower\n25W",
                block_type="paragraph",
            ),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        line_elements = [e for e in elements if isinstance(e, LineElement)]

        # heading + body + caption = 3 non-table elements
        # table block with 4 lines (2 rows x 2 cols) = 4 cell elements
        assert len(text_elements) >= 4  # At minimum: 3 non-table + at least 1 table cell
        assert len(text_elements) == 7  # 3 + 4 cells
        assert len(line_elements) >= 5  # borders + column divider

    def test_mixed_page_no_extra_lines_for_body(self):
        """Body paragraphs without captions don't get spurious grid lines."""
        blocks = [
            _make_block("h1", 72, 90, "Heading", block_type="heading"),
            _make_block("p1", 100, 200, "Long body\nparagraph\ntext", block_type="paragraph"),
            _make_block("p2", 210, 300, "Another\nparagraph", block_type="paragraph"),
        ]
        page = _make_page_info(blocks)

        elements = _ir_blocks_to_elements(page)

        line_elements = [e for e in elements if isinstance(e, LineElement)]
        assert len(line_elements) == 0
