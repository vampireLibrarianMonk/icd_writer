"""Confluence connector — talks to Confluence Cloud REST API v2 (or mock)."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import requests

from .base import (
    ConnectorConfig,
    ConnectorType,
    RemoteFile,
    RemotePage,
    RemoteSpace,
    RemoteVersion,
)

logger = logging.getLogger(__name__)


class ConfluenceClient:
    """Client for Confluence REST API (Cloud v2 + v1 content endpoints)."""

    def __init__(self, config: ConnectorConfig):
        if config.connector_type != ConnectorType.CONFLUENCE:
            raise ValueError(f"Expected CONFLUENCE config, got {config.connector_type}")
        self.base_url = config.base_url.rstrip("/")
        self.token = config.token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Make a GET request and return JSON response."""
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get_bytes(self, path: str) -> bytes:
        """Make a GET request and return raw bytes."""
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content

    def test_connection(self) -> bool:
        """Verify connection by listing spaces."""
        try:
            data = self._get("/wiki/api/v2/spaces", params={"limit": 1})
            return "results" in data
        except Exception as e:
            logger.warning(f"Confluence connection test failed: {e}")
            return False

    def list_spaces(self) -> list[RemoteSpace]:
        """List all accessible Confluence spaces."""
        data = self._get("/wiki/api/v2/spaces", params={"limit": 50})
        results = data.get("results", [])
        return [
            RemoteSpace(
                id=s["id"],
                name=s["name"],
                key=s.get("key", ""),
                description=s.get("description", {}).get("plain", {}).get("value", ""),
            )
            for s in results
        ]

    def list_pages(self, space_id: str) -> list[RemotePage]:
        """List pages within a space."""
        data = self._get(f"/wiki/api/v2/spaces/{space_id}/pages", params={"limit": 50})
        results = data.get("results", [])
        return [
            RemotePage(
                id=p["id"],
                title=p["title"],
                space_id=space_id,
                parent_id=p.get("parentId"),
                version=p.get("version", {}).get("number", 1),
                modified_at=p.get("version", {}).get("createdAt", ""),
                author=p.get("authorId", ""),
            )
            for p in results
        ]

    def list_files(self, page_id: str) -> list[RemoteFile]:
        """List attachments on a page."""
        data = self._get(f"/wiki/rest/api/content/{page_id}/child/attachment", params={"limit": 50})
        results = data.get("results", [])
        return [
            RemoteFile(
                id=a["id"],
                filename=a["title"],
                size_bytes=a.get("extensions", {}).get("fileSize", 0),
                media_type=a.get("extensions", {}).get("mediaType", "application/octet-stream"),
                download_url=a.get("_links", {}).get("download", ""),
                modified_at="",
            )
            for a in results
        ]

    def get_page_body(self, page_id: str) -> str:
        """Get page HTML body content."""
        data = self._get(
            f"/wiki/rest/api/content/{page_id}",
            params={"expand": "body.storage"},
        )
        return data.get("body", {}).get("storage", {}).get("value", "")

    def download_file(self, file: RemoteFile) -> bytes:
        """Download an attachment."""
        if not file.download_url:
            raise ValueError(f"No download URL for file: {file.filename}")
        return self._get_bytes(file.download_url)

    def export_page_pdf(self, page_id: str) -> bytes:
        """Export a page as PDF."""
        return self._get_bytes(f"/wiki/rest/api/content/{page_id}/export/pdf")

    def get_versions(self, file_id: str) -> list[RemoteVersion]:
        """Confluence attachments have limited version history via content API."""
        # Confluence v1 API: /content/{id}/history
        # For simplicity, return single current version
        return [RemoteVersion(id="current", modified_at="", size_bytes=0)]
