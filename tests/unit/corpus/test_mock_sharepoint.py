"""Tests for Mock SharePoint (Graph API) — validates exact API contract replication.

Exercises the mock SharePoint server through FastAPI TestClient to verify
it returns responses matching the real Microsoft Graph API v1.0 format.
Tests cover authentication, drive listing, folder browsing, file download,
version history, and delta queries.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mock_servers.sharepoint.app import app

AUTH_HEADER = {"Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.mock-token"}


@pytest.fixture
def client():
    return TestClient(app)


# ─── Authentication ────────────────────────────────────────────────────


class TestSharePointAuth:
    """Verify auth enforcement matches real Graph API behavior."""

    def test_no_auth_returns_401(self, client):
        """Endpoints require Bearer token — 401 without."""
        res = client.get("/sites/site-engineering/drives")
        assert res.status_code == 401

    def test_non_bearer_returns_401(self, client):
        """Only Bearer tokens accepted (not Basic)."""
        res = client.get(
            "/sites/site-engineering/drives",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert res.status_code == 401

    def test_bearer_token_accepted(self, client):
        """Valid Bearer token gets 200."""
        res = client.get("/sites/site-engineering/drives", headers=AUTH_HEADER)
        assert res.status_code == 200


# ─── Drives (Document Libraries) ──────────────────────────────────────


class TestSharePointDrives:
    """Verify /sites/{id}/drives matches Graph API response format."""

    def test_list_drives_returns_value_array(self, client):
        """Response has 'value' array (Graph API collection format)."""
        res = client.get("/sites/site-engineering/drives", headers=AUTH_HEADER)
        assert res.status_code == 200
        data = res.json()
        assert "value" in data
        assert len(data["value"]) >= 2

    def test_drive_has_required_fields(self, client):
        """Each drive has id, name, driveType, quota, webUrl."""
        res = client.get("/sites/site-engineering/drives", headers=AUTH_HEADER)
        drives = res.json()["value"]
        for drive in drives:
            assert "id" in drive
            assert "name" in drive
            assert "driveType" in drive
            assert drive["driveType"] == "documentLibrary"
            assert "quota" in drive
            assert "webUrl" in drive

    def test_response_has_odata_context(self, client):
        """Response includes @odata.context (Graph API standard)."""
        res = client.get("/sites/site-engineering/drives", headers=AUTH_HEADER)
        data = res.json()
        assert "@odata.context" in data

    def test_interface_data_drive_present(self, client):
        """'Interface Data' drive is listed."""
        res = client.get("/sites/site-engineering/drives", headers=AUTH_HEADER)
        names = [d["name"] for d in res.json()["value"]]
        assert "Interface Data" in names


# ─── Folder Contents ──────────────────────────────────────────────────


class TestSharePointFolderBrowsing:
    """Verify folder listing matches Graph API driveItem collection."""

    def test_list_root_children(self, client):
        """GET /drives/{id}/root/children returns items."""
        res = client.get("/drives/drive-interface-data/root/children", headers=AUTH_HEADER)
        assert res.status_code == 200
        data = res.json()
        assert "value" in data
        assert len(data["value"]) >= 3

    def test_drive_item_has_required_fields(self, client):
        """Each item has id, name, size, timestamps, parentReference."""
        res = client.get("/drives/drive-interface-data/root/children", headers=AUTH_HEADER)
        items = res.json()["value"]
        for item in items:
            assert "id" in item
            assert "name" in item
            assert "size" in item
            assert "createdDateTime" in item
            assert "lastModifiedDateTime" in item
            assert "parentReference" in item

    def test_file_item_has_file_facet(self, client):
        """File items have 'file' facet with mimeType."""
        res = client.get("/drives/drive-interface-data/root/children", headers=AUTH_HEADER)
        items = res.json()["value"]
        files = [i for i in items if "file" in i]
        assert len(files) >= 1
        for f in files:
            assert "mimeType" in f["file"]

    def test_drawings_drive_has_images(self, client):
        """Drawings drive contains image files."""
        res = client.get("/drives/drive-drawings/root/children", headers=AUTH_HEADER)
        items = res.json()["value"]
        names = [i["name"] for i in items]
        assert any(n.endswith(".png") for n in names)
        assert any(n.endswith(".tiff") for n in names)


# ─── File Download ─────────────────────────────────────────────────────


class TestSharePointDownload:
    """Verify file download matches Graph API content endpoint."""

    def test_download_xlsx(self, client):
        """GET /drives/{id}/items/{id}/content returns XLSX file bytes."""
        res = client.get(
            "/drives/drive-interface-data/items/item-thermostat-params/content",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        # XLSX is ZIP (PK magic)
        assert res.content[:2] == b"PK"
        assert len(res.content) > 3000

    def test_download_png(self, client):
        """Can download PNG image files."""
        res = client.get(
            "/drives/drive-drawings/items/item-mount-drawing/content",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        assert res.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_download_tiff(self, client):
        """Can download TIFF files."""
        res = client.get(
            "/drives/drive-drawings/items/item-connector-pinout/content",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        # TIFF magic: II (little-endian) or MM (big-endian)
        assert res.content[:2] in (b"II", b"MM")

    def test_download_nonexistent_returns_404(self, client):
        """Missing item returns 404 with Graph API error format."""
        res = client.get(
            "/drives/drive-interface-data/items/item-fake/content",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 404


# ─── Version History ──────────────────────────────────────────────────


class TestSharePointVersions:
    """Verify version history matches Graph API format."""

    def test_versions_endpoint_returns_list(self, client):
        """GET /items/{id}/versions returns version collection."""
        res = client.get(
            "/drives/drive-interface-data/items/item-mass-props/versions",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert "value" in data
        assert len(data["value"]) >= 2

    def test_version_has_required_fields(self, client):
        """Each version has id, lastModifiedDateTime, size."""
        res = client.get(
            "/drives/drive-interface-data/items/item-mass-props/versions",
            headers=AUTH_HEADER,
        )
        versions = res.json()["value"]
        for v in versions:
            assert "id" in v
            assert "lastModifiedDateTime" in v
            assert "size" in v

    def test_mass_props_has_3_versions(self, client):
        """HSI Mass Properties has 3 versions (v1→v2→v3)."""
        res = client.get(
            "/drives/drive-interface-data/items/item-mass-props/versions",
            headers=AUTH_HEADER,
        )
        versions = res.json()["value"]
        assert len(versions) == 3

    def test_versions_ordered_chronologically(self, client):
        """Versions are in chronological order."""
        res = client.get(
            "/drives/drive-interface-data/items/item-mass-props/versions",
            headers=AUTH_HEADER,
        )
        versions = res.json()["value"]
        dates = [v["lastModifiedDateTime"] for v in versions]
        assert dates == sorted(dates), f"Versions not in order: {dates}"


# ─── Delta Query ──────────────────────────────────────────────────────


class TestSharePointDelta:
    """Verify delta query matches Graph API change tracking format."""

    def test_initial_delta_returns_all_items(self, client):
        """Delta with no token returns all items (initial sync)."""
        res = client.get("/drives/drive-interface-data/root/delta", headers=AUTH_HEADER)
        assert res.status_code == 200
        data = res.json()
        assert "value" in data
        assert len(data["value"]) >= 3
        assert "@odata.deltaLink" in data

    def test_subsequent_delta_returns_empty(self, client):
        """Delta with 'latest' token returns empty (no changes)."""
        res = client.get(
            "/drives/drive-interface-data/root/delta?token=latest",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["value"] == []
        assert "@odata.deltaLink" in data


# ─── Item Metadata ─────────────────────────────────────────────────────


class TestSharePointItemMetadata:
    """Verify single item GET matches Graph API driveItem format."""

    def test_get_item_metadata(self, client):
        """GET /drives/{id}/items/{id} returns full driveItem."""
        res = client.get(
            "/drives/drive-interface-data/items/item-thermostat-params",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        item = res.json()
        assert item["name"] == "Thermostat_Parameters.xlsx"
        assert "file" in item
        assert "mimeType" in item["file"]
        assert "lastModifiedBy" in item

    def test_nonexistent_item_returns_404(self, client):
        """Unknown item ID returns 404."""
        res = client.get(
            "/drives/drive-interface-data/items/item-nonexistent",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 404


# ─── Health ────────────────────────────────────────────────────────────


class TestSharePointHealth:
    """Verify health endpoint for docker-compose healthcheck."""

    def test_health_returns_ok(self, client):
        """Health endpoint returns 200 with status ok."""
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
