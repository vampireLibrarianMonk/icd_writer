# Table Editing Strategy

## The Problem

The current editing workflow for table cells is unintuitive:

1. User clicks a table area → the Editor panel shows the **entire block** as a flat text blob:
   ```
   Characteristic
   Setting
   Power
   30W (TBR-UCB-110)
   Turn-on Temperature
   -30C
   Turn-off Temperature
   -20C
   ```
2. User must find the value they want to change inside this blob, edit the raw text, click Apply
3. The system extracts the changed fragment and patches the PDF

This works technically but is terrible UX. The user sees a paragraph editor for what is visually a table. They have no spatial context. It's easy to break the structure by accidentally removing a newline or editing the wrong line.

## What We Learned

Through the v1.2.1 development, we established these hard constraints:

### The PDF Layer
- Table cells on the PDF are **individual spans** at specific (x, y) coordinates
- Table borders are **filled rectangles** (not lines) — thin rects of ~0.5pt height/width
- `page.search_for("30W")` finds the text at its exact position
- Redaction + insert at the correct (x, y) works perfectly
- Centering is achieved by computing the original text's center-x and positioning the new text there

### The IR Layer
- The Document IR stores table content as a **single text block** with newlines separating what are visually separate cells
- The block has one bbox covering the entire table data region
- There's no per-cell structure in the IR

### The Patch Layer
- Short fragments (< 80 chars, single-line) go through **inline redact+insert**
- The inline path centers new text at the original text's center-x
- Table borders are preserved by shrinking the redaction rect by 0.5-1pt
- This already works correctly for single-cell value replacement

## Strategy: Click-to-Edit Cells Directly

### UX Vision

1. User navigates to a table page (e.g., page 7)
2. The document viewer shows the PDF with **cell-level click targets** overlaid on the table
3. User clicks a specific cell (e.g., the "30W" cell)
4. A small **inline edit popup** appears at that cell's position (not the sidebar Editor panel)
5. User types "25W", presses Enter
6. The cell updates immediately — no "Apply" button, no paragraph blob

### Why This Is Better

- Spatial context: user sees the table, clicks the cell they want
- No risk of breaking structure: they only edit one value
- No need to understand the newline-separated text format
- Faster: fewer clicks, immediate feedback
- Familiar: feels like editing a spreadsheet cell

## Implementation Plan

### Phase 1: Cell Detection Backend

The backend already has `/document/page/{n}/table` which clusters spans into a grid. Extend this:

```
GET /document/page/{n}/table-cells
```

Returns a flat list of clickable cells with their bounding boxes:

```json
{
  "cells": [
    {
      "id": "cell-p07-r0-c0",
      "text": "Characteristic",
      "bbox": {"x0": 176, "y0": 256, "x1": 300, "y1": 269},
      "row": 0,
      "col": 0,
      "editable": true
    },
    {
      "id": "cell-p07-r0-c1",
      "text": "Setting",
      "bbox": {"x0": 310, "y0": 256, "x1": 440, "y1": 269},
      "row": 0,
      "col": 1,
      "editable": true
    },
    {
      "id": "cell-p07-r1-c1",
      "text": "30W (TBR-UCB-110)",
      "bbox": {"x0": 310, "y0": 270, "x1": 440, "y1": 283},
      "row": 1,
      "col": 1,
      "editable": true
    }
  ],
  "columns": 2,
  "rows": 4,
  "table_bbox": {"x0": 171, "y0": 255, "x1": 532, "y1": 313}
}
```

**Implementation**: Use the rawdict to extract spans in the table zone (detected by `table-zones` endpoint). Cluster by y (rows) and x (columns). Each cell is a span or group of spans at a unique (row, col) position.

### Phase 2: Cell Edit Backend

```
PUT /document/page/{n}/table-cell
{
  "cell_id": "cell-p07-r1-c1",
  "old_text": "30W (TBR-UCB-110)",
  "new_text": "25W"
}
```

This is essentially what we already have — the existing `PUT /document/table-cell` endpoint does `old_text → new_text` replacement. The difference:
- The cell_id provides unambiguous targeting (no searching for text that might appear elsewhere)
- The bbox from the cell detection gives us the exact redaction rect (no need for `search_for`)
- Record the action with `inline=True` and `patch_old`/`patch_new`

### Phase 3: Frontend — Cell Overlay Layer

The `DocumentView` component already renders overlay rectangles for elements. Add a **table cell overlay mode**:

1. Detect table zones on the page (from `GET /document/page/{n}/table-zones`)
2. For each table zone, fetch cell data from `GET /document/page/{n}/table-cells`
3. Render transparent click targets over each cell
4. On click: show an inline edit input (absolutely positioned at the cell's screen coordinates)
5. On Enter/blur: call the cell edit endpoint, refresh the page image

```tsx
// Inline cell editor — positioned over the clicked cell
<input
  style={{
    position: "absolute",
    left: cellScreenX,
    top: cellScreenY,
    width: cellWidth,
    height: cellHeight,
    fontSize: "11px",
    textAlign: "center",
    border: "2px solid var(--accent)",
  }}
  defaultValue={cell.text}
  onKeyDown={(e) => { if (e.key === "Enter") submitEdit(); }}
  autoFocus
/>
```

### Phase 4: Visual Feedback

After edit:
- The page image refreshes (existing `refreshTrigger` mechanism)
- The cell overlay updates with the new text
- A subtle animation (flash green) confirms the edit landed

## What We DON'T Need to Change

- **Export path**: already handles short inline edits correctly (centered at original center-x)
- **Undo/redo**: already works for table-cell edits
- **Border preservation**: redaction rect shrinking already in place
- **page_patch.py inline branch**: already routes short edits through the correct path

## Relation to Existing Paragraph Editor

The paragraph editor (sidebar) stays for:
- Paragraph text blocks (Section 4.1 workflow)
- Long-form text editing
- Blocks that aren't tables

The table cell editor is a **separate interaction mode** that activates only when the user clicks within a detected table zone. The two don't interfere — clicking a paragraph still opens the sidebar editor; clicking a table cell opens the inline editor.

## Detection Heuristic: Is This a Table?

A page region is a table if:
- The `table-zones` endpoint identifies it (grid density detection from filled rectangles)
- OR: the IR block is preceded by a caption block (text matching "Table X.Y...")
- OR: the rawdict shows 3+ spans at the same y with distinct x-clusters (columnar layout)

## Open Questions

1. **Merged cells**: Some tables have cells spanning multiple columns. How to handle the bbox?
   - Start simple: one span = one cell. Merged cells show as wider boxes.

2. **Multi-line cells**: Some cells have wrapped text (2+ lines in one cell).
   - Group spans by column-x AND proximity-y. Adjacent spans in the same column = one cell.

3. **Header row styling**: Should header cells be non-editable or styled differently?
   - Mark row 0 as `"editable": false` if it matches column header patterns.

4. **New rows/columns**: Out of scope for Phase 1. Single-cell value replacement only.

## Success Criteria

- User can click a table cell value and change it without opening the paragraph editor
- The exported PDF shows the new value centered in the correct cell position
- Table borders remain intact
- All existing 4.x tests continue to pass
- The interaction takes < 3 clicks (click cell → type → Enter)
