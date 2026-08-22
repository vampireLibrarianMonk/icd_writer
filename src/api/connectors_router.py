"""API router for enterprise document connectors (Confluence, SharePoint).

Provides endpoints for:
- Configuring connector credentials
- Testing connections
- Browsing remote spaces/pages/files
- Downloading files from remote sources
- Listing configured connectors and their status
"""

from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.connectors.base import ConnectorConfig, ConnectorType
from src.connectors.confluence import ConfluenceClient
from src.connectors.sharepoint import SharePointClient

router = APIRouter(prefix="/connectors", tags=["connectors"])

# ─── In-memory connector state ────────────────────────────────────────

_configs: dict[str, ConnectorConfig] = {}
_clients: dict[str, ConfluenceClient | SharePointClient] = {}


def _get_or_create_client(connector_type: str) -> ConfluenceClient | SharePointClient:
    """Get cached client or raise if not configured."""
    if connector_type not in _configs:
        raise HTTPException(404, f"Connector not configured: {connector_type}")
    if connector_type not in _clients:
        config = _configs[connector_type]
        if config.connector_type == ConnectorType.CONFLUENCE:
            _clients[connector_type] = ConfluenceClient(config)
        else:
            _clients[connector_type] = SharePointClient(config)
    return _clients[connector_type]


# ─── Auto-configure from environment ──────────────────────────────────


def _auto_configure():
    """Load connector configs from environment variables if present."""
    # Confluence
    confluence_url = os.environ.get("CONFLUENCE_URL", "")
    confluence_token = os.environ.get("CONFLUENCE_TOKEN", "")
    if confluence_url and confluence_token:
        _configs["confluence"] = ConnectorConfig(
            connector_type=ConnectorType.CONFLUENCE,
            base_url=confluence_url,
            token=confluence_token,
        )

    # SharePoint
    sharepoint_url = os.environ.get("SHAREPOINT_URL", "")
    sharepoint_token = os.environ.get("SHAREPOINT_TOKEN", "")
    if sharepoint_url and sharepoint_token:
        site_id = os.environ.get("SHAREPOINT_SITE_ID", "site-engineering")
        _configs["sharepoint"] = ConnectorConfig(
            connector_type=ConnectorType.SHAREPOINT,
            base_url=sharepoint_url,
            token=sharepoint_token,
            extra={"site_id": site_id},
        )


_auto_configure()


# ─── Request/Response Models ──────────────────────────────────────────


class ConfigureRequest(BaseModel):
    url: str
    token: str
    site_id: str = ""  # SharePoint only


# ─── List Connectors ──────────────────────────────────────────────────


@router.get("")
def list_connectors():
    """List all configured connectors and their connection status."""
    connectors = []

    for ctype in ["confluence", "sharepoint"]:
        config = _configs.get(ctype)
        connectors.append({
            "type": ctype,
            "configured": config is not None,
            "enabled": config.enabled if config else False,
            "url": config.base_url if config else "",
        })

    return {"connectors": connectors}


# ─── Configure ────────────────────────────────────────────────────────


@router.post("/confluence/configure")
def configure_confluence(req: ConfigureRequest):
    """Configure or update Confluence connector credentials."""
    config = ConnectorConfig(
        connector_type=ConnectorType.CONFLUENCE,
        base_url=req.url.rstrip("/"),
        token=req.token,
    )
    _configs["confluence"] = config
    _clients.pop("confluence", None)  # Clear cached client

    # Test the connection
    client = ConfluenceClient(config)
    success = client.test_connection()
    if success:
        _clients["confluence"] = client

    return {"status": "configured", "connected": success}


@router.post("/sharepoint/configure")
def configure_sharepoint(req: ConfigureRequest):
    """Configure or update SharePoint connector credentials."""
    config = ConnectorConfig(
        connector_type=ConnectorType.SHAREPOINT,
        base_url=req.url.rstrip("/"),
        token=req.token,
        extra={"site_id": req.site_id or "site-engineering"},
    )
    _configs["sharepoint"] = config
    _clients.pop("sharepoint", None)

    client = SharePointClient(config)
    success = client.test_connection()
    if success:
        _clients["sharepoint"] = client

    return {"status": "configured", "connected": success}


# ─── Test Connection ──────────────────────────────────────────────────


@router.get("/{connector_type}/test")
def test_connection(connector_type: str):
    """Test if a configured connector can reach its remote service."""
    if connector_type not in _configs:
        raise HTTPException(404, f"Not configured: {connector_type}")

    client = _get_or_create_client(connector_type)
    success = client.test_connection()
    return {"connector": connector_type, "connected": success}


# ─── Browse: Spaces ───────────────────────────────────────────────────


@router.get("/{connector_type}/spaces")
def list_spaces(connector_type: str):
    """List available spaces/drives in the remote system."""
    client = _get_or_create_client(connector_type)
    spaces = client.list_spaces()
    return {
        "connector": connector_type,
        "spaces": [asdict(s) for s in spaces],
    }


# ─── Browse: Pages/Items ──────────────────────────────────────────────


@router.get("/{connector_type}/spaces/{space_id}/pages")
def list_pages(connector_type: str, space_id: str):
    """List pages/items within a space or drive."""
    client = _get_or_create_client(connector_type)
    pages = client.list_pages(space_id)
    return {
        "connector": connector_type,
        "space_id": space_id,
        "pages": [asdict(p) for p in pages],
    }


# ─── Browse: Files/Attachments ────────────────────────────────────────


@router.get("/{connector_type}/pages/{page_id}/files")
def list_files(connector_type: str, page_id: str):
    """List files/attachments on a page."""
    client = _get_or_create_client(connector_type)
    files = client.list_files(page_id)
    return {
        "connector": connector_type,
        "page_id": page_id,
        "files": [asdict(f) for f in files],
    }


# ─── Download ─────────────────────────────────────────────────────────


@router.get("/{connector_type}/download/{file_id}")
def download_file(connector_type: str, file_id: str, filename: str = ""):
    """Download a file from the remote system.

    For Confluence: file_id is the attachment ID, filename is the attachment name.
    For SharePoint: file_id is the item ID, requires drive_id context.
    """
    from fastapi.responses import Response

    client = _get_or_create_client(connector_type)

    if connector_type == "confluence":
        # Build a RemoteFile with the download URL
        from src.connectors.base import RemoteFile
        remote_file = RemoteFile(
            id=file_id,
            filename=filename or "download",
            download_url=f"/download/attachments/{file_id}/{filename}",
        )
        content = client.download_file(remote_file)
    elif connector_type == "sharepoint":
        # For SharePoint, download by drive + item
        drive_id = "drive-interface-data"  # Default; could be query param
        content = client.download_item(drive_id, file_id)
    else:
        raise HTTPException(400, f"Unknown connector: {connector_type}")

    # Determine content type from filename
    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".tiff": "image/tiff",
    }
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    media_type = media_types.get(ext, "application/octet-stream")

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Versions ─────────────────────────────────────────────────────────


@router.get("/{connector_type}/files/{file_id}/versions")
def get_file_versions(connector_type: str, file_id: str, drive_id: str = ""):
    """Get version history for a remote file."""
    client = _get_or_create_client(connector_type)

    if connector_type == "sharepoint" and hasattr(client, "get_versions"):
        versions = client.get_versions(file_id, drive_id or None)
    else:
        versions = client.get_versions(file_id)

    return {
        "connector": connector_type,
        "file_id": file_id,
        "versions": [asdict(v) for v in versions],
    }
