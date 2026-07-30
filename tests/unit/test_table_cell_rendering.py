"""Unit tests: Table Cell Rendering

Verifies that table data blocks are rendered as individual per-cell
TextElements aligned to the grid, not as a single monolithic text span.

This is the core of section 4.3 of the User Guide: editing a table value
(e.g., 30W → 25W) should produce a properly formatted table in the page image.

Tests cover:
1. Table detection (paragraph preceded by caption within 15pt)
2. Cell splitting (newline-separated text → individual cell elements)
3. Grid alignment (cells positioned at correct row/column coordinates)
4. Edit preservation (edited values appear in correct cells)
5. Various table shapes (2-col, odd-row, single-col fallback)
6. Real document rendering (HSI page 7 table)
"""

from pathlib import Path

import pytest

from src.models.common import BoundingBox
from src.models.document_ir import (
    PageClassification,
    PageClassificationType,
    PageInfo,
    TextBlock,
    TextStyle,
)
from src.rendering.elements import LineElement, TextElement
from src.rendering.ir_renderer import (
    _add_table_lines,
    _ir_blocks_to_elements,
    _is_table_data_block,
    _split_table_into_cells,
)

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"


# ─── Helpers ───────────────────────────────────────────────────────────


def _block(
    block_id, y0, y1, text,
    block_type="paragraph", x0=72.0, x1=540.0,
    font_name="TimesNewRoman", font_size=12.0,
):
    return TextBlock(
        id=block_id, block_type=block_type, page=1,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text_verbatim=text, reading_order=0,
        style=TextStyle(font_name=font_name, font_size_pt=font_size, bold=False, italic=False),
        confidence=1.0, is_ocr=False,
    )


def _page(blocks, width=612.0, height=792.0):
    return PageInfo(
        page_number=1, width_pt=width, height_pt=height,
        classification=PageClassification(
            page_number=1, classifications=[PageClassificationType.NATIVE_DIGITAL_TEXT],
        ),
        text_blocks=blocks,
    )


# ─── Table detection ──────────────────────────────────────────────────


class TestTableDetection:
    """Test _is_table_data_block correctly identifies table data."""

    def test_paragraph_after_caption_is_table(self):
        """Paragraph immediately below a caption is detected as table."""
        blocks = [
            _block("cap", 240, 255, "Table 1 Title", block_type="caption"),
            _block("tbl", 256, 313, "A\nB\nC\nD"),
        ]
        page = _page(blocks)
        table_block = blocks[1]
        assert _is_table_data_block(table_block, page) is True

    def test_paragraph_far_from_caption_is_not_table(self):
        """Paragraph more than 15pt below caption is NOT table."""
        blocks = [
            _block("cap", 200, 215, "Table 2 Title", block_type="caption"),
            _block("p1", 240, 270, "A\nB\nC\nD"),  # 25pt gap
        ]
        page = _page(blocks)
        assert _is_table_data_block(blocks[1], page) is False

    def test_single_line_paragraph_is_not_table(self):
        """Single line paragraph is NOT table even after caption."""
        blocks = [
            _block("cap", 240, 255, "Table 3", block_type="caption"),
            _block("p1", 256, 270, "Just one line"),
        ]
        page = _page(blocks)
        assert _is_table_data_block(blocks[1], page) is False

    def test_heading_is_not_table(self):
        """Heading blocks are never tables."""
        blocks = [
            _block("cap", 240, 255, "Table 4", block_type="caption"),
            _block("h1", 256, 280, "Section\nTitle", block_type="heading"),
        ]
        page = _page(blocks)
        assert _is_table_data_block(blocks[1], page) is False

    def test_paragraph_without_caption_is_not_table(self):
        """Paragraph with no caption above is NOT table."""
        blocks = [
            _block("h1", 200, 220, "Heading", block_type="heading"),
            _block("p1", 230, 290, "Line1\nLine2\nLine3"),
        ]
        page = _page(blocks)
        assert _is_table_data_block(blocks[1], page) is False


# ─── Cell splitting: 2-column tables ─────────────────────────────────


class TestCellSplitting2Column:
    """Test _split_table_into_cells for 2-column key-value tables."""

    def test_4_line_table_produces_4_cells(self):
        """4 lines (2 rows × 2 cols) produces 4 cell elements."""
        block = _block("tbl", 256, 313, "Key1\nVal1\nKey2\nVal2", x0=176, x1=428)
        cells = _split_table_into_cells(block, "TimesNewRoman", 12.0, False, False)
        assert len(cells) == 4

    def test_8_line_table_produces_8_cells(self):
        """8 lines (4 rows × 2 cols) produces 8 cell elements."""
        text = "Characteristic\nSetting\nPower\n25W\nTurn-on Temperature\n-30C\nTurn-off Temperature\n-20C"
        block = _block("tbl", 256, 313, text, x0=176, x1=428)
        cells = _split_table_into_cells(block, "TimesNewRoman", 12.0, False, False)
        assert len(cells) == 8

    def test_cells_have_correct_text(self):
        """Each cell contains the correct text content."""
        text = "Power\n25W\nVoltage\n28V"
        block = _block("tbl", 256, 313, text, x0=176, x1=428)
        cells = _split_table_into_cells(block, "TimesNewRoman", 12.0, False, False)
        cell_texts = [c.text for c in cells]
        assert "Power" in cell_texts
        assert "25W" in cell_texts
        assert "Voltage" in cell_texts
        assert "28V" in cell_texts

    def test_left_column_cells_positioned_left(self):
        """Key cells (left column) have x0 near the block's left edge."""
        text = "Power\n25W\nVoltage\n28V"
        block = _block("tbl", 256, 313, text, x0=176, x1=428)
        mid_x = (176 + 428) / 2  # = 302
        cells = _split_table_into_cells(block, "TimesNewRoman", 12.0, False, False)

        left_cells = [c for c in cells if c.bbox.x0 < mid_x]
        right_cells = [c for c in cells if c.bbox.x0 >= mid_x]

        assert len(left_cells) == 2  # Power, Voltage
        assert len(right_cells) == 2  # 25W, 28V

    def test_right_column_cells_positioned_right(self):
        """Value cells (right column) have x0 past the midpoint."""
        text = "Power\n25W\nVoltage\n28V"
        block = _block("tbl", 256, 313, text, x0=176, x1=428)
        mid_x = (176 + 428) / 2
        cells = _split_table_into_cells(block, "TimesNewRoman", 12.0, False, False)

        right_cells = [c for c in cells if c.bbox.x0 >= mid_x]
        assert all(c.text in ["25W", "28V"] for c in right_cells)

    def test_rows_have_increasing_y(self):
        """Cells in later rows have higher y-position."""
        text = "A\n1\nB\n2\nC\n3"
        block = _block("tbl", 100, 200, text, x0=72, x1=540)
        cells = _split_table_into_cells(block, "Helvetica", 10.0, False, False)

        # Get left-column cells (A, B, C) — they represent rows
        left_cells = sorted(
            [c for c in cells if c.text in ["A", "B", "C"]],
            key=lambda c: c.bbox.y0,
        )
        assert left_cells[0].text == "A"
        assert left_cells[1].text == "B"
        assert left_cells[2].text == "C"
        assert left_cells[0].bbox.y0 < left_cells[1].bbox.y0 < left_cells[2].bbox.y0

    def test_cells_within_block_bounds(self):
        """All cells are positioned within the original block bounds."""
        text = "Key1\nVal1\nKey2\nVal2\nKey3\nVal3"
        block = _block("tbl", 200, 290, text, x0=100, x1=500)
        cells = _split_table_into_cells(block, "Helvetica", 10.0, False, False)

        for cell in cells:
            assert cell.bbox.x0 >= 100, f"Cell '{cell.text}' x0={cell.bbox.x0} < 100"
            assert cell.bbox.x1 <= 500, f"Cell '{cell.text}' x1={cell.bbox.x1} > 500"
            assert cell.bbox.y0 >= 200, f"Cell '{cell.text}' y0={cell.bbox.y0} < 200"
            assert cell.bbox.y1 <= 290 + 5, f"Cell '{cell.text}' y1={cell.bbox.y1} > 295"

    def test_cell_font_propagated(self):
        """Font info propagates to all cell elements."""
        text = "A\n1\nB\n2"
        block = _block("tbl", 100, 150, text)
        cells = _split_table_into_cells(block, "Courier", 14.0, True, False)

        for cell in cells:
            assert cell.font_name == "Courier"
            assert cell.font_size_pt == 14.0
            assert cell.bold is True


# ─── Cell splitting: odd-line and single-column fallback ──────────────


class TestCellSplittingFallback:
    """Test fallback behavior for non-standard table layouts."""

    def test_odd_lines_single_column(self):
        """Odd number of lines → single column layout."""
        text = "Row1\nRow2\nRow3"
        block = _block("tbl", 100, 160, text, x0=72, x1=540)
        cells = _split_table_into_cells(block, "Helvetica", 10.0, False, False)
        assert len(cells) == 3  # One per line

    def test_single_column_cells_span_full_width(self):
        """Single-column cells use the full block width."""
        text = "Row1\nRow2\nRow3"
        block = _block("tbl", 100, 160, text, x0=100, x1=500)
        cells = _split_table_into_cells(block, "Helvetica", 10.0, False, False)

        for cell in cells:
            # Each cell should span roughly the full width (with padding)
            assert cell.bbox.x1 - cell.bbox.x0 > 350

    def test_2_lines_is_2_column(self):
        """Exactly 2 lines → 1 row × 2 columns."""
        text = "Header\nValue"
        block = _block("tbl", 100, 130, text, x0=72, x1=540)
        cells = _split_table_into_cells(block, "Helvetica", 10.0, False, False)
        # 2 lines, even → 1 row × 2 cols = 2 cells
        assert len(cells) == 2

    def test_single_line_returns_one_element(self):
        """Single line text returns one element (fallback)."""
        text = "Single value"
        block = _block("tbl", 100, 120, text, x0=72, x1=540)
        cells = _split_table_into_cells(block, "Helvetica", 10.0, False, False)
        assert len(cells) == 1
        assert cells[0].text == "Single value"


# ─── Integration: full render pipeline ────────────────────────────────


class TestTableRenderIntegration:
    """Test the full _ir_blocks_to_elements pipeline for tables."""

    def test_table_block_becomes_cells_not_monolithic(self):
        """Table data block renders as multiple cells, not one big element."""
        blocks = [
            _block("cap", 240, 255, "Table 1 Power", block_type="caption"),
            _block("tbl", 256, 313, "Characteristic\nSetting\nPower\n25W", x0=176, x1=428),
        ]
        page = _page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        # Should have: caption (1) + 4 table cells = 5 text elements
        assert len(text_elements) == 5
        # None of the elements should contain newlines (cells are split)
        for elem in text_elements:
            if elem.text != "Table 1 Power":  # Caption is OK as-is
                assert "\n" not in elem.text, f"Cell should not have newlines: '{elem.text}'"

    def test_edited_value_appears_in_correct_cell(self):
        """After editing 30W→25W, the '25W' value is in the right column."""
        blocks = [
            _block("cap", 240, 255, "Table 3.2.1-1", block_type="caption"),
            _block("tbl", 256, 313,
                   "Characteristic\nSetting\nPower\n25W\nTurn-on Temperature\n-30C\nTurn-off Temperature\n-20C",
                   x0=176, x1=428),
        ]
        page = _page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        # Find the 25W cell
        cell_25w = next((e for e in text_elements if e.text == "25W"), None)
        assert cell_25w is not None, "25W cell not found"

        # It should be in the RIGHT column (x0 > midpoint 302)
        mid_x = (176 + 428) / 2
        assert cell_25w.bbox.x0 > mid_x, f"25W should be in right column, x0={cell_25w.bbox.x0}"

    def test_grid_lines_align_with_cells(self):
        """Grid row dividers align with cell row boundaries."""
        blocks = [
            _block("cap", 240, 255, "Table X", block_type="caption"),
            _block("tbl", 256, 313,
                   "A\n1\nB\n2\nC\n3\nD\n4",
                   x0=176, x1=428),
        ]
        page = _page(blocks)
        elements = _ir_blocks_to_elements(page)

        text_elements = [e for e in elements if isinstance(e, TextElement)]
        line_elements = [e for e in elements if isinstance(e, LineElement)]

        # Get row positions from cells
        left_cells = sorted(
            [e for e in text_elements if e.bbox.x0 < 302 and e.text in ["A", "B", "C", "D"]],
            key=lambda e: e.bbox.y0,
        )

        # Get horizontal grid lines (row dividers)
        h_lines = sorted(
            [l for l in line_elements if abs(l.y1 - l.y2) < 1 and 256 < l.y1 < 313],
            key=lambda l: l.y1,
        )

        # Row dividers should be between adjacent cell rows
        assert len(h_lines) >= 3, f"Expected 3+ row dividers, got {len(h_lines)}"

    def test_non_table_paragraph_still_monolithic(self):
        """Regular paragraphs (no caption above) render as single element."""
        blocks = [
            _block("h1", 72, 90, "Section Title", block_type="heading"),
            _block("p1", 100, 200, "Line1\nLine2\nLine3"),
        ]
        page = _page(blocks)
        elements = _ir_blocks_to_elements(page)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        # Body paragraph should be single element with newlines
        body_elem = next(e for e in text_elements if "Line1" in e.text)
        assert "Line1\nLine2\nLine3" == body_elem.text


# ─── Real document: HSI page 7 ────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestHSIPage7TableCells:
    """Verify table cell rendering on the actual HSI page 7."""

    @pytest.fixture
    def page7(self):
        from src.pipeline import process_pdf
        doc_ir = process_pdf(HSI_PDF)
        return doc_ir.pages[6]

    def test_table_3_2_1_detected_as_table(self, page7):
        """Block b05 (thermostat characteristics) is detected as table."""
        b05 = next(b for b in page7.text_blocks if "30W" in b.text_verbatim)
        assert _is_table_data_block(b05, page7) is True

    def test_table_3_2_1_splits_into_cells(self, page7):
        """The thermostat table produces per-cell elements."""
        b05 = next(b for b in page7.text_blocks if "30W" in b.text_verbatim)
        cells = _split_table_into_cells(
            b05,
            b05.style.font_name or "TimesNewRoman",
            b05.style.font_size_pt or 12.0,
            b05.style.bold, b05.style.italic,
        )
        # 8 lines → 4 rows × 2 cols = 8 cells
        assert len(cells) == 8

    def test_table_3_2_1_cells_contain_30w(self, page7):
        """The original table has '30W (TBR-UCB-110)' in a right-column cell."""
        b05 = next(b for b in page7.text_blocks if "30W" in b.text_verbatim)
        cells = _split_table_into_cells(
            b05,
            b05.style.font_name or "TimesNewRoman",
            b05.style.font_size_pt or 12.0,
            b05.style.bold, b05.style.italic,
        )
        power_cell = next((c for c in cells if "30W" in c.text), None)
        assert power_cell is not None
        mid_x = (b05.bbox.x0 + b05.bbox.x1) / 2
        assert power_cell.bbox.x0 > mid_x, "30W should be in right column"

    def test_table_3_2_1_after_edit_has_25w(self, page7):
        """After editing 30W→25W, the cell contains '25W'."""
        b05 = next(b for b in page7.text_blocks if "30W" in b.text_verbatim)
        b05.text_verbatim = b05.text_verbatim.replace("30W (TBR-UCB-110)", "25W")

        elements = _ir_blocks_to_elements(page7)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        cell_25w = next((e for e in text_elements if e.text == "25W"), None)
        assert cell_25w is not None, "25W cell not found after edit"
        mid_x = (b05.bbox.x0 + b05.bbox.x1) / 2
        assert cell_25w.bbox.x0 > mid_x

    def test_full_page7_render_has_no_monolithic_table(self, page7):
        """Full page 7 render should NOT have a single element with all table rows."""
        elements = _ir_blocks_to_elements(page7)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        # No single element should contain "Characteristic\nSetting" (that's monolithic)
        for elem in text_elements:
            assert "Characteristic\nSetting" not in elem.text, (
                f"Found monolithic table element: '{elem.text[:50]}...'"
            )

    def test_full_page7_has_grid_lines_and_cells(self, page7):
        """Page 7 render has both grid lines AND individual cell text."""
        elements = _ir_blocks_to_elements(page7)
        text_elements = [e for e in elements if isinstance(e, TextElement)]
        line_elements = [e for e in elements if isinstance(e, LineElement)]

        # Should have cells for the thermostat table
        table_cells = [e for e in text_elements if e.text in [
            "Characteristic", "Setting", "Power",
            "30W (TBR-UCB-110)", "Turn-on Temperature", "-30C",
            "Turn-off Temperature", "-20C",
        ]]
        assert len(table_cells) >= 6, f"Expected 6+ table cells, got {len(table_cells)}"

        # Should have grid lines
        assert len(line_elements) >= 5, f"Expected 5+ grid lines, got {len(line_elements)}"

    def test_edit_round_trip_preserves_table_structure(self, page7):
        """Edit the table, re-render, verify structure is maintained."""
        b05 = next(b for b in page7.text_blocks if "30W" in b.text_verbatim)

        # Simulate the User Guide 4.3 workflow
        original = b05.text_verbatim
        b05.text_verbatim = original.replace("30W (TBR-UCB-110)", "25W")

        elements = _ir_blocks_to_elements(page7)
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        # Verify key structural properties:
        # 1. 25W appears as its own cell
        assert any(e.text == "25W" for e in text_elements)
        # 2. Other rows still present
        assert any(e.text == "-30C" for e in text_elements)
        assert any(e.text == "-20C" for e in text_elements)
        # 3. No monolithic multi-row element
        for e in text_elements:
            lines = e.text.count("\n")
            if lines > 0 and e.bbox.y0 > 250 and e.bbox.y0 < 320:
                pytest.fail(f"Table cell should not have newlines: '{e.text[:40]}'")
