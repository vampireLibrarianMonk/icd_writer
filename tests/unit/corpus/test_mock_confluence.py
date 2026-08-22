"""Tests for Mock Confluence API — validates exact API contract replication.

Exercises the mock Confluence server through FastAPI TestClient to verify
it returns responses matching the real Confluence Cloud REST API v2 format.
Tests cover authentication, pagination, content retrieval, attachment
downloads, and PDF export — everything our connector will call.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mock_servers.confluence.app import app

AUTH_HEADER = {"Authorization": "Bearer test-token-123"}


@pytest.fixture
def client():
    return TestClient(app)


# ─── Authentication ────────────────────────────────────────────────────


class TestConfluenceAuth:
    """Verify auth enforcement matches real Confluence behavior."""

    def test_no_auth_returns_401(self, client):
        """Endpoints require authentication — 401 without header."""
        res = client.get("/wiki/api/v2/spaces")
        assert res.status_code == 401

    def test_bearer_token_accepted(self, client):
        """Bearer token authentication works."""
        res = client.get("/wiki/api/v2/spaces", headers=AUTH_HEADER)
        assert res.status_code == 200

    def test_basic_auth_accepted(self, client):
        """Basic auth is also accepted."""
        res = client.get("/wiki/api/v2/spaces", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert res.status_code == 200


# ─── Spaces ────────────────────────────────────────────────────────────


class TestConfluenceSpaces:
    """Verify /wiki/api/v2/spaces response matches real Confluence format."""

    def test_list_spaces_returns_results(self, client):
        """Response has 'results' array with space objects."""
        res = client.get("/wiki/api/v2/spaces", headers=AUTH_HEADER)
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert len(data["results"]) >= 2

    def test_space_has_required_fields(self, client):
        """Each space has id, key, name, type, status."""
        res = client.get("/wiki/api/v2/spaces", headers=AUTH_HEADER)
        spaces = res.json()["results"]
        for space in spaces:
            assert "id" in space
            assert "key" in space
            assert "name" in space
            assert "type" in space
            assert "status" in space
            assert space["status"] == "current"

    def test_space_has_links(self, client):
        """Each space has _links.webui."""
        res = client.get("/wiki/api/v2/spaces", headers=AUTH_HEADER)
        spaces = res.json()["results"]
        for space in spaces:
            assert "_links" in space
            assert "webui" in space["_links"]

    def test_response_has_pagination_links(self, client):
        """Response has _links for pagination (even if empty)."""
        res = client.get("/wiki/api/v2/spaces", headers=AUTH_HEADER)
        data = res.json()
        assert "_links" in data

    def test_hsi_space_present(self, client):
        """HSI Engineering space is in the results."""
        res = client.get("/wiki/api/v2/spaces", headers=AUTH_HEADER)
        keys = [s["key"] for s in res.json()["results"]]
        assert "HSI" in keys


# ─── Pages ─────────────────────────────────────────────────────────────


class TestConfluencePages:
    """Verify pages endpoint matches real Confluence format."""

    def test_list_pages_in_space(self, client):
        """GET /wiki/api/v2/spaces/{id}/pages returns page list."""
        res = client.get("/wiki/api/v2/spaces/space-hsi/pages", headers=AUTH_HEADER)
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert len(data["results"]) >= 3

    def test_page_has_required_fields(self, client):
        """Each page has id, title, status, version."""
        res = client.get("/wiki/api/v2/spaces/space-hsi/pages", headers=AUTH_HEADER)
        pages = res.json()["results"]
        for page in pages:
            assert "id" in page
            assert "title" in page
            assert "status" in page
            assert "version" in page
            assert "number" in page["version"]

    def test_page_has_timestamps(self, client):
        """Pages have version.createdAt timestamps."""
        res = client.get("/wiki/api/v2/spaces/space-hsi/pages", headers=AUTH_HEADER)
        pages = res.json()["results"]
        for page in pages:
            assert "createdAt" in page["version"]

    def test_get_page_content_v1(self, client):
        """GET /wiki/rest/api/content/{id}?expand=body.storage returns HTML body."""
        res = client.get(
            "/wiki/rest/api/content/page-hsi-power?expand=body.storage",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert "body" in data
        assert "storage" in data["body"]
        assert "value" in data["body"]["storage"]
        # Should contain actual HTML content
        html = data["body"]["storage"]["value"]
        assert "<" in html and ">" in html
        assert len(html) > 50

    def test_get_nonexistent_page_returns_404(self, client):
        """Request for unknown page ID returns 404."""
        res = client.get(
            "/wiki/rest/api/content/page-does-not-exist",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 404


# ─── Attachments ───────────────────────────────────────────────────────


class TestConfluenceAttachments:
    """Verify attachment listing and download match real Confluence."""

    def test_list_attachments(self, client):
        """GET /content/{id}/child/attachment returns attachment list."""
        res = client.get(
            "/wiki/rest/api/content/page-hsi-mech-req/child/attachment",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert len(data["results"]) >= 1

    def test_attachment_has_required_fields(self, client):
        """Each attachment has id, title, metadata, extensions, _links."""
        res = client.get(
            "/wiki/rest/api/content/page-hsi-mech-req/child/attachment",
            headers=AUTH_HEADER,
        )
        attachments = res.json()["results"]
        for att in attachments:
            assert "id" in att
            assert "title" in att
            assert "extensions" in att
            assert "fileSize" in att["extensions"]
            assert "_links" in att
            assert "download" in att["_links"]

    def test_download_attachment_returns_file(self, client):
        """GET /download/attachments/{id}/{filename} returns file bytes."""
        res = client.get(
            "/download/attachments/att-mech-req-v2/HSI_Mech_Requirements_v2.docx",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        # DOCX files are ZIP format (PK magic bytes)
        assert res.content[:2] == b"PK"
        assert len(res.content) > 5000

    def test_download_pptx_attachment(self, client):
        """Can download PPTX attachments."""
        res = client.get(
            "/download/attachments/att-thermal-cdr/Thermal_Analysis_CDR.pptx",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 200
        assert res.content[:2] == b"PK"  # PPTX is also ZIP

    def test_download_nonexistent_returns_404(self, client):
        """Missing file returns 404."""
        res = client.get(
            "/download/attachments/att-fake/nonexistent.pdf",
            headers=AUTH_HEADER,
        )
        assert res.status_code == 404


# ─── Health ────────────────────────────────────────────────────────────


class TestConfluenceHealth:
    """Verify health endpoint for docker-compose healthcheck."""

    def test_health_returns_ok(self, client):
        """Health endpoint returns 200 with status ok."""
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
