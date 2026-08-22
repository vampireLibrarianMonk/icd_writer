"""API router for credential management (CRUD against app-local store + Secrets Manager).

Provides a unified credential store for all connector services. Users can:
- List stored credentials (names + URLs, never exposes tokens)
- Add new credentials
- Update existing credentials
- Delete credentials
- Test a credential against its target service

Credentials are stored in-memory for the running app and optionally
persisted to AWS Secrets Manager for cross-restart persistence.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/credentials", tags=["credentials"])

# ─── In-Memory Credential Store ───────────────────────────────────────

# Each credential is stored as: { id, service, name, url, token, extra, created_at, last_tested }
_credentials: dict[str, dict] = {}
_next_id = 1


def _generate_id() -> str:
    global _next_id
    cred_id = f"cred-{_next_id:03d}"
    _next_id += 1
    return cred_id


# ─── Request/Response Models ──────────────────────────────────────────


class CredentialCreate(BaseModel):
    service: str  # "confluence", "sharepoint", or custom
    name: str  # user-friendly label (e.g., "HESSI Confluence", "JSC SharePoint")
    url: str
    token: str
    site_id: str = ""  # SharePoint site ID, optional
    notes: str = ""


class CredentialUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    token: str | None = None
    site_id: str | None = None
    notes: str | None = None


# ─── CRUD Endpoints ───────────────────────────────────────────────────


@router.get("")
def list_credentials():
    """List all stored credentials (tokens masked)."""
    results = []
    for cred_id, cred in _credentials.items():
        results.append({
            "id": cred_id,
            "service": cred["service"],
            "name": cred["name"],
            "url": cred["url"],
            "site_id": cred.get("site_id", ""),
            "notes": cred.get("notes", ""),
            "token_preview": _mask_token(cred["token"]),
            "created_at": cred["created_at"],
            "last_tested": cred.get("last_tested"),
            "last_test_result": cred.get("last_test_result"),
        })
    return {"credentials": results}


@router.post("")
def create_credential(req: CredentialCreate):
    """Add a new credential to the store."""
    cred_id = _generate_id()
    _credentials[cred_id] = {
        "service": req.service,
        "name": req.name,
        "url": req.url.rstrip("/"),
        "token": req.token,
        "site_id": req.site_id,
        "notes": req.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_tested": None,
        "last_test_result": None,
    }
    _sync_to_secrets_manager()
    return {"id": cred_id, "status": "created"}


@router.get("/{cred_id}")
def get_credential(cred_id: str):
    """Get a single credential's details (token masked)."""
    cred = _credentials.get(cred_id)
    if not cred:
        raise HTTPException(404, f"Credential not found: {cred_id}")
    return {
        "id": cred_id,
        "service": cred["service"],
        "name": cred["name"],
        "url": cred["url"],
        "site_id": cred.get("site_id", ""),
        "notes": cred.get("notes", ""),
        "token_preview": _mask_token(cred["token"]),
        "created_at": cred["created_at"],
        "last_tested": cred.get("last_tested"),
        "last_test_result": cred.get("last_test_result"),
    }


@router.put("/{cred_id}")
def update_credential(cred_id: str, req: CredentialUpdate):
    """Update an existing credential."""
    cred = _credentials.get(cred_id)
    if not cred:
        raise HTTPException(404, f"Credential not found: {cred_id}")

    if req.name is not None:
        cred["name"] = req.name
    if req.url is not None:
        cred["url"] = req.url.rstrip("/")
    if req.token is not None:
        cred["token"] = req.token
    if req.site_id is not None:
        cred["site_id"] = req.site_id
    if req.notes is not None:
        cred["notes"] = req.notes

    _sync_to_secrets_manager()
    return {"id": cred_id, "status": "updated"}


@router.delete("/{cred_id}")
def delete_credential(cred_id: str):
    """Delete a credential from the store."""
    if cred_id not in _credentials:
        raise HTTPException(404, f"Credential not found: {cred_id}")
    del _credentials[cred_id]
    _sync_to_secrets_manager()
    return {"id": cred_id, "status": "deleted"}


@router.post("/{cred_id}/test")
def test_credential(cred_id: str):
    """Test a stored credential against its target service."""
    cred = _credentials.get(cred_id)
    if not cred:
        raise HTTPException(404, f"Credential not found: {cred_id}")

    from src.connectors.base import ConnectorConfig, ConnectorType
    from src.connectors.confluence import ConfluenceClient
    from src.connectors.sharepoint import SharePointClient

    service = cred["service"]
    url = _resolve_url(cred["url"])
    token = cred["token"]

    success = False
    error_msg = ""

    try:
        if service == "confluence":
            config = ConnectorConfig(
                connector_type=ConnectorType.CONFLUENCE,
                base_url=url,
                token=token,
            )
            client = ConfluenceClient(config)
            success = client.test_connection()
        elif service == "sharepoint":
            config = ConnectorConfig(
                connector_type=ConnectorType.SHAREPOINT,
                base_url=url,
                token=token,
                extra={"site_id": cred.get("site_id", "site-engineering")},
            )
            client = SharePointClient(config)
            success = client.test_connection()
        else:
            # Generic HTTP test — just try to reach the URL
            import requests
            resp = requests.get(f"{url}/health", timeout=5, headers={"Authorization": f"Bearer {token}"})
            success = resp.status_code == 200
    except Exception as e:
        error_msg = str(e)

    # Record test result
    cred["last_tested"] = datetime.now(timezone.utc).isoformat()
    cred["last_test_result"] = "success" if success else f"failed: {error_msg}"

    return {
        "id": cred_id,
        "connected": success,
        "error": error_msg if not success else None,
        "tested_at": cred["last_tested"],
    }


# ─── Helpers ──────────────────────────────────────────────────────────


def _mask_token(token: str) -> str:
    """Show first 4 and last 4 characters, mask the middle."""
    if len(token) <= 10:
        return "••••••••"
    return token[:4] + "•" * (len(token) - 8) + token[-4:]


def _resolve_url(url: str) -> str:
    """Translate localhost URLs to Docker container names when in Docker."""
    url = url.rstrip("/")
    in_docker = os.environ.get("OPENSEARCH_HOST") == "opensearch"
    if in_docker:
        url_map = {
            "http://localhost:8090": "http://mock-confluence:8090",
            "http://localhost:8091": "http://mock-sharepoint:8091",
            "http://127.0.0.1:8090": "http://mock-confluence:8090",
            "http://127.0.0.1:8091": "http://mock-sharepoint:8091",
        }
        return url_map.get(url, url)
    return url


def _sync_to_secrets_manager():
    """Persist all credentials to AWS Secrets Manager (best-effort)."""
    try:
        import boto3
        import json

        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)

        payload = {}
        for cred_id, cred in _credentials.items():
            payload[cred_id] = {
                "service": cred["service"],
                "name": cred["name"],
                "url": cred["url"],
                "token": cred["token"],
                "site_id": cred.get("site_id", ""),
                "notes": cred.get("notes", ""),
                "created_at": cred["created_at"],
            }

        secret_string = json.dumps(payload)
        secret_name = "icd-writer/credentials"

        try:
            client.update_secret(SecretId=secret_name, SecretString=secret_string)
        except client.exceptions.ResourceNotFoundException:
            client.create_secret(Name=secret_name, SecretString=secret_string)
    except Exception:
        pass  # Secrets Manager unavailable — operate in-memory only


def _load_from_secrets_manager():
    """Load credentials from Secrets Manager on startup."""
    global _next_id
    try:
        import boto3
        import json

        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId="icd-writer/credentials")
        data = json.loads(response["SecretString"])

        for cred_id, cred in data.items():
            _credentials[cred_id] = {
                "service": cred["service"],
                "name": cred["name"],
                "url": cred["url"],
                "token": cred["token"],
                "site_id": cred.get("site_id", ""),
                "notes": cred.get("notes", ""),
                "created_at": cred.get("created_at", ""),
                "last_tested": None,
                "last_test_result": None,
            }

        # Set next_id past existing IDs
        if _credentials:
            max_num = max(int(k.split("-")[1]) for k in _credentials.keys() if k.startswith("cred-"))
            _next_id = max_num + 1
    except Exception:
        pass  # No saved credentials or Secrets Manager unavailable


# Load on module init
_load_from_secrets_manager()


def _seed_from_env():
    """Seed credential store from connector env vars if not already populated."""
    from datetime import datetime, timezone

    global _next_id

    # Don't seed if we already have credentials (from Secrets Manager)
    if _credentials:
        return

    confluence_url = os.environ.get("CONFLUENCE_URL", "")
    confluence_token = os.environ.get("CONFLUENCE_TOKEN", "")
    if confluence_url and confluence_token:
        cred_id = _generate_id()
        _credentials[cred_id] = {
            "service": "confluence",
            "name": "Confluence (auto-configured)",
            "url": confluence_url,
            "token": confluence_token,
            "site_id": "",
            "notes": "Auto-configured from CONFLUENCE_URL environment variable",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_tested": None,
            "last_test_result": None,
        }

    sharepoint_url = os.environ.get("SHAREPOINT_URL", "")
    sharepoint_token = os.environ.get("SHAREPOINT_TOKEN", "")
    if sharepoint_url and sharepoint_token:
        cred_id = _generate_id()
        _credentials[cred_id] = {
            "service": "sharepoint",
            "name": "SharePoint (auto-configured)",
            "url": sharepoint_url,
            "token": sharepoint_token,
            "site_id": os.environ.get("SHAREPOINT_SITE_ID", "site-engineering"),
            "notes": "Auto-configured from SHAREPOINT_URL environment variable",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_tested": None,
            "last_test_result": None,
        }


_seed_from_env()
