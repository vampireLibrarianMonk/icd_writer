# Table CRUD Operations — Design

## Context

v1.3.0 delivers single-cell inline editing for tables. The user clicks a cell,
types a new value, and it's patched onto the PDF with correct centering and
border preservation. This document designs the next level: adding and removing
rows.

## Constraints

PDF tables are not structured data. They are:
- **Text spans** at specific (x, y) coordinates
- **Filled rectangles** (0.5pt tall/wide) forming grid borders
- **No logical row/column model** in the file format

Any row operation must manipulate both text AND drawing objects.

## Architecture Decisions

### What We Already Have

- `GET /document/page/{n}/table-cells` — returns cells clustered by row/col with bboxes
- `GET /document/page/{n}/table-zones` — returns table bounding boxes (y_min, y_max)
- `PUT /document/table-cell` — patches a single cell value (inline mode)
- Table border detection: thin filled rects identified in rawdict drawings
- Page content shift mechanism: `page_rebuild.py` can write content at offset positions

### Core Principle

**Patch what you can, rebuild what you must.** For row operations:
- The table zone gets rebuilt (new rows/borders drawn from scratch)
- Content ABOVE the table stays pixel-perfect (untouched)
- Content BELOW the table gets shifted down/up by the row height delta

---

## Phase 1: Append Row (add at bottom)

### Simplest case — no content shift needed if table is the last body element.

**Backend endpoint:**
```
POST /document/page/{n}/table-row
{
  "zone_y_min": 255,
  "zone_y_max": 313,
  "position": "bottom",
  "cells": ["New Item", "Value"]
}
```

**Implementation:**
1. Get the table zone's last row y-position and row height
2. Compute new row y = last_row_y + row_height
3. Insert text spans for each cell at the correct column x-positions
4. Draw horizontal border line (filled rect) below the new row
5. Draw vertical border lines for each column boundary
6. If new row extends past content_bottom → handle overflow

**Drawing borders:**
```python
# Horizontal line below new row
page.draw_rect(fitz.Rect(table_x0, new_row_bottom, table_x1, new_row_bottom + 0.48), fill=(0,0,0))
# Vertical lines at each column boundary
for col_x in column_boundaries:
    page.draw_rect(fitz.Rect(col_x, new_row_y, col_x + 0.48, new_row_bottom), fill=(0,0,0))
```

**Content shift:**
- Calculate height_delta = row_height (e.g., 14.16pt)
- All content below table_y_max must move down by height_delta
- Use the rawdict rebuild approach for the portion below the table
- OR: redact the below-table content, rewrite it shifted down

**Session recording:**
```python
session.record(ActionType.BLOCK_EDITED, page=page_num, block_id=table_block_id,
    data={"operation": "add_row", "position": "bottom", "cells": [...],
          "old_text": current_block_text, "new_text": updated_block_text})
```

---

## Phase 2: Delete Row

**Backend endpoint:**
```
DELETE /document/page/{n}/table-row
{
  "zone_y_min": 255,
  "zone_y_max": 313,
  "row_index": 3
}
```

**Implementation:**
1. Identify the row's y-range (row_y_min to row_y_max)
2. Redact all text spans in that row's y-range
3. Redact the horizontal border lines at the row boundaries
4. Shift all content below the deleted row UP by row_height
5. Update the IR block text (remove the row's cell values)

**Undo:** Store the deleted row's cell values + position. On undo, re-insert.

---

## Phase 3: Insert Row at Position

**Backend endpoint:**
```
POST /document/page/{n}/table-row
{
  "zone_y_min": 255,
  "zone_y_max": 313,
  "position": "after",
  "after_row": 1,
  "cells": ["New Item", "Value"]
}
```

**Implementation:**
1. Identify the insertion y-position (below target row)
2. Shift all rows BELOW the insertion point down by row_height
3. Shift all content below the TABLE down by row_height
4. Insert new text spans + borders at the insertion position
5. Handle page overflow if the shift pushes content past the bottom margin

**This is the hardest operation** because it requires a partial page rebuild
for everything below the insertion point.

---

## Phase 4: Frontend UI

### Row Operations Toolbar

When a table zone is active (cells are showing), display a small toolbar:
```
[ + Add Row ] [ - Delete Row ] 
```

**Add Row:**
1. Click "+ Add Row" → a new empty row appears at the bottom of the table
2. Each cell in the new row is immediately editable (inline inputs)
3. Press Enter on the last cell → row is committed

**Delete Row:**
1. Click a cell to select a row (entire row highlights)
2. Click "- Delete Row" → confirmation → row removed
3. Content below shifts up

### Visual Feedback
- New row appears with a green border (uncommitted)
- After commit: page image refreshes showing the new row
- Deleted row flashes red before disappearing

---

## Content Shift Mechanism

The key technical challenge. Options:

### Option A: Partial Rebuild Below Table
- Extract rawdict for everything below table_y_max
- Rewrite it on a blank area shifted by height_delta
- Requires the same TextWriter + base-14 font approach as overflow pages
- Pro: works for any content type (paragraphs, other tables, images)
- Con: font fidelity limitations (base-14 metrics differ slightly)

### Option B: PDF Content Stream Transform
- Use pikepdf to modify the content stream's transformation matrix
- Add a `cm` (concat matrix) command that shifts the coordinate system
- Pro: preserves all original rendering exactly
- Con: complex, fragile, may affect page-level elements unexpectedly

### Option C: Full Page Rebuild for Affected Pages
- When a row operation happens, rebuild the entire page from rawdict
- Pro: handles all edge cases
- Con: all the fidelity issues we already solved (and moved away from)

**Recommendation: Option A** — same approach as overflow page handling.
The rebuild only applies to content below the table (not the table itself
or anything above it). The table zone is drawn fresh (text + borders).

---

## Data Flow

```
User clicks "+ Add Row"
  → Frontend sends POST /document/page/7/table-row {position: "bottom", cells: [...]}
  → Backend:
    1. Gets table zone geometry (columns, row heights, borders)
    2. Computes new row position
    3. Modifies source page:
       a. Shift below-table content down (if needed)
       b. Draw new cell text at correct positions
       c. Draw new border rectangles
    4. Updates Document IR (appends row text to block)
    5. Records session action
  → Returns {status: "added", new_row_index: 4}
  → Frontend increments refreshTrigger → page image reloads
```

---

## Testing Strategy

```python
class TestTableRowCRUD:
    def test_append_row_adds_cells(self, client):
        # Add a row to the thermostat table on page 7
        # Verify exported PDF has the new row text at correct position
        
    def test_append_row_preserves_borders(self, client):
        # After adding a row, table still has grid lines
        
    def test_delete_row_removes_text(self, client):
        # Delete last row, verify text is gone from export
        
    def test_delete_row_shifts_content_up(self, client):
        # Content below table moves up by one row height
        
    def test_insert_row_middle_shifts_below(self, client):
        # Insert between rows 1 and 2, verify rows 2+ shifted down
        
    def test_row_operation_undo(self, client):
        # Add row → undo → row gone, original state restored
```

---

## Open Questions

1. **How to determine column widths for a new row?** Use the existing column
   x-positions from the detected cells. New cell text gets centered at the
   same column centers.

2. **What if the new row has more/fewer cells than columns?** Pad with empty
   cells or truncate. The frontend should enforce the correct column count.

3. **Row height:** Use the average row height from existing rows (typically
   14-15pt for 12pt text with padding).

4. **Multiple tables on one page:** The zone_y_min/y_max parameters scope
   the operation to a specific table.

5. **Undo for content shift:** Must reverse the shift exactly. Store the
   shift amount and direction in the session action data.

---

## Success Criteria

- User can add a row to a table and see it in the preview immediately
- Exported PDF shows the new row with proper borders and alignment
- Content below the table is not corrupted
- Undo removes the added row cleanly
- All existing 4.x User Guide tests continue to pass
