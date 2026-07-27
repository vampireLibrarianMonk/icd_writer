# Known Issues & Next Steps

## UI Editing Surface (HSI_SYS_015G.pdf)

### Working
- ✅ Headers (left/right) — individually clickable and editable
- ✅ Footers (left/center/right) — individually clickable and editable
- ✅ TOC (page 3) — clean section/page editor, no dots
- ✅ Paragraphs — merged into logical blocks, editable
- ✅ Headings — separate from paragraphs, properly labeled
- ✅ Section numbers (N.N.) — detected and standalone
- ✅ Table editor (page 2) — grid view in right panel
- ✅ Back-to-Table / Back-to-TOC navigation
- ✅ Dark/light mode
- ✅ Undo/redo with button state

### Known Issues

1. **Page 7 paragraph at y=144 not selectable**
   - "The Spectrometer includes two heater circuits..." is body text
   - Drawing-based table zone starts at y=143, hiding it
   - Root cause: table grid lines start at the same y as the paragraph above
   - Fix: use grid density (count of thin rects in a band) rather than just y-range

2. **Page 7 shows two tables as one merged grid**
   - Table 1 (thermostat characteristics): y=253-398
   - Table 2 (thermal limits): y=483-570
   - The table endpoint merges them into one 15×4 grid
   - Fix: detect gaps in row clustering to split into separate tables

3. **Table zone boundaries are imprecise**
   - Drawing-based zones include area above/below actual grid content
   - Some paragraphs between headings and tables get caught in zones
   - Fix: require minimum density of grid lines within a y-band to qualify as table

### Proposed Fix: Grid Density Table Detection

Instead of using all drawing y-positions, count the number of thin filled rectangles
per horizontal band. A table band has many small rects (cell borders). A paragraph
with a single horizontal rule does not.

```python
# For each 20pt band, count thin rectangles
for y_band in range(0, page_height, 20):
    rects_in_band = [d for d in drawings 
                     if y_band <= d.rect.y0 <= y_band + 20
                     and (d.rect.width < 2 or d.rect.height < 2)]
    if len(rects_in_band) >= 5:  # table-like density
        table_bands.add(y_band)
```

This would correctly identify only the actual grid content areas.
