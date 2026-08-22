# Panel Architecture — Activity Rail + Grouped Panels + Panel Manager

**Priority:** High (prerequisite for connector UI integration)
**Status:** Design complete, ready to implement
**Last updated:** 2026-08-22

---

## Problem

The current right panel has 6 flat tabs:
```
[ 📝 Editor | 🔍 Search | 📋 TBDs | 📊 Compare | 📁 Docs | 📜 Session ]
```

Adding Confluence, SharePoint, and Lineage as top-level tabs gives 9+ tabs — too many
to fit, cognitively cluttered, and no way to hide tabs the user doesn't need.

---

## Design

### Three-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ App Layout                                                            │
│                                                                       │
│  ┌─────────────────────┐  ┌──┐  ┌────────────────────────────────┐  │
│  │                      │  │  │  │   PANEL CONTENT                │  │
│  │                      │  │  │  │                                │  │
│  │   Document Viewer    │  │R │  │  [Sub-tab A] [Sub-tab B] [C]  │  │
│  │                      │  │A │  │  ───────────────────────────── │  │
│  │                      │  │I │  │                                │  │
│  │                      │  │L │  │  (active panel content here)   │  │
│  │                      │  │  │  │                                │  │
│  │                      │  │  │  │                                │  │
│  │                      │  │  │  │                                │  │
│  │                      │  │⚙️│  │                                │  │
│  └─────────────────────┘  └──┘  └────────────────────────────────┘  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

**Layer 1: Activity Rail** (narrow vertical bar, ~40px)
- Icon buttons for panel groups
- Always visible (never hidden)
- Bottom icon opens Panel Manager

**Layer 2: Panel Content Area** (resizable, current panelWidth)
- Shows the active group's content
- Has sub-tabs for groups that contain multiple views

**Layer 3: Panel Manager** (popover from ⚙️ icon)
- Checkboxes to enable/disable individual panels
- State persisted in localStorage

---

## Activity Rail Groups

| Position | Icon | Group ID | Label | Sub-panels |
|----------|------|----------|-------|-----------|
| 1 | ✏️ | `editor` | Editor | (single — no sub-tabs) |
| 2 | 🔍 | `discover` | Discover | Search, TBD Dashboard |
| 3 | 📄 | `sources` | Sources | Local Docs, Confluence, SharePoint, Lineage |
| 4 | 🔀 | `compare` | Compare | (single — Revision Compare) |
| 5 | 📜 | `session` | Session | Session Timeline, Costs |
| — | ⚙️ | — | Settings | Opens Panel Manager popover |

### Why This Grouping

- **Editor** stays alone — it's the primary editing context (auto-switches on element click)
- **Discover** = "find things in the indexed corpus" — search and TBDs are both discovery tools
- **Sources** = "where do documents come from?" — local files, Confluence, SharePoint, and lineage are all about document provenance
- **Compare** stays alone — it's a full-screen workflow (revision selection + section accordion)
- **Session** = "what have I done?" — action journal and costs are session introspection

---

## Sub-Tab Behavior

Within a group that has multiple sub-panels:

```
┌──────────────────────────────────────┐
│ 📄 Sources                            │
│ ┌──────┐ ┌──────────┐ ┌──────────┐  │
│ │ Local│ │Confluence│ │SharePoint│  │
│ └──────┘ └──────────┘ └──────────┘  │
│ ┌──────┐                             │
│ │Lineage│                            │
│ └──────┘                             │
│ ─────────────────────────────────── │
│                                       │
│ (sub-panel content here)              │
│                                       │
└──────────────────────────────────────┘
```

- Sub-tabs are small pill buttons below the group header
- Active sub-tab persists per group (remembered when switching away and back)
- Sub-tabs that are disabled via Panel Manager don't render

---

## Panel Manager

Triggered by ⚙️ icon at bottom of activity rail. Popover panel:

```
┌─────────────────────────────────┐
│ Panel Visibility          [✕]   │
├─────────────────────────────────┤
│                                 │
│ EDITOR                          │
│  ☑ Unified Editor               │
│                                 │
│ DISCOVER                        │
│  ☑ Search                       │
│  ☑ TBD Dashboard                │
│                                 │
│ SOURCES                         │
│  ☑ Local Documents              │
│  ☐ Confluence (not configured)  │
│  ☐ SharePoint (not configured)  │
│  ☑ Lineage                      │
│                                 │
│ COMPARE                         │
│  ☑ Revision Compare             │
│                                 │
│ SESSION                         │
│  ☑ Session Timeline             │
│  ☐ Cost Tracking                │
│                                 │
└─────────────────────────────────┘
```

**Rules:**
- Disabled panels are hidden from sub-tabs AND from the group (if all sub-panels disabled, group icon dims)
- Unconfigured connectors show "(not configured)" and are disabled by default
- Once a connector is configured (via Settings), its panel auto-enables
- Editor is always enabled (can't disable)
- State persists in `localStorage.panelVisibility`

---

## State Management (Zustand)

```typescript
interface PanelState {
  // Which group is active in the rail
  activeGroup: "editor" | "discover" | "sources" | "compare" | "session";

  // Which sub-tab is active within each group
  activeSubTab: {
    discover: "search" | "tbd";
    sources: "local" | "confluence" | "sharepoint" | "lineage";
    session: "timeline" | "costs";
  };

  // Visibility (panel manager toggles)
  visibility: {
    search: boolean;
    tbd: boolean;
    local: boolean;
    confluence: boolean;
    sharepoint: boolean;
    lineage: boolean;
    compare: boolean;
    timeline: boolean;
    costs: boolean;
  };

  // Actions
  setActiveGroup: (group: string) => void;
  setSubTab: (group: string, tab: string) => void;
  toggleVisibility: (panel: string) => void;
}
```

Persisted to localStorage on every change. Loaded on app start.

---

## Connector Configuration Flow

When user first clicks a disabled "Confluence" or "SharePoint" sub-tab:

1. Instead of showing empty content, show a **Setup Card**:
```
┌─────────────────────────────────────┐
│ Connect to Confluence               │
│                                     │
│ Confluence is not configured yet.   │
│                                     │
│ URL: [________________________]     │
│ Token: [_____________________]      │
│ Spaces: [____________________]      │
│                                     │
│        [ Test Connection ]          │
│        [ Save & Connect  ]          │
│                                     │
└─────────────────────────────────────┘
```

2. On successful connection, the panel switches to the browser view
3. Configuration stored in backend (`.env` or `POST /connectors/configure`)
4. Panel Manager auto-enables the panel

This means users never see a broken empty tab — either they see the setup card
or the working browser.

---

## Component Structure

```
frontend/src/components/
├── panels/
│   ├── ActivityRail.tsx              # Vertical icon bar
│   ├── PanelManager.tsx              # Visibility popover
│   ├── PanelContainer.tsx            # Renders active group + sub-tabs
│   ├── SubTabBar.tsx                 # Pill-style sub-tab selector
│   │
│   ├── editor/
│   │   └── UnifiedEditor.tsx         # (existing, moved here)
│   │
│   ├── discover/
│   │   ├── SearchPanel.tsx           # (existing, moved here)
│   │   └── TBDDashboardPanel.tsx     # (existing, moved here)
│   │
│   ├── sources/
│   │   ├── LocalDocsPanel.tsx        # (existing DocumentManagerPanel, renamed)
│   │   ├── ConfluencePanel.tsx       # NEW — space/page browser
│   │   ├── SharePointPanel.tsx       # NEW — drive/folder browser
│   │   ├── LineagePanel.tsx          # NEW — time-ordered source chain
│   │   └── ConnectorSetupCard.tsx    # Shown for unconfigured connectors
│   │
│   ├── compare/
│   │   └── RevisionComparePanel.tsx  # (existing, moved here)
│   │
│   └── session/
│       ├── SessionPanel.tsx          # (existing, moved here)
│       └── CostPanel.tsx             # (existing costs, extracted)
│
└── stores/
    └── panelStore.ts                 # Zustand store for panel state
```

---

## Migration Plan

### Phase 1: Refactor Layout (no new features)
1. Create `ActivityRail.tsx` + `PanelContainer.tsx`
2. Move existing panels into group folders (no rename yet)
3. Replace flat tab bar with rail + panel content area
4. Sub-tabs for Discover (Search / TBDs) and Session (Timeline / Costs)
5. All existing functionality preserved — just reorganized visually
6. Add `panelStore.ts` with visibility state

### Phase 2: Panel Manager
1. Create `PanelManager.tsx` popover
2. Wire checkboxes to visibility state
3. Persist to localStorage
4. Disabled panels hidden from sub-tabs

### Phase 3: Connector Panels (empty shells)
1. Create `ConfluencePanel.tsx` — setup card only (no actual connection)
2. Create `SharePointPanel.tsx` — setup card only
3. Create `LineagePanel.tsx` — static mockup showing timeline design
4. Add to Sources group sub-tabs (disabled by default)

### Phase 4: Wire to Backend
1. Connect ConfluencePanel to `/connectors/confluence/*` endpoints
2. Connect SharePointPanel to `/connectors/sharepoint/*` endpoints
3. Connect LineagePanel to `/lineage/{doc_stem}` endpoint
4. Import from source → feeds into existing ingest pipeline

---

## Visual Design Notes

### Activity Rail Styling
- Width: 40px
- Background: `var(--bg-tertiary)` (slightly darker than panel)
- Icons: 20px, centered
- Active indicator: 2px left border in accent color
- Hover: slight background highlight
- Tooltip on hover showing group name

### Sub-Tab Styling
- Small pill buttons (not full-width tabs)
- Background: transparent (inactive), `var(--bg-primary)` (active)
- Font: 12px, medium weight
- Spacing: 4px gap between pills
- Wrapped if needed (for narrow panel widths)

### Panel Manager Styling
- Popover anchored to ⚙️ icon
- Grouped with section headers (EDITOR, DISCOVER, etc.)
- Checkboxes with label
- "(not configured)" in muted text for unconfigured connectors
- Close on click outside or ✕ button

---

## Current App.tsx Changes (Phase 1)

Replace the current `<div>` with tabs:

```tsx
// Before (current):
<div style={{ width: panelWidth, ... }}>
  <div style={{ display: "flex" }}> {/* flat tab bar */}
    <PanelTab label="📝 Editor" ... />
    <PanelTab label="🔍 Search" ... />
    ...
  </div>
  <div style={{ flex: 1 }}>
    {activePanel === "editor" && <UnifiedEditor />}
    ...
  </div>
</div>

// After (Phase 1):
<ActivityRail
  activeGroup={activeGroup}
  onGroupChange={setActiveGroup}
  onOpenSettings={() => setShowPanelManager(true)}
/>
<PanelContainer
  width={panelWidth}
  activeGroup={activeGroup}
  activeSubTab={activeSubTab}
  onSubTabChange={setSubTab}
  visibility={visibility}
/>
{showPanelManager && (
  <PanelManager
    visibility={visibility}
    onToggle={toggleVisibility}
    onClose={() => setShowPanelManager(false)}
  />
)}
```

---

## Auto-Switch Behavior (Preserved)

Current behavior where clicking a document element auto-switches to Editor
is preserved. The event listener logic stays the same, just calls
`setActiveGroup("editor")` instead of `setActivePanel("editor")`.

Similarly:
- TBD navigate → `setActiveGroup("discover")` + `setSubTab("discover", "tbd")`
- Related versions found → `setActiveGroup("compare")`
- Document opened → `setActiveGroup("editor")`

---

## Keyboard Shortcuts (Future)

| Shortcut | Action |
|----------|--------|
| `Ctrl+1` | Switch to Editor |
| `Ctrl+2` | Switch to Discover |
| `Ctrl+3` | Switch to Sources |
| `Ctrl+4` | Switch to Compare |
| `Ctrl+5` | Switch to Session |
| `Ctrl+Shift+P` | Open Panel Manager |

---

## Success Criteria

1. All existing panels work identically (no regression)
2. Activity rail is always visible and responsive
3. Sub-tabs switch smoothly within groups
4. Panel Manager toggles persist across page reload
5. Unconfigured connectors show setup card (not empty space)
6. Panel width resize still works
7. Auto-switch events still work (element click → editor)
8. No performance regression (lazy-load panel content)
