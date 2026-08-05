# Remaining Work — ICD Writer

Last updated: 2026-08-01

---

## 1. Flattened PDF Editing

**Status:** Not started  
**Priority:** High — blocks editing of scanned/flattened ICDs

### Problem

The current patch approach (`search_for` → redact → insert) requires text in the PDF content stream. Flattened PDFs have text rasterized into images — `page.search_for()` returns nothing.

### Approach

OCR the page → get text bounding boxes → store as Document IR → on edit, draw a white filled rectangle over the old text area (covers the rasterized image) → insert_text with new value on top.

### Implementation Steps

1. Connect existing OCR pipeline (`src/ocr/`) to the edit workflow
2. For flattened pages: OCR extracts text + positions into Document IR
3. Edit detection uses IR block positions (not `search_for`)
4. Patch method: `page.draw_rect(old_bbox, fill=white)` + `page.insert_text(new_text)`
5. Preview: same approach (patch the page image in-place)
6. Test with `icds/flat/` corpus

### Dependencies

- AWS Textract or local Tesseract for OCR
- Bounding box accuracy from OCR must be tight enough to cover old text without bleeding into adjacent content

---

## 2. Font Embedding for Rebuilt Pages

**Status:** Deferred — using base-14 fonts as workaround  
**Priority:** Medium — affects visual fidelity of overflow pages

### Problem

When overflow occurs, the next page is rebuilt using `page_rebuild.py` with TextWriter + base-14 fonts. These have slightly different metrics than the document's original embedded fonts (Times New Roman → Times-Roman, Arial → Helvetica). Line wrapping may differ by 1-2 characters.

PyMuPDF's `TextWriter` and `insert_font` do not embed font glyph data into the PDF. The font is referenced by name only. Viewers without the referenced font show nothing or substitute incorrectly.

### Approach Options

1. **Subset embedding** — Use a font subsetting library (fonttools) to embed only the used glyphs into the PDF after generation
2. **pikepdf post-processing** — Open the generated PDF with pikepdf and embed the font streams
3. **Accept base-14** — Current workaround. Base-14 fonts render in all viewers. Metrics are ~98% compatible.

### Current Workaround

All text insertion uses PDF base-14 font names (`tiro`, `tibo`, `helv`, `hebo`, `cour`). These are universally available in all PDF viewers without embedding. The trade-off is slightly different character widths on rebuilt overflow pages.

---

## 3. Table-Aware Editing

**Status:** Partially implemented  
**Priority:** Medium

### What Works

- Single-cell replacement via fragment extraction (e.g., "30W" → "25W")
- Cell value centered at original text's center-x position
- Table borders preserved (redaction rect shrunk to avoid covering cell lines)

### What Doesn't Work

- Adding/removing rows
- Multi-cell edits (changing column headers, restructuring)
- Table detection as a first-class object (currently stored as a text block in the IR)
- The editor panel labels table data blocks as "paragraph"

### Remaining Steps

1. Detect table blocks in the IR (blocks preceded by a caption, multi-line with columnar structure)
2. Parse into rows × columns grid
3. Frontend: render as editable grid (the TableEditor component exists but isn't fully connected)
4. Backend: support per-cell edit endpoint that correctly positions replacement text

---

## 4. Header/Footer Editing

**Status:** Endpoint exists, not integrated into export  
**Priority:** Low

### What Exists

- `GET /document/page/{n}/header-footer` returns individual header/footer spans
- `HeaderFooterEditor.tsx` component exists in the frontend

### Remaining

- `PUT` endpoint to edit header/footer text
- Apply header/footer changes across all pages (global edit)
- Export path needs to patch header/footer spans on each page

---

## 5. Cross-Page TOC Auto-Update

**Status:** Not started  
**Priority:** Low

### Problem

When page content changes (e.g., page extension adds a page), the TOC page numbers become stale. Currently the user must manually edit TOC entries to update page references.

### Approach

After a page split or reflow that changes page assignments:
1. Detect which sections moved to which pages
2. Auto-update the TOC IR entries with new page numbers
3. Apply the TOC patches on export

---

## 6. Multi-Document Editing Session

**Status:** Not started  
**Priority:** Low

### Problem

Currently only one document can be open at a time. Opening a new document clears the session.

### Approach

- Allow multiple documents in the session state
- Tab-based navigation between open documents
- Each document maintains its own edit history and undo stack

---

## 7. Requirement Traceability

**Status:** Extraction exists, linking does not  
**Priority:** Future

### What Exists

- `GET /document/requirements` extracts "shall" statements with page/block references
- TBD dashboard tracks unresolved items across documents

### Remaining

- Link requirements to interfaces (provider/consumer)
- Cross-document traceability matrix
- Requirement coverage analysis
- Export traceability report

---

## 8. Production Hardening

**Status:** Ongoing  
**Priority:** Medium

### Items

- [ ] Authentication / multi-user sessions
- [ ] Persistent session storage (currently in-memory, lost on restart)
- [ ] Rate limiting on Bedrock API calls
- [ ] PDF upload size limits and validation
- [ ] Error recovery for failed exports
- [ ] Automated backup of Document IR files
- [ ] CI/CD pipeline with test gates
- [ ] Docker health check improvements (check OpenSearch connectivity)
