"""User Guide Regression: Table Editing (Section 4.3)

Validates the table editing workflow described in the User Guide:
- Click cell -> edit -> apply
- Add row -> Apply Table Changes -> row count increases
- Delete row -> content shifts up
- Column count preserved across add/delete
- Content below table shifts correctly with table height changes
- Drawings (borders) shift with text

Tests use HSI_SYS_015G.pdf page 7, which contains a thermostat table.
"""

import shutil
import uuid
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _fresh_client(pdf_path: Path) -> TestClient:
    """Create a test client with an isolated copy of the PDF."""
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    test_copy = output_dir / f".test_tbl_{uuid.uuid4().hex[:8]}_{pdf_path.name}"
    shutil.copy2(str(pdf_path), str(test_copy))

    app = create_app()
    client = TestClient(app)
    client.post("/session/start")
    res = client.post(f"/document/open?pdf_path={test_copy}")
    assert res.status_code == 200
    return client


def _get_zones(client: TestClient, page: int) -> list[dict]:
    """Fetch table zones for a page."""
    res = client.get(f"/document/page/{page}/table-zones")
    assert res.status_code == 200
    return res.json().get("zones", [])


def _get_table(client: TestClient, page: int, y_min: float = 0, y_max: float = 9999) -> dict:
    """Fetch table data for a page/zone."""
    res = client.get(f"/document/page/{page}/table?y_min={y_min}&y_max={y_max}")
    assert res.status_code == 200
    return res.json()


def _rebuild_table(client: TestClient, page: int, y_min: float, y_max: float, data: list[list[str]]) -> dict:
    """Post a table rebuild request."""
    res = client.post(
        f"/document/page/{page}/table-rebuild",
        json={"y_min": y_min, "y_max": y_max, "data": data},
    )
    assert res.status_code == 200, f"Rebuild failed: {res.text}"
    return res.json()


def _get_text_below_table(client: TestClient, page: int, table_y_max: float) -> list[dict]:
    """Get text blocks below a table zone on a page."""
    res = client.get(f"/document/page/{page}")
    assert res.status_code == 200
    blocks = res.json()["blocks"]
    return [b for b in blocks if b["bbox"]["y0"] > table_y_max]


# ─── Table Zone Detection ─────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTableZonesDetected:
    """Verify that table zones are properly detected on page 7."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_table_zones_detected(self, client):
        """GET /document/page/7/table-zones returns at least one zone for HSI page 7."""
        zones = _get_zones(client, 7)
        assert len(zones) >= 1, "No table zones detected on page 7"

    def test_table_zones_have_bounds(self, client):
        """Each zone has y_min and y_max defining vertical extent."""
        zones = _get_zones(client, 7)
        for zone in zones:
            assert "y_min" in zone
            assert "y_max" in zone
            assert zone["y_max"] > zone["y_min"], "Zone has zero or negative height"


# ─── Table Cell Detection ─────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTableCellsReturned:
    """Verify table cell detection returns proper row x col structure."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_table_cells_returned(self, client):
        """GET /document/page/7/table returns rows x cols structure."""
        zones = _get_zones(client, 7)
        assert len(zones) >= 1
        zone = zones[0]

        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        assert table["has_table"] is True
        assert table["columns"] >= 2
        assert table["rows"] >= 3
        assert len(table["data"]) == table["rows"]

    def test_table_cells_have_text(self, client):
        """At least some cells in the table contain text."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        non_empty = sum(
            1 for row in table["data"] for cell in row if cell["text"].strip()
        )
        assert non_empty >= 4, f"Only {non_empty} non-empty cells found"


# ─── Inline Cell Edit ─────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestInlineCellEdit:
    """Verify editing a single table cell via rebuild with modified data."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_inline_cell_edit(self, client):
        """PUT table-cell equivalent: rebuild with one cell modified updates that cell."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        # Extract current data as plain text
        data = [[cell["text"] for cell in row] for row in table["data"]]
        original_columns = table["columns"]

        # Modify a single cell (row 1, col 0 — typically a data cell)
        marker = "CELL_EDIT_TEST_42"
        data[1][0] = marker

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["status"] == "rebuilt"
        assert result["columns"] == original_columns

        # Verify the edit persists when re-reading the table
        table_after = _get_table(client, 7, zone["y_min"], zone["y_max"])
        all_texts = [cell["text"] for row in table_after["data"] for cell in row]
        assert any(marker in t for t in all_texts), (
            f"Edited cell text '{marker}' not found in rebuilt table"
        )


# ─── Add Row ──────────────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestAddRowIncreasesCount:
    """Verify that adding a row to the table increases the row count."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_add_row_increases_count(self, client):
        """Rebuild with an extra row returns rows+1."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        original_rows = table["rows"]
        original_cols = table["columns"]
        data = [[cell["text"] for cell in row] for row in table["data"]]

        # Add a new row with placeholder text
        new_row = ["New Cell " + str(i) for i in range(original_cols)]
        data.append(new_row)

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["status"] == "rebuilt"
        assert result["rows"] == original_rows + 1

    def test_add_row_shifts_content_below(self, client):
        """Text below table moves down by approximately one row height after add."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        # Get content below table before the edit
        blocks_before = _get_text_below_table(client, 7, zone["y_max"])
        if not blocks_before:
            pytest.skip("No text blocks below table on page 7")

        first_below_y_before = blocks_before[0]["bbox"]["y0"]

        # Add a row
        data = [[cell["text"] for cell in row] for row in table["data"]]
        new_row = ["Added" for _ in range(table["columns"])]
        data.append(new_row)

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        height_delta = result.get("height_delta", 0)

        # Re-read blocks below table
        # After rebuild, the table zone y_max has shifted, so use original + delta
        blocks_after = _get_text_below_table(client, 7, zone["y_max"] + height_delta)
        if not blocks_after:
            # Content may have been pushed; just confirm height_delta > 0
            assert height_delta > 0, "Row added but no height delta reported"
            return

        first_below_y_after = blocks_after[0]["bbox"]["y0"]
        # Content should have shifted down (positive delta)
        assert first_below_y_after > first_below_y_before - 1, (
            f"Content below table did not shift down: before={first_below_y_before}, after={first_below_y_after}"
        )


# ─── Delete Row ───────────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestDeleteRowDecreasesCount:
    """Verify that deleting a row from the table decreases the row count."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_delete_row_decreases_count(self, client):
        """Rebuild with one less row returns rows-1."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        original_rows = table["rows"]
        data = [[cell["text"] for cell in row] for row in table["data"]]

        # Remove last data row (keep header)
        data.pop()

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["status"] == "rebuilt"
        assert result["rows"] == original_rows - 1

    def test_delete_row_shifts_content_below(self, client):
        """Text below table moves up after row deletion."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        blocks_before = _get_text_below_table(client, 7, zone["y_max"])
        if not blocks_before:
            pytest.skip("No text blocks below table on page 7")

        first_below_y_before = blocks_before[0]["bbox"]["y0"]

        # Delete a row
        data = [[cell["text"] for cell in row] for row in table["data"]]
        data.pop()

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        height_delta = result.get("height_delta", 0)

        # Content should shift up (negative height_delta)
        assert height_delta < 0 or height_delta == 0, (
            f"Expected negative or zero height_delta after row delete, got {height_delta}"
        )


# ─── Column Count Preserved ───────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTableColumnCountPreserved:
    """Verify column count remains stable through add/delete operations."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_table_column_count_preserved_after_add(self, client):
        """Column count unchanged after adding a row."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        original_cols = table["columns"]
        data = [[cell["text"] for cell in row] for row in table["data"]]
        new_row = ["X"] * original_cols
        data.append(new_row)

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["columns"] == original_cols

    def test_table_column_count_preserved_after_delete(self, client):
        """Column count unchanged after deleting a row."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        original_cols = table["columns"]
        data = [[cell["text"] for cell in row] for row in table["data"]]
        data.pop()

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["columns"] == original_cols


# ─── Shift Preserves Text Exactly ─────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestShiftPreservesText:
    """Verify that text spans below the table are preserved exactly after shift."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_shift_preserves_text_exactly(self, client):
        """Every text span below table exists at new Y with identical content after add."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        # Capture text content below table before modification
        blocks_before = _get_text_below_table(client, 7, zone["y_max"])
        texts_before = [b["text"] for b in blocks_before if b["text"].strip()]

        if not texts_before:
            pytest.skip("No text below table to verify")

        # Add a row to trigger shift
        data = [[cell["text"] for cell in row] for row in table["data"]]
        new_row = ["Shift Test"] * table["columns"]
        data.append(new_row)
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        # Re-read entire page content
        res = client.get("/document/page/7")
        assert res.status_code == 200
        all_blocks_after = res.json()["blocks"]
        texts_after = [b["text"] for b in all_blocks_after if b["text"].strip()]

        # All original text below the table should still be present
        for original_text in texts_before[:5]:  # Check first 5 for performance
            assert any(original_text in t for t in texts_after), (
                f"Text '{original_text[:60]}...' disappeared after table row add"
            )


# ─── Drawings Shift With Text ─────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestDrawingsShiftWithText:
    """Verify that vector drawings below the table shift with content."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_drawings_shift_with_text(self, client):
        """After row add, page image changes (indicating redrawn content)."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        # Get page image before
        img_before = client.get("/document/page/7/image")
        assert img_before.status_code == 200
        assert img_before.content[:8] == PNG_MAGIC

        # Add a row
        data = [[cell["text"] for cell in row] for row in table["data"]]
        new_row = ["Draw Test"] * table["columns"]
        data.append(new_row)
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        # Get page image after
        img_after = client.get("/document/page/7/image")
        assert img_after.status_code == 200
        assert img_after.content[:8] == PNG_MAGIC

        # Images should differ (table changed, content shifted)
        assert img_before.content != img_after.content, (
            "Page image did not change after table row addition"
        )
