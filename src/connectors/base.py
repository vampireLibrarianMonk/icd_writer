"""Base connector interface for enterprise document sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol


class ConnectorType(str, Enum):
    CONFLUENCE = "confluence"
    SHAREPOINT = "sharepoint"


@dataclass
class ConnectorConfig:
    """Configuration for a connector instance."""

    connector_type: ConnectorType
    base_url: str
    token: str
    enabled: bool = True
    # Connector-specific settings
    extra: dict = field(default_factory=dict)


@dataclass
class RemoteSpace:
    """A space/site/library in the remote system."""

    id: str
    name: str
    key: str = ""
    description: str = ""


@dataclass
class RemotePage:
    """A page or folder in the remote system."""

    id: str
    title: str
    space_id: str = ""
    parent_id: str | None = None
    version: int = 1
    modified_at: str = ""
    author: str = ""
    has_children: bool = False


@dataclass
class RemoteFile:
    """A downloadable file/attachment in the remote system."""

    id: str
    filename: str
    size_bytes: int = 0
    media_type: str = "application/octet-stream"
    download_url: str = ""
    modified_at: str = ""
    version_count: int = 1


@dataclass
class RemoteVersion:
    """A version entry for a file."""

    id: str
    modified_at: str
    size_bytes: int = 0
    author: str = ""


class ConnectorClient(Protocol):
    """Protocol that all connector clients must implement."""

    def test_connection(self) -> bool:
        """Verify the connection works. Returns True on success."""
        ...

    def list_spaces(self) -> list[RemoteSpace]:
        """List available spaces/sites/libraries."""
        ...

    def list_pages(self, space_id: str) -> list[RemotePage]:
        """List pages/folders within a space."""
        ...

    def list_files(self, page_id: str) -> list[RemoteFile]:
        """List downloadable files/attachments on a page/folder."""
        ...

    def download_file(self, file: RemoteFile) -> bytes:
        """Download a file's content as bytes."""
        ...

    def get_versions(self, file_id: str) -> list[RemoteVersion]:
        """Get version history for a file."""
        ...
