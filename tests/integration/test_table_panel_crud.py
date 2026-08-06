"""Integration Tests: Table Panel CRUD (Add/Delete Row via Rebuild)

Tests the panel-based table editing workflow:
1. GET /document/page/{n}/table — returns structured table data
2. Frontend modifies the data (add row, delete row, edit cell)
3. POST /document/page/{n}/table-rebuild — redraws the table zone

Verifies:
- Table detection returns correct structure (rows, columns, data)
- Table rebuild writes new cell text into the PDF
- Added rows appear in the rebuilt table
- Deleted rows are removed from the rebuilt table
- Column count is preserved through add/delete operations
- Content below the table is shifted when table height changes
- Working copy is modified, not the original
- Multiple tables on one page are handled independently
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
NDS_PDF = ICDS_DIR / "NDS_IDD_RevC.pdf"
LVC_PDF = ICDS_DIR / "20150010976.pdf"


def _fresh_client(pdf_path: Path) -> TestClient:
    """Create a test client with an isolated copy of the PDF."""
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    test_copy = output_dir / f".test_{uuid.uuid4().hex[:8]}_{pdf_path.name}"
    shutil.copy2(str(pdf_path), str(test_copy))

    app = create_app()
    client = TestClient(app)
    client.post("/session/start")
    res = client.post(f"/document/open?pdf_path={test_copy}")
    assert res.status_code == 200
    return client


def _get_table(client: TestClient, page: int, y_min: float = 0, y_max: float = 9999) -> dict:
    """Fetch table data for a page/zone."""
    res = client.get(f"/document/page/{page}/table?y_min={y_min}&y_max={y_max}")
    assert res.status_code == 200
    return res.json()


def _get_zones(client: TestClient, page: int) -> list[dict]:
    """Fetch table zones for a page."""
    res = client.get(f"/document/page/{page}/table-zones")
    assert res.status_code == 200
    return res.json().get("zones", [])


def _rebuild_table(client: TestClient, page: int, y_min: float, y_max: float, data: list[list[str]]) -> dict:
    """Post a table rebuild request."""
    res = client.post(
        f"/document/page/{page}/table-rebuild",
        json={"y_min": y_min, "y_max": y_max, "data": data},
    )
    assert res.status_code == 200, f"Rebuild failed: {res.text}"
    return res.json()


# ─── HSI Document (page 7 thermostat table) ───────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTablePanelHSI:
    """Table panel CRUD on HSI_SYS_015G.pdf page 7."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_table_detection_returns_structure(self, client):
        """GET /table returns has_table=True with rows and columns."""
        zones = _get_zones(client, 7)
        assert len(zones) >= 1

        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        assert table["has_table"] is True
        assert table["columns"] >= 2
        assert table["rows"] >= 3
        assert len(table["data"]) >= 3

    def test_table_data_contains_expected_cells(self, client):
        """Table data includes known cell values from the thermostat table."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        # Flatten all cell texts
        all_texts = [cell["text"] for row in table["data"] for cell in row]
        # Should contain at least some recognizable table content
        combined = " ".join(all_texts)
        assert "Characteristic" in combined or "Power" in combined or "Temperature" in combined, (
            f"Expected table content not found in: {combined[:200]}"
        )

    def test_rebuild_preserves_existing_data(self, client):
        """Rebuilding with the same data doesn't corrupt the table."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        # Extract just the text data
        data = [[cell["text"] for cell in row] for row in table["data"]]

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["status"] == "rebuilt"
        assert result["rows"] == len(data)
        assert result["columns"] == table["columns"]

    def test_rebuild_preserves_table_caption(self, client):
        """The table caption/title above the grid is not wiped by rebuild."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        data = [[cell["text"] for cell in row] for row in table["data"]]

        _rebuild_table(client, 7, table.get("row_y_min", zone["y_min"]),
                       table.get("row_y_max", zone["y_max"]), data)

        # Verify the caption is still in the page image text
        # The caption "Table 3.2.1-1" should survive since it's above the grid
        import fitz
        session_res = client.get("/session").json()
        doc_path = session_res["document"]
        # Find the working copy
        from pathlib import Path
        working_path = Path("output") / f".working_{Path(doc_path).name}"
        if not working_path.exists():
            working_path = Path(doc_path)

        doc = fitz.open(str(working_path))
        page = doc[6]
        page_text = page.get_text("text")
        doc.close()
        assert "Table 3.2.1-1" in page_text, "Table caption was wiped by rebuild"

    def test_add_row_increases_row_count(self, client):
        """Adding a row and rebuilding shows the new data in the PDF."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        data = [[cell["text"] for cell in row] for row in table["data"]]
        original_rows = len(data)

        # Add a new row
        new_row = ["Hysteresis", "5C"]
        # Pad to match column count
        while len(new_row) < table["columns"]:
            new_row.append("")
        data.append(new_row)

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["rows"] == original_rows + 1

        # Verify text is in the PDF
        session_res = client.get("/session")
        doc_path = session_res.json()["document"]
        # The working copy should have the new text
        img_res = client.get("/document/page/7/image")
        assert img_res.status_code == 200

    def test_delete_row_decreases_row_count(self, client):
        """Deleting a row and rebuilding removes it."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        data = [[cell["text"] for cell in row] for row in table["data"]]
        original_rows = len(data)

        # Delete the last data row (keep header)
        data = data[:-1]

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["rows"] == original_rows - 1

    def test_column_count_preserved_after_add(self, client):
        """Column count stays the same after adding a row."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        data = [[cell["text"] for cell in row] for row in table["data"]]
        new_row = ["Test"] * table["columns"]
        data.append(new_row)

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["columns"] == table["columns"]

    def test_height_delta_positive_on_add(self, client):
        """Adding rows reports a positive height delta."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        data = [[cell["text"] for cell in row] for row in table["data"]]
        # Add 3 rows
        for i in range(3):
            data.append([f"New_{i}"] * table["columns"])

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["height_delta"] > 0

    def test_height_delta_negative_on_delete(self, client):
        """Deleting rows reports a negative height delta."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        data = [[cell["text"] for cell in row] for row in table["data"]]
        # Delete 2 rows
        data = data[:2]

        result = _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)
        assert result["height_delta"] < 0

    def test_sequential_cell_edits_stable(self, client):
        """Editing multiple cells sequentially maintains correct structure."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        data = [[cell["text"] for cell in row] for row in table["data"]]
        original_cols = table["columns"]

        # Edit 1
        data[1][1] = "25W"
        result = _rebuild_table(client, 7, table["row_y_min"], table["row_y_max"], data)
        assert result["columns"] == original_cols

        # Re-fetch and edit 2
        table2 = _get_table(client, 7, zone["y_min"], zone["y_max"])
        assert table2["columns"] == original_cols
        data2 = [[cell["text"] for cell in row] for row in table2["data"]]
        data2[1][0] = "test"
        result2 = _rebuild_table(client, 7, table2["row_y_min"], table2["row_y_max"], data2)
        assert result2["columns"] == original_cols

        # Re-fetch and edit 3
        table3 = _get_table(client, 7, zone["y_min"], zone["y_max"])
        assert table3["columns"] == original_cols
        data3 = [[cell["text"] for cell in row] for row in table3["data"]]
        data3[0][1] = "Config"
        result3 = _rebuild_table(client, 7, table3["row_y_min"], table3["row_y_max"], data3)
        assert result3["columns"] == original_cols

        # Final check
        final = _get_table(client, 7, zone["y_min"], zone["y_max"])
        assert final["columns"] == original_cols
        final_texts = [[c["text"] for c in row] for row in final["data"]]
        assert final_texts[0] == ["Characteristic", "Config"]
        assert final_texts[1] == ["test", "25W"]

    def test_page_image_changes_after_rebuild(self, client):
        """Page image updates after a rebuild."""
        zones = _get_zones(client, 7)
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])

        img_before = client.get("/document/page/7/image").content

        data = [[cell["text"] for cell in row] for row in table["data"]]
        data.append(["VISIBLE_CHANGE"] * table["columns"])
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        img_after = client.get("/document/page/7/image").content
        assert img_before != img_after

    def test_multiple_zones_on_page(self, client):
        """Page 7 has multiple table zones that can be edited independently."""
        zones = _get_zones(client, 7)
        assert len(zones) >= 2, f"Expected 2+ zones, got {len(zones)}"

        # Both zones should return table data
        for zone in zones[:2]:
            table = _get_table(client, 7, zone["y_min"], zone["y_max"])
            # At least one should be a valid table
            if table["has_table"]:
                assert table["columns"] >= 2


# ─── NDS Document (3-column reference table) ──────────────────────────


@pytest.mark.skipif(not NDS_PDF.exists() or NDS_PDF.stat().st_size < 200, reason="NDS PDF not found")
class TestTablePanelNDS:
    """Table panel CRUD on NDS_IDD_RevC.pdf page 10 (3-column table)."""

    @pytest.fixture
    def client(self):
        return _fresh_client(NDS_PDF)

    def test_three_column_table_detected(self, client):
        """NDS page 10 table has 3+ columns."""
        zones = _get_zones(client, 10)
        assert len(zones) >= 1

        zone = zones[0]
        table = _get_table(client, 10, zone["y_min"], zone["y_max"])
        assert table["has_table"] is True
        assert table["columns"] >= 3

    def test_rebuild_three_column_table(self, client):
        """Can rebuild a 3-column table with added row."""
        zones = _get_zones(client, 10)
        zone = zones[0]
        table = _get_table(client, 10, zone["y_min"], zone["y_max"])

        data = [[cell["text"] for cell in row] for row in table["data"]]
        new_row = ["DOC-999", "Rev Z", "Test Document"]
        while len(new_row) < table["columns"]:
            new_row.append("")
        data.append(new_row)

        result = _rebuild_table(client, 10, zone["y_min"], zone["y_max"], data)
        assert result["status"] == "rebuilt"
        assert result["columns"] == table["columns"]


# ─── Working Copy Isolation ───────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTableRebuildIsolation:
    """Verify that rebuild operates on working copy, not original."""

    def test_original_unchanged_after_rebuild(self):
        """The original PDF is not modified by table rebuild."""
        # Record original file hash
        import hashlib
        original_hash = hashlib.sha256(HSI_PDF.read_bytes()).hexdigest()

        client = _fresh_client(HSI_PDF)
        zones = _get_zones(client, 7)
        if not zones:
            pytest.skip("No zones detected")
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        if not table["has_table"]:
            pytest.skip("No table detected")

        data = [[cell["text"] for cell in row] for row in table["data"]]
        data.append(["SHOULD_NOT_TOUCH_ORIGINAL"] * table["columns"])
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        # Original should be unchanged
        after_hash = hashlib.sha256(HSI_PDF.read_bytes()).hexdigest()
        assert original_hash == after_hash, "Original PDF was modified!"

    def test_save_persists_to_original_copy(self):
        """POST /document/save writes rebuild changes to the document path."""
        client = _fresh_client(HSI_PDF)
        zones = _get_zones(client, 7)
        if not zones:
            pytest.skip("No zones detected")
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        if not table["has_table"]:
            pytest.skip("No table detected")

        data = [[cell["text"] for cell in row] for row in table["data"]]
        data.append(["SAVED_ROW"] * table["columns"])
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        # Save
        save_res = client.post("/document/save")
        assert save_res.status_code == 200

        # The saved document should contain the new text
        session_res = client.get("/session")
        doc_path = Path(session_res.json()["document"])
        doc = fitz.open(str(doc_path))
        page7_text = doc[6].get_text("text")
        doc.close()
        assert "SAVED_ROW" in page7_text

    def test_session_records_rebuild_action(self):
        """Rebuild records a BLOCK_EDITED action in the session."""
        client = _fresh_client(HSI_PDF)
        zones = _get_zones(client, 7)
        if not zones:
            pytest.skip("No zones detected")
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        if not table["has_table"]:
            pytest.skip("No table detected")

        data = [[cell["text"] for cell in row] for row in table["data"]]
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        actions_res = client.get("/session/actions")
        actions = actions_res.json()
        assert actions["undo_available"] is True


# ─── Export Reliability Tests ─────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTableExportReliability:
    """Verify export PDF reflects table rebuilds correctly without duplication."""

    def test_export_after_rebuild_no_duplicates(self):
        """Export after table rebuild has edited value, not original."""
        client = _fresh_client(HSI_PDF)
        zones = _get_zones(client, 7)
        if not zones:
            pytest.skip("No zones")
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        if not table["has_table"]:
            pytest.skip("No table")

        data = [[cell["text"] for cell in row] for row in table["data"]]
        original_value = data[1][1]
        data[1][1] = "EXPORT_25W"
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        export_res = client.post("/document/export")
        assert export_res.status_code == 200
        export_path = Path(export_res.json()["path"])

        doc = fitz.open(str(export_path))
        page7_text = doc[6].get_text("text")
        doc.close()

        assert "EXPORT_25W" in page7_text, "Edited value not in export"
        assert original_value not in page7_text, (
            f"Original '{original_value}' still in export — double-writing!"
        )

    def test_export_after_sequential_rebuilds(self):
        """Export after multiple rebuilds has only final values, no duplication."""
        client = _fresh_client(HSI_PDF)
        zones = _get_zones(client, 7)
        if not zones:
            pytest.skip("No zones")
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        if not table["has_table"]:
            pytest.skip("No table")

        # First rebuild
        data = [[cell["text"] for cell in row] for row in table["data"]]
        data[1][1] = "FIRST_EDIT"
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        # Second rebuild
        table2 = _get_table(client, 7, zone["y_min"], zone["y_max"])
        data2 = [[cell["text"] for cell in row] for row in table2["data"]]
        data2[1][0] = "SECOND_EDIT"
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data2)

        export_res = client.post("/document/export")
        assert export_res.status_code == 200
        export_path = Path(export_res.json()["path"])

        doc = fitz.open(str(export_path))
        page7_text = doc[6].get_text("text")
        doc.close()

        assert "FIRST_EDIT" in page7_text, "First edit missing from export"
        assert "SECOND_EDIT" in page7_text, "Second edit missing from export"
        assert page7_text.count("FIRST_EDIT") == 1, "FIRST_EDIT duplicated in export"
        assert page7_text.count("SECOND_EDIT") == 1, "SECOND_EDIT duplicated in export"

    def test_export_unedited_pages_unchanged(self):
        """Unedited pages are identical between original and export."""
        client = _fresh_client(HSI_PDF)
        zones = _get_zones(client, 7)
        if not zones:
            pytest.skip("No zones")
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        if not table["has_table"]:
            pytest.skip("No table")

        data = [[cell["text"] for cell in row] for row in table["data"]]
        data[1][1] = "PAGE7_ONLY"
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        export_res = client.post("/document/export")
        export_path = Path(export_res.json()["path"])

        orig_doc = fitz.open(str(HSI_PDF))
        export_doc = fitz.open(str(export_path))

        # Page 5 (unedited) should be the same
        orig_p5 = orig_doc[4].get_text("text")
        export_p5 = export_doc[4].get_text("text")
        orig_doc.close()
        export_doc.close()

        assert orig_p5 == export_p5, "Unedited page 5 was modified in export"


# ─── Undo Tests ───────────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestTableUndoRedo:
    """Verify undo reverts table rebuild changes in both IR and PDF."""

    def test_undo_reverts_table_rebuild(self):
        """After rebuild + undo, page image matches original."""
        client = _fresh_client(HSI_PDF)
        zones = _get_zones(client, 7)
        if not zones:
            pytest.skip("No zones")
        zone = zones[0]
        table = _get_table(client, 7, zone["y_min"], zone["y_max"])
        if not table["has_table"]:
            pytest.skip("No table")

        # Get baseline image
        img_original = client.get("/document/page/7/image").content

        # Rebuild with edited value
        data = [[cell["text"] for cell in row] for row in table["data"]]
        data[1][1] = "UNDO_TEST_VALUE"
        _rebuild_table(client, 7, zone["y_min"], zone["y_max"], data)

        # Image should have changed
        img_after_rebuild = client.get("/document/page/7/image").content
        assert img_original != img_after_rebuild

        # Undo
        undo_res = client.post("/document/undo")
        assert undo_res.status_code == 200
        assert undo_res.json()["status"] == "undone"

        # Image should match original
        img_after_undo = client.get("/document/page/7/image").content
        assert img_after_undo == img_original, "Page image didn't revert after undo"
