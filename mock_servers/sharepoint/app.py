"""Mock SharePoint (Microsoft Graph API) Server.

Replicates the exact Microsoft Graph API v1.0 endpoints for SharePoint
document libraries. Responds with the same JSON shapes, pagination, and
headers as real Graph API.

Endpoints implemented:
  GET  /sites/{site_id}/drives                      → list document libraries
  GET  /drives/{drive_id}/root/children             → list root folder items
  GET  /drives/{drive_id}/items/{item_id}/children  → list folder contents
  GET  /drives/{drive_id}/items/{item_id}/content   → download file
  GET  /drives/{drive_id}/items/{item_id}           → get item metadata
  GET  /drives/{drive_id}/items/{item_id}/versions  → version history
  GET  /drives/{drive_id}/root/delta                → delta query (changed items)

Auth: Accepts any Bearer token (mock — no validation, but requires header).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response

app = FastAPI(
    title="Mock SharePoint (Graph API)",
    description="Local test stub replicating Microsoft Graph API for SharePoint",
    version="1.0.0",
)

# ─── Data Loading ──────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"


def _load_json(filename: str) -> dict | list:
    path = DATA_DIR / filename
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _get_drives() -> list[dict]:
    return _load_json("drives.json")


def _get_items() -> list[dict]:
    return _load_json("items.json")


# ─── Auth ──────────────────────────────────────────────────────────────


def _check_auth(authorization: str | None = Header(None)):
    """Require Bearer token (any value accepted for testing)."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "InvalidAuthenticationToken", "message": "Access token is empty."}},
        )


# ─── Graph API: List Drives (Document Libraries) ──────────────────────


@app.get("/sites/{site_id}/drives")
def list_drives(
    site_id: str,
    authorization: str | None = Header(None),
):
    """List document libraries for a SharePoint site.

    Response matches Microsoft Graph /sites/{id}/drives format.
    """
    _check_auth(authorization)
    drives = _get_drives()

    site_drives = [d for d in drives if d.get("site_id") == site_id]

    return {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#drives",
        "value": [
            {
                "id": d["id"],
                "name": d["name"],
                "description": d.get("description", ""),
                "driveType": "documentLibrary",
                "createdDateTime": d.get("created_at", "2024-01-01T00:00:00Z"),
                "lastModifiedDateTime": d.get("modified_at", "2025-06-01T00:00:00Z"),
                "quota": {
                    "total": 27487790694400,
                    "used": d.get("used_bytes", 1048576),
                    "remaining": 27487789645824,
                    "state": "normal",
                },
                "owner": {
                    "group": {"displayName": d.get("owner", "Engineering")},
                },
                "webUrl": f"https://contoso.sharepoint.com/sites/{site_id}/{d['name']}",
            }
            for d in site_drives
        ],
    }


# ─── Graph API: List Root Folder Contents ──────────────────────────────


@app.get("/drives/{drive_id}/root/children")
def list_root_children(
    drive_id: str,
    authorization: str | None = Header(None),
):
    """List items in the root of a document library.

    Response matches Microsoft Graph driveItem collection format.
    """
    _check_auth(authorization)
    items = _get_items()

    # Root items have no parent_id or parent_id == "root"
    root_items = [
        i for i in items
        if i.get("drive_id") == drive_id and i.get("parent_id") in (None, "", "root")
    ]

    return {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#drives('{}')/root/children".format(drive_id),
        "value": [_format_drive_item(item) for item in root_items],
    }


# ─── Graph API: List Folder Contents ──────────────────────────────────


@app.get("/drives/{drive_id}/items/{item_id}/children")
def list_item_children(
    drive_id: str,
    item_id: str,
    authorization: str | None = Header(None),
):
    """List children of a folder item.

    Response matches Microsoft Graph driveItem children format.
    """
    _check_auth(authorization)
    items = _get_items()

    children = [
        i for i in items
        if i.get("drive_id") == drive_id and i.get("parent_id") == item_id
    ]

    return {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#driveItems",
        "value": [_format_drive_item(item) for item in children],
    }


# ─── Graph API: Get Item Metadata ─────────────────────────────────────


@app.get("/drives/{drive_id}/items/{item_id}")
def get_item(
    drive_id: str,
    item_id: str,
    authorization: str | None = Header(None),
):
    """Get metadata for a single drive item.

    Response matches Microsoft Graph driveItem format.
    """
    _check_auth(authorization)
    items = _get_items()

    item = next(
        (i for i in items if i.get("drive_id") == drive_id and i["id"] == item_id),
        None,
    )
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "itemNotFound", "message": f"Item {item_id} not found"}},
        )

    return _format_drive_item(item)


# ─── Graph API: Download File Content ──────────────────────────────────


@app.get("/drives/{drive_id}/items/{item_id}/content")
def download_item_content(
    drive_id: str,
    item_id: str,
    authorization: str | None = Header(None),
):
    """Download file content.

    In real Graph API, this returns a 302 redirect to a download URL.
    For testing, we serve the file directly.
    """
    _check_auth(authorization)
    items = _get_items()

    item = next(
        (i for i in items if i.get("drive_id") == drive_id and i["id"] == item_id),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.get("is_folder"):
        raise HTTPException(status_code=400, detail="Cannot download a folder")

    # Resolve file path
    filename = item["name"]
    file_path = DATA_DIR / "files" / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".html": "text/html",
    }
    media_type = media_types.get(file_path.suffix.lower(), "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )


# ─── Graph API: Version History ────────────────────────────────────────


@app.get("/drives/{drive_id}/items/{item_id}/versions")
def list_item_versions(
    drive_id: str,
    item_id: str,
    authorization: str | None = Header(None),
):
    """List version history for a file.

    Response matches Microsoft Graph driveItemVersion collection.
    """
    _check_auth(authorization)
    items = _get_items()

    item = next(
        (i for i in items if i.get("drive_id") == drive_id and i["id"] == item_id),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    versions = item.get("versions", [])
    if not versions:
        # Default: single current version
        versions = [
            {
                "id": "1.0",
                "lastModifiedDateTime": item.get("modified_at", "2024-06-01T00:00:00Z"),
                "size": item.get("size", 0),
            }
        ]

    return {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#versions",
        "value": [
            {
                "id": v["id"],
                "lastModifiedDateTime": v["lastModifiedDateTime"],
                "size": v.get("size", item.get("size", 0)),
                "lastModifiedBy": {
                    "user": {"displayName": v.get("author", "Engineering")}
                },
            }
            for v in versions
        ],
    }


# ─── Graph API: Delta Query ───────────────────────────────────────────


@app.get("/drives/{drive_id}/root/delta")
def delta_query(
    drive_id: str,
    token: str = "",
    authorization: str | None = Header(None),
):
    """Delta query — returns items changed since last sync.

    If no token provided, returns all items (initial sync).
    If token is "latest", returns empty (no changes).
    """
    _check_auth(authorization)
    items = _get_items()

    if token == "latest":
        # No changes since last sync
        return {
            "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#driveItems",
            "value": [],
            "@odata.deltaLink": f"/drives/{drive_id}/root/delta?token=latest",
        }

    # Initial sync or stale token — return all items
    drive_items = [i for i in items if i.get("drive_id") == drive_id]

    return {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#driveItems",
        "value": [_format_drive_item(item) for item in drive_items],
        "@odata.deltaLink": f"/drives/{drive_id}/root/delta?token=latest",
    }


# ─── Helper ────────────────────────────────────────────────────────────


def _format_drive_item(item: dict) -> dict:
    """Format an item dict into Microsoft Graph driveItem shape."""
    result = {
        "id": item["id"],
        "name": item["name"],
        "size": item.get("size", 0),
        "createdDateTime": item.get("created_at", "2024-01-01T00:00:00Z"),
        "lastModifiedDateTime": item.get("modified_at", "2024-06-01T00:00:00Z"),
        "webUrl": f"https://contoso.sharepoint.com/sites/eng/{item['name']}",
        "createdBy": {"user": {"displayName": item.get("author", "Engineering")}},
        "lastModifiedBy": {"user": {"displayName": item.get("modified_by", "Engineering")}},
        "parentReference": {
            "driveId": item.get("drive_id", ""),
            "id": item.get("parent_id", "root"),
        },
    }

    if item.get("is_folder"):
        result["folder"] = {"childCount": item.get("child_count", 0)}
    else:
        result["file"] = {
            "mimeType": item.get("mime_type", "application/octet-stream"),
            "hashes": {"sha256Hash": item.get("sha256", "")},
        }

    return result


# ─── Health Check ──────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-sharepoint"}
