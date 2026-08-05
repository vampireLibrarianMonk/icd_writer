# Session Management — Design

## Current State

- Session lives in-memory only (lost on backend restart)
- "Save Session" buried under File menu, writes a JSON journal to disk
- No load-back capability
- No session browser/timeline view
- No save-as (always writes to same path)

## Target UX

### Top-Level "Session" Menu (replaces File > Save Session)

| Menu Item | Action |
|-----------|--------|
| Session > Save | Saves current session to the default path (or last-used path) |
| Session > Save As... | Prompts for filename, saves session bundle |
| Session > Load... | File picker to load a previously saved session |
| Session > New | Starts fresh session (confirms if unsaved changes) |

### Session Tab (right panel, alongside Editor/Search/TBDs/Diff)

Shows the action journal as a timeline:
- Timestamp + action type + summary
- Each entry shows: "12:34 — Edited block-p07-b13 on page 7"
- Clicking an entry could jump to that page
- Visual indicator of current position in undo stack

## Implementation

### Backend

**Session file format** (`.icd-session` JSON):
```json
{
  "version": "1.0",
  "created_at": "2026-08-01T...",
  "document_path": "icds/digital/HSI_SYS_015G.pdf",
  "document_sha256": "a604e12...",
  "actions": [...],  // Full action journal
  "undo_stack_ids": ["abc123", ...],
  "redo_stack_ids": []
}
```

**New endpoints:**
- `POST /session/save-as` — accepts `{"path": "sessions/my_edits.icd-session"}`, writes file
- `POST /session/load` — accepts file upload or path, restores session state + replays actions onto IR
- `GET /session/journal` — returns full action list with timestamps for the Session tab

**Load logic:**
1. Open the document referenced in the session file
2. Replay all BLOCK_EDITED actions in order to reconstruct the IR state
3. Restore undo/redo stacks

### Frontend

**Toolbar changes:**
- Add "Session" top-level menu between "File" and "Edit" (or replace the save item in File)
- Session tab in right panel

**Session tab component:**
- Fetches `GET /session/journal` on mount
- Renders a scrollable timeline
- Each entry: icon (edit/undo/open) + time + description
- Current position indicator (entries after undo are grayed)

## Phases

### Phase A: Backend persistence (Save/Load endpoints)
- `POST /session/save-as` writes JSON file
- `POST /session/load` reads file, opens document, replays actions
- `GET /session/journal` returns formatted action list

### Phase B: Frontend Session menu
- Add "Session" to toolbar with Save/Save As/Load/New
- Wire to backend endpoints

### Phase C: Session tab
- New tab component showing the journal timeline
- Auto-refreshes after edits

## Open Questions

1. Where to store session files? `./sessions/` directory? User-specified?
2. Should Load prompt for "discard current changes?" if unsaved?
3. Should the session file embed the document IR delta (for offline use) or just the actions (replay from source)?
   - Recommend: actions only (smaller, source PDF must be available)
