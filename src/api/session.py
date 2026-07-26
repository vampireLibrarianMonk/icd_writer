"""Session and action journal.

Every user action is recorded as an immutable event. This enables:
- Undo/redo (traverse the event list)
- Session replay (re-apply all events from scratch)
- Audit trail (who changed what, when)
- Crash recovery (replay journal to restore state)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of user actions tracked in the journal."""

    DOCUMENT_OPENED = "document_opened"
    BLOCK_SELECTED = "block_selected"
    BLOCK_EDITED = "block_edited"
    BLOCK_REVERTED = "block_reverted"
    PAGE_RENDERED = "page_rendered"
    DOCUMENT_SAVED = "document_saved"
    DOCUMENT_EXPORTED = "document_exported"
    OCR_REQUESTED = "ocr_requested"
    REVIEW_CONFIRMED = "review_confirmed"
    UNDO = "undo"
    REDO = "redo"


class Action(BaseModel):
    """A single recorded user action."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action_type: ActionType
    page: int | None = None
    block_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    """A user editing session with full action journal."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    document_path: str = ""
    document_sha256: str = ""
    actions: list[Action] = Field(default_factory=list)
    undo_stack: list[Action] = Field(default_factory=list)
    redo_stack: list[Action] = Field(default_factory=list)

    def record(self, action_type: ActionType, **kwargs: Any) -> Action:
        """Record an action and clear the redo stack."""
        action = Action(action_type=action_type, **kwargs)
        self.actions.append(action)
        if action_type == ActionType.BLOCK_EDITED:
            self.undo_stack.append(action)
            self.redo_stack.clear()
        return action

    def undo(self) -> Action | None:
        """Undo the last edit action."""
        if not self.undo_stack:
            return None
        action = self.undo_stack.pop()
        self.redo_stack.append(action)
        self.record(ActionType.UNDO, data={"undone_action_id": action.id})
        return action

    def redo(self) -> Action | None:
        """Redo the last undone action."""
        if not self.redo_stack:
            return None
        action = self.redo_stack.pop()
        self.undo_stack.append(action)
        self.record(ActionType.REDO, data={"redone_action_id": action.id})
        return action

    @property
    def edit_count(self) -> int:
        """Number of edit actions in this session."""
        return sum(1 for a in self.actions if a.action_type == ActionType.BLOCK_EDITED)

    def save_journal(self, path: Path | str) -> None:
        """Persist the full session journal to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load_journal(cls, path: Path | str) -> "Session":
        """Load a session from a journal file."""
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(data)
