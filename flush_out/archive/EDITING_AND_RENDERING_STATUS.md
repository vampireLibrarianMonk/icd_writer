# Editing & Rendering — Current State and Next Steps

## What Works

### Page 5 (Paragraph Edit)
- Click text block → edit in Editor tab → Apply → page image re-renders with change ✓
- Export PDF contains the edit ✓
- Overlay text updates immediately ✓

### Export PDF
- Edited pages render entirely from Document IR (no bbox patching against source) ✓
- Unedited pages copy directly from source PDF (pixel-perfect, fast) ✓
- New pages (from page split) render from IR ✓

### Elements Endpoint
- Always returns from Document IR (blocks have proper IDs) ✓
- Table zone overlays removed (IR blocks are clickable directly) ✓
- Block edits use PUT /document/block/{id} path every time ✓

---

## What's Partially Working

### Page 7 (Table Edit)
- **Edit persists**: block-p07-b05 contains "Characteristic\nSetting\nPower\n25W\n..." after edit ✓
- **Export works**: exported PDF has the correct 25W value ✓
- **Preview re-renders**: page image updates after edit ✓
- **Table lines**: Added grid lines (borders, row dividers, column divider) for blocks preceded by a caption
- **Overlap dedup**: blocks whose center falls inside an already-rendered region are skipped ✓

### Known Visual Issues on Re-rendered Pages
- Re-rendered pages show TEXT ONLY (no images, no vector graphics from original PDF)
- Table formatting is approximate (grid lines at midpoint, evenly spaced rows)
- Font substitution may differ from original (uses Helvetica fallback)
- The second table on page 7 (Thermal Limits) has overlapping IR blocks (b09, b10, b11, b12 at y≈498-570) — the overlap dedup keeps only the largest

---

## Architecture of the Rendering Pipeline

```
User clicks Apply
    │
    ▼
PUT /document/block/{id}  →  updates state["document_ir"] in memory
    │
    ▼
reflow_and_split()  →  adjusts bboxes, may create new page
    │
    ▼
Frontend increments refreshTrigger (Date.now())
    │
    ├─→ GET /document/page/{N}/elements  →  returns IR blocks (always)
    │
    └─→ GET /document/page/{N}/image?v={timestamp}
              │
              ├─ Page NOT edited: fitz.open(source).get_pixmap() → original PDF render
              │
              └─ Page IS edited:
                    _ir_blocks_to_elements(page_info)
                        → deduplicate overlapping blocks
                        → TextElement for each block
                    _add_table_lines(page_info, elements)
                        → detect blocks preceded by caption
                        → add LineElement (borders, rows, column divider)
                    render_page_to_html(width, height, elements)
                    HTML(string=html).write_pdf()
                    fitz.open(pdf_bytes).get_pixmap(dpi=150) → PNG
```

---

## Key Files

| File | Role |
|------|------|
| `src/api/app.py` (line ~787) | Page image endpoint — detects edit, re-renders from IR |
| `src/api/app.py` (line ~1038) | Elements endpoint — always returns from IR |
| `src/api/app.py` (line ~1515) | Block edit endpoint — modifies IR, calls reflow_and_split |
| `src/rendering/ir_renderer.py` | `_ir_blocks_to_elements()` — dedup + table lines |
| `src/rendering/ir_renderer.py` | `_format_block_text()` — currently plain passthrough |
| `src/rendering/ir_renderer.py` | `_add_table_lines()` — draws grid for caption-preceded blocks |
| `src/rendering/ir_renderer.py` | `render_ir_to_pdf()` — export: IR-only for edited pages |
| `src/rendering/renderer.py` | `render_page_to_html()` — produces HTML with absolute positioning |
| `src/rendering/renderer.py` (line ~180) | `_render_text()` — renders TextElement as positioned spans |
| `src/reflow.py` | `reflow_and_split()` — adjusts blocks after edit, creates pages |
| `frontend/src/components/DocumentView.tsx` | Image display + overlay click handling |
| `frontend/src/components/UnifiedEditor.tsx` | Edit text + Apply button |

---

## Next Steps to Improve Table Rendering

### Problem
The IR stores table content as a single text block with newlines:
```
Characteristic\nSetting\nPower\n25W\nTurn-on Temperature\n-30C\nTurn-off Temperature\n-20C
```

This gets rendered as a plain text span (white-space:pre) with grid lines overlaid. The text isn't aligned to the grid because it's a single positioned element.

### Options

**Option A: Split table text into per-cell TextElements**
- Parse the newline-separated text into rows × columns
- Create a separate TextElement for each cell, positioned within the grid
- Pros: text aligns to grid, looks like a table
- Cons: need to determine column widths and row heights

**Option B: Render as HTML `<table>` directly in the page HTML**
- Instead of TextElement → span, emit `<table>` with borders in the HTML
- Requires modifying `render_page_to_html` to handle a new element type (TableElement)
- Pros: proper table layout with CSS borders
- Cons: more complex, new element type needed

**Option C: Hybrid — keep original PDF render for unedited regions**
- Only re-render the EDITED block, overlay it on the original page image
- Compose: original PNG + edited block rendered as overlay
- Pros: preserves original formatting for everything except the edit
- Cons: compositing logic, z-ordering issues

### Recommended: Option A (per-cell TextElements)
- Detect table blocks (preceded by caption, short newline-separated lines)
- Parse into rows: every 2 lines = 1 row (key, value) OR detect column count from header
- Create TextElement for each cell positioned at (col_x, row_y)
- Grid lines already exist from `_add_table_lines()`

---

## Blocks on Page 7 for Reference

```
block-p07-b00  heading    y=37-50     HESSI Spacecraft to Spectrometer ICD
block-p07-b01  paragraph  y=742-756   Dave Pankow | Page 4 | 1999-Mar-12  (footer)
block-p07-b02  paragraph  y=73-114    the Cryostat. Cooler operation...
block-p07-b03  heading    y=127-214   3.2.1. Spectrometer Heaters...
block-p07-b04  caption    y=241-255   Table 3.2.1-1 Spectrometer Thermostat Characteristics
block-p07-b05  paragraph  y=256-313   Characteristic|Setting|Power|25W|Turn-on|-30C|Turn-off|-20C
block-p07-b06  heading    y=343-399   A Coldplate heater is also provided...
block-p07-b07  heading    y=426-470   3.3. Spectrometer Temperature Requirements...
block-p07-b08  caption    y=483-497   Table 3.3-1 Thermal Limits
block-p07-b09  paragraph  y=512-525   Range                    (OVERLAPS with b12)
block-p07-b10  paragraph  y=498-511   Bus Side Interface       (OVERLAPS with b12)
block-p07-b11  paragraph  y=511-526   Temperature, °C          (OVERLAPS with b12)
block-p07-b12  paragraph  y=498-570   Spectrometer|Temperature|Non-Op Limits|-60–+61|...
block-p07-b13  heading    y=597-659   4. Electrical Interface...
```

The first table (b05) is clean — single block, 4 rows × 2 columns.
The second table (b12) has fragments (b09, b10, b11) overlapping — dedup keeps b12 only.

---

## Frontend State After This Session

- `VITE_API_BASE` = empty in container build (relative URLs through nginx)
- All components use `${API_BASE}` template literals for fetch calls
- `refreshTrigger` uses `Date.now()` for guaranteed unique values
- `<img key={...}>` forces DOM re-mount on refresh
- No more table zone overlays (removed)
- No more table-zones API call from DocumentView
