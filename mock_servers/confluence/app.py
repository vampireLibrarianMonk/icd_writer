"""Mock Confluence REST API Server.

Replicates the exact Confluence Cloud REST API v2 (and v1 content endpoints)
that our connector calls. Seeded from test_corpus files. Responds with the
same JSON shapes, status codes, and headers as real Confluence.

Endpoints implemented:
  GET  /wiki/api/v2/spaces                              → list spaces
  GET  /wiki/api/v2/spaces/{space_id}/pages             → list pages in space
  GET  /wiki/rest/api/content/{page_id}                 → get page (v1, supports expand)
  GET  /wiki/rest/api/content/{page_id}/child/attachment → list attachments
  GET  /wiki/rest/api/content/{page_id}/export/pdf      → export page as PDF
  GET  /download/attachments/{attach_id}/{filename}     → download attachment file
  GET  /wiki/api/v2/pages/{page_id}                     → get page (v2)

Auth: Accepts any Bearer token or Basic auth (mock — no validation).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse

app = FastAPI(
    title="Mock Confluence API",
    description="Local test stub replicating Confluence Cloud REST API",
    version="1.0.0",
)

# ─── Data Loading ──────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"


def _load_json(filename: str) -> dict | list:
    path = DATA_DIR / filename
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _get_spaces() -> list[dict]:
    return _load_json("spaces.json")


def _get_pages() -> list[dict]:
    return _load_json("pages.json")


def _get_attachments() -> list[dict]:
    return _load_json("attachments.json")


# ─── Auth Middleware (permissive) ──────────────────────────────────────


def _check_auth(authorization: str | None = Header(None)):
    """Accept any auth header — we just verify one is present."""
    # In production, this would validate OAuth/PAT tokens.
    # For testing, we accept anything but require the header exists.
    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─── Confluence REST API v2: Spaces ────────────────────────────────────


@app.get("/wiki/api/v2/spaces")
def list_spaces(
    limit: int = 25,
    cursor: str | None = None,
    authorization: str | None = Header(None),
):
    """List all spaces the user has access to.

    Response matches Confluence Cloud API v2 format exactly.
    """
    _check_auth(authorization)
    spaces = _get_spaces()

    results = spaces[:limit]
    return {
        "results": [
            {
                "id": s["id"],
                "key": s["key"],
                "name": s["name"],
                "type": s.get("type", "global"),
                "status": "current",
                "homepageId": s.get("homepage_id", ""),
                "description": {"plain": {"value": s.get("description", "")}},
                "_links": {
                    "webui": f"/spaces/{s['key']}",
                },
            }
            for s in results
        ],
        "_links": {
            "next": f"/wiki/api/v2/spaces?cursor=end" if len(spaces) > limit else "",
        },
    }


# ─── Confluence REST API v2: Pages ─────────────────────────────────────


@app.get("/wiki/api/v2/spaces/{space_id}/pages")
def list_pages_in_space(
    space_id: str,
    limit: int = 25,
    authorization: str | None = Header(None),
):
    """List pages within a space.

    Response matches Confluence Cloud API v2 pages endpoint.
    """
    _check_auth(authorization)
    pages = _get_pages()

    # Filter by space
    space_pages = [p for p in pages if p.get("space_id") == space_id]
    results = space_pages[:limit]

    return {
        "results": [
            {
                "id": p["id"],
                "title": p["title"],
                "status": "current",
                "spaceId": space_id,
                "parentId": p.get("parent_id"),
                "parentType": "page" if p.get("parent_id") else None,
                "authorId": p.get("author_id", "user-001"),
                "createdAt": p.get("created_at", "2024-01-15T10:00:00.000Z"),
                "version": {
                    "number": p.get("version", 1),
                    "createdAt": p.get("modified_at", "2024-06-01T12:00:00.000Z"),
                },
                "_links": {
                    "webui": f"/spaces/{space_id}/pages/{p['id']}",
                    "editui": f"/spaces/{space_id}/pages/{p['id']}/edit",
                },
            }
            for p in results
        ],
        "_links": {"next": ""},
    }


# ─── Confluence REST API v1: Content (with expand) ─────────────────────


@app.get("/wiki/rest/api/content/{page_id}")
def get_content(
    page_id: str,
    expand: str = "",
    authorization: str | None = Header(None),
):
    """Get page content (v1 API — supports expand=body.storage).

    This is the endpoint used for fetching page HTML body.
    """
    _check_auth(authorization)
    pages = _get_pages()
    page = next((p for p in pages if p["id"] == page_id), None)

    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    result = {
        "id": page["id"],
        "type": "page",
        "status": "current",
        "title": page["title"],
        "space": {"key": page.get("space_key", "ENG")},
        "version": {"number": page.get("version", 1)},
        "history": {
            "lastUpdated": {
                "when": page.get("modified_at", "2024-06-01T12:00:00.000Z"),
                "by": {"displayName": page.get("author", "Systems Engineering")},
            }
        },
        "_links": {
            "webui": f"/pages/{page_id}",
            "self": f"/wiki/rest/api/content/{page_id}",
        },
    }

    if "body.storage" in expand:
        # Serve the HTML body from file if it exists
        body_file = DATA_DIR / "bodies" / f"{page_id}.html"
        if body_file.exists():
            body_html = body_file.read_text(encoding="utf-8")
        else:
            body_html = f"<p>{page.get('summary', 'Page content')}</p>"

        result["body"] = {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        }

    return result


# ─── Confluence REST API v2: Pages (v2 format) ─────────────────────────


@app.get("/wiki/api/v2/pages/{page_id}")
def get_page_v2(
    page_id: str,
    body_format: str = "storage",
    authorization: str | None = Header(None),
):
    """Get page (v2 API format)."""
    _check_auth(authorization)
    pages = _get_pages()
    page = next((p for p in pages if p["id"] == page_id), None)

    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    return {
        "id": page["id"],
        "title": page["title"],
        "status": "current",
        "spaceId": page.get("space_id", ""),
        "version": {
            "number": page.get("version", 1),
            "createdAt": page.get("modified_at", "2024-06-01T12:00:00.000Z"),
        },
    }


# ─── Confluence REST API v1: Attachments ───────────────────────────────


@app.get("/wiki/rest/api/content/{page_id}/child/attachment")
def list_attachments(
    page_id: str,
    limit: int = 25,
    authorization: str | None = Header(None),
):
    """List attachments on a page.

    Response matches Confluence v1 attachment endpoint format.
    """
    _check_auth(authorization)
    attachments = _get_attachments()

    page_attachments = [a for a in attachments if a.get("page_id") == page_id]
    results = page_attachments[:limit]

    return {
        "results": [
            {
                "id": a["id"],
                "type": "attachment",
                "status": "current",
                "title": a["filename"],
                "metadata": {
                    "mediaType": a.get("media_type", "application/octet-stream"),
                    "comment": a.get("comment", ""),
                },
                "extensions": {
                    "mediaType": a.get("media_type", "application/octet-stream"),
                    "fileSize": a.get("file_size", 0),
                },
                "_links": {
                    "download": f"/download/attachments/{a['id']}/{a['filename']}",
                    "self": f"/wiki/rest/api/content/{a['id']}",
                },
            }
            for a in results
        ],
        "size": len(results),
        "_links": {},
    }


# ─── Confluence: Export Page as PDF ────────────────────────────────────


@app.get("/wiki/rest/api/content/{page_id}/export/pdf")
def export_page_pdf(
    page_id: str,
    authorization: str | None = Header(None),
):
    """Export a page as PDF.

    Returns PDF bytes. In real Confluence, this renders the page to PDF.
    We serve a pre-generated PDF from the data directory.
    """
    _check_auth(authorization)

    pdf_path = DATA_DIR / "exports" / f"{page_id}.pdf"
    if not pdf_path.exists():
        # Fallback: serve any available PDF
        exports_dir = DATA_DIR / "exports"
        if exports_dir.exists():
            pdfs = list(exports_dir.glob("*.pdf"))
            if pdfs:
                pdf_path = pdfs[0]

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF export not available")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"export_{page_id}.pdf",
    )


# ─── Confluence: Download Attachment ───────────────────────────────────


@app.get("/download/attachments/{attachment_id}/{filename}")
def download_attachment(
    attachment_id: str,
    filename: str,
    authorization: str | None = Header(None),
):
    """Download an attachment file.

    Serves the actual file from the data/attachments directory.
    """
    _check_auth(authorization)

    file_path = DATA_DIR / "attachments" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Attachment not found: {filename}")

    # Determine media type
    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".tiff": "image/tiff",
        ".html": "text/html",
    }
    media_type = media_types.get(file_path.suffix.lower(), "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )


# ─── Health Check ──────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-confluence"}
