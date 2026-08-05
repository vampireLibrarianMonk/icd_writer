# Page Rebuild — Design for Complete Solution

## Current State (as of commit fcd4964)

The application has two rendering paths:
1. **Unedited pages**: served directly from source PDF (pixel-perfect, fast)
2. **Edited pages**: rebuilt from rawdict extraction (`src/rendering/page_rebuild.py`)

The rebuild approach is architecturally correct but the implementation has critical gaps.

## What Works

- **4.2 (TBR replacement)**: Simple text substitution within a paragraph block. The block text is replaced and the paragraph reflows correctly.
- **4.3 (Table cell edit)**: The block containing table data is identified and replaced. Table borders (from drawings) are preserved.
- Basic structure: drawings copied, images copied, unedited text spans written at exact positions.

## What Doesn't Work (Section 4.4 — Page Extension)

### Problem 1: Block Granularity Mismatch

The Document IR stores blocks at the **paragraph** level (e.g., "4. Electrical Interface\nThe IDPU will be..."). When the user edits this block, the system replaces the ENTIRE block content.

But in the PDF rawdict, this content may be a **single block** containing both the heading AND the paragraph. When we replace the entire block, the heading disappears.

**Root cause**: The IR's `text_verbatim` for block-p07-b13 is:
```
4. Electrical Interface
The IDPU will be the single-point electrical interface between the spacecraft and the HESSI
instruments.  Details of the operation, power consumption, harness, and connector details are in
the IDPU ICD, reference 2.
```

The user pastes new text to REPLACE this block. The heading "4. Electrical Interface" was part of the block's `text_verbatim`, so it gets replaced too.

**Fix needed**: The edit system should either:
- Allow the user to edit ONLY the paragraph portion (not the heading)
- Or: when the rawdict block contains a heading (first line in Arial/Bold font), preserve it and only replace the paragraph lines after it

### Problem 2: Font Fidelity in Rebuilt Spans

The `_write_block_verbatim` function uses `_map_font()` which maps to PyMuPDF built-in fonts ("tiro", "helv", etc.). These have DIFFERENT metrics than the document's embedded fonts:

| Document Font | Built-in Substitute | Issue |
|---|---|---|
| TimesNewRoman (embedded TrueType) | "tiro" (Type1 Times-Roman) | Different character widths, different rendering |
| Arial,Bold | "hebo" | Close but not identical |
| Symbol | "symb" | Works |

**Root cause**: PyMuPDF's `insert_text` with built-in font names uses PostScript Type1 fonts. The document uses TrueType fonts with different metrics.

**Fix needed**: Use `fitz.Font(fontfile=...)` with system fonts (Liberation Serif/Sans/Mono) which are metrically identical to the document's fonts. The `_find_system_font()` function in `page_patch.py` already finds these paths. The rebuild should use `TextWriter` + system `fitz.Font` objects for ALL text insertion (not just edited blocks).

The font data for key fonts on the Docker system:
- `/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf` → TimesNewRoman (ascender=0.8911)
- `/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf` → TimesNewRoman,Bold
- `/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf` → Arial
- `/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf` → Arial,Bold

On Windows:
- `C:/Windows/Fonts/times.ttf` → TimesNewRoman (ascender=0.8911)
- `C:/Windows/Fonts/timesbd.ttf` → TimesNewRoman,Bold
- `C:/Windows/Fonts/arial.ttf` → Arial
- `C:/Windows/Fonts/arialbd.ttf` → Arial,Bold

### Problem 3: Overflow Page is Disconnected

When text overflows page 7's footer boundary, the overflow lines go on a NEW page 8. But:
- The overflow page has no header/footer (it's a bare blank page)
- Section 5 content (original page 8) is pushed to page 9 unnecessarily
- The overflow (5 lines) could easily fit on the same page as Section 5

**Fix needed**: Don't create a separate overflow page. Instead, PREPEND the overflow lines to the top of the original page 8 when rebuilding it. If the next page has room (original page 8 content doesn't fill it), merge the overflow with it.

## Correct Architecture

### The rawdict IS the IR

Every PDF page has a complete rawdict that contains:
- **blocks**: groups of lines
  - **lines**: groups of spans
    - **spans**: text with font, size, color, origin, bbox, character positions

This is already extracted perfectly by `page.get_text("rawdict")`. It has everything needed for 1:1 reconstruction.

### The Rebuild Pipeline

For an edited page:

```
1. Extract rawdict from source page
2. For each block in rawdict:
   a. If block matches the edited IR block (by text overlap):
      - Write the heading lines verbatim (preserve section numbers)
      - Word-wrap the new paragraph text using the block's font/size/width
      - Insert lines at correct positions with original line spacing
      - Track overflow lines if text exceeds page boundary
   b. If block does NOT match:
      - Write ALL spans verbatim at their exact positions
3. For overflow:
   - Prepend overflow lines to the NEXT page's rebuild
   - Or: rebuild the next page too, starting with overflow content
```

### Key Design Decisions

1. **Span-level preservation for unedited content**: Use `TextWriter` + system font objects (not `insert_text` with built-in names). This gives exact character positioning because the system fonts have identical metrics.

2. **Block-level replacement for edits**: When a block is edited, the ENTIRE block is rewritten. But preserve heading lines (lines whose font is Bold/Arial) at the top of the block.

3. **Overflow merging**: Don't create separate overflow pages. Rebuild the following page with overflow content prepended at the top, pushing the original content down.

4. **Color preservation**: Every span's color is extracted as an integer from rawdict (`span["color"]`). Convert to RGB tuple and pass to the text insertion.

## Files to Modify

| File | Change |
|---|---|
| `src/rendering/page_rebuild.py` | Complete rewrite of text rendering using system fonts + TextWriter |
| `src/api/app.py` (export-download) | Remove overflow page creation; instead rebuild the next page with overflow prepended |
| `src/api/app.py` (page image) | Same rebuild approach for preview |

## Test Verification (all must pass)

```bash
# 4.1: paragraph edit
# - "all reasonable effort" appears in the text
# - line spacing matches original (14.16pt)
# - no overflow past margin

# 4.2: TBR replacement  
# - "0.5" replaces "(TBR-UCB-102)"
# - surrounding text unchanged
# - font/color match original

# 4.3: table cell edit
# - "25W" centered in column
# - table borders intact
# - color matches (magenta)

# 4.4: page extension
# - paste text appears on page 7 below the last table
# - "4. Electrical Interface" heading PRESERVED at top of the paste area
# - text flows naturally with correct font
# - overflow continues on page 8 (merged with Section 5 content)
# - total pages: 8 (no extra page needed — overflow fits above Section 5)
```

## Reference: Page 7 rawdict Block Structure

```
Block 0 (y=36):  "HESSI Spacecraft to Spectrometer ICD\nHSI_SYS_015G.doc" [HEADER]
Block 1 (y=38):  "Dave Pankow\nPage 4\n1999-Mar-12" [FOOTER]
Block 2 (y=72):  "the Cryostat.  Cooler operation..." [3 lines, paragraph]
Block 3 (y=127): "3.2.1. Spectrometer Heaters\nThe Spectrometer includes..." [HEADING + paragraph]
Block 4 (y=241): "Table 3.2.1-1  Spectrometer Thermostat..." [caption]
Block 5 (y=255): "Characteristic\nSetting\nPower\n30W..." [table data]
Block 6 (y=342): "A Coldplate heater is also provided..." [paragraph]
Block 7 (y=425): "3.3. Spectrometer Temperature Requirements\nThe Non-Op..." [HEADING + paragraph]
Block 8 (y=483): "Table 3.3-1  Thermal Limits" [caption]
Blocks 9-12:     [thermal limits table data — overlapping fragments]
Block 13 (y=597): "4. Electrical Interface\nThe IDPU will be..." [HEADING + paragraph — THIS IS EDITED]
```

The key insight: Block 13 has the heading "4. Electrical Interface" on its FIRST LINE (in Arial,Bold font) followed by paragraph text (in TimesNewRoman). When the user edits this block, only the PARAGRAPH should change — the heading should be preserved.

## Reference: Font Extraction from rawdict Spans

Each span in rawdict provides:
```python
{
    "font": "TimesNewRoman",  # or "Arial,Bold", "Symbol", etc.
    "size": 12.0,
    "flags": 4,  # bit flags: 1<<4 = bold, 1<<1 = italic
    "color": 16711935,  # 0xRRGGBB integer
    "origin": (319.44, 281.28),  # baseline insertion point
    "bbox": (319.44, 270.59, 427.60, 283.87),  # visual bounding box
    "chars": [{"c": "3", "origin": (319.44, 281.28)}, ...]  # per-character positions
}
```

For 1:1 reconstruction, write each span at its `origin` point using a `fitz.Font` object loaded from the matching system font file.
