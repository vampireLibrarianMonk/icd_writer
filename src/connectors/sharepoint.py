"""SharePoint connector — talks to Microsoft Graph API v1.0 (or mock)."""

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


class SharePointClient:
    """Client for Microsoft Graph API (SharePoint document libraries)."""

    def __init__(self, config: ConnectorConfig):
        if config.connector_type != ConnectorType.SHAREPOINT:
            raise ValueError(f"Expected SHAREPOINT config, got {config.connector_type}")
        self.base_url = config.base_url.rstrip("/")
        self.token = config.token
        self.site_id = config.extra.get("site_id", "site-engineering")
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
        """Verify connection by listing drives."""
        try:
            data = self._get(f"/sites/{self.site_id}/drives")
            return "value" in data
        except Exception as e:
            logger.warning(f"SharePoint connection test failed: {e}")
            return False

    def list_spaces(self) -> list[RemoteSpace]:
        """List document libraries (drives) as spaces."""
        data = self._get(f"/sites/{self.site_id}/drives")
        drives = data.get("value", [])
        return [
            RemoteSpace(
                id=d["id"],
                name=d["name"],
                key=d["id"],
                description=d.get("description", ""),
            )
            for d in drives
        ]

    def list_pages(self, space_id: str) -> list[RemotePage]:
        """List items in root of a drive (folders and files treated as pages)."""
        data = self._get(f"/drives/{space_id}/root/children")
        items = data.get("value", [])
        return [
            RemotePage(
                id=item["id"],
                title=item["name"],
                space_id=space_id,
                parent_id=item.get("parentReference", {}).get("id"),
                version=1,
                modified_at=item.get("lastModifiedDateTime", ""),
                author=item.get("lastModifiedBy", {}).get("user", {}).get("displayName", ""),
                has_children="folder" in item,
            )
            for item in items
        ]

    def list_folder_children(self, drive_id: str, folder_id: str) -> list[RemotePage]:
        """List children of a specific folder."""
        data = self._get(f"/drives/{drive_id}/items/{folder_id}/children")
        items = data.get("value", [])
        return [
            RemotePage(
                id=item["id"],
                title=item["name"],
                space_id=drive_id,
                parent_id=folder_id,
                version=1,
                modified_at=item.get("lastModifiedDateTime", ""),
                author=item.get("lastModifiedBy", {}).get("user", {}).get("displayName", ""),
                has_children="folder" in item,
            )
            for item in items
        ]

    def list_files(self, page_id: str) -> list[RemoteFile]:
        """For SharePoint, list_pages already returns files. This gets file details."""
        # In Graph API, files are driveItems. We return the page itself as a file.
        # This is used when a page IS a file (not a folder).
        data = self._get(f"/drives/{self.site_id}/items/{page_id}")
        if "file" not in data:
            return []
        return [
            RemoteFile(
                id=data["id"],
                filename=data["name"],
                size_bytes=data.get("size", 0),
                media_type=data.get("file", {}).get("mimeType", "application/octet-stream"),
                download_url=f"/drives/{data.get('parentReference', {}).get('driveId', self.site_id)}/items/{data['id']}/content",
                modified_at=data.get("lastModifiedDateTime", ""),
            )
        ]

    def download_file(self, file: RemoteFile) -> bytes:
        """Download file content."""
        if not file.download_url:
            raise ValueError(f"No download URL for: {file.filename}")
        return self._get_bytes(file.download_url)

    def download_item(self, drive_id: str, item_id: str) -> bytes:
        """Download a drive item by IDs directly."""
        return self._get_bytes(f"/drives/{drive_id}/items/{item_id}/content")

    def get_versions(self, file_id: str, drive_id: str | None = None) -> list[RemoteVersion]:
        """Get version history for a file."""
        d = drive_id or "drive-interface-data"
        data = self._get(f"/drives/{d}/items/{file_id}/versions")
        versions = data.get("value", [])
        return [
            RemoteVersion(
                id=v["id"],
                modified_at=v.get("lastModifiedDateTime", ""),
                size_bytes=v.get("size", 0),
                author=v.get("lastModifiedBy", {}).get("user", {}).get("displayName", ""),
            )
            for v in versions
        ]

    def get_delta(self, drive_id: str, token: str = "") -> tuple[list[RemotePage], str]:
        """Delta query — returns changed items and a new delta token."""
        params = {"token": token} if token else {}
        data = self._get(f"/drives/{drive_id}/root/delta", params=params)
        items = data.get("value", [])
        delta_link = data.get("@odata.deltaLink", "")
        # Extract token from delta link
        new_token = ""
        if "token=" in delta_link:
            new_token = delta_link.split("token=")[-1]

        pages = [
            RemotePage(
                id=item["id"],
                title=item["name"],
                space_id=drive_id,
                modified_at=item.get("lastModifiedDateTime", ""),
            )
            for item in items
        ]
        return pages, new_token
