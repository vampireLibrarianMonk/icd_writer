# Remaining Work — ICD Writer

Last updated: 2026-08-21

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

## 2. Table Editing — Remaining Gaps

**Status:** Panel-based CRUD works (v1.4.0)
**Priority:** Low

### What Doesn't Work

- Multi-cell edits (select a range, batch change)
- Table detection as first-class IR object (still inferred from PDF geometry)
- Row/column resizing (columns are equal-width after rebuild)
- Column width preservation from original (would need font metric matching)

---

## 3. Cross-Page TOC Auto-Update

**Status:** Not started
**Priority:** Low

### Problem

When page content changes (e.g., page extension adds a page), the TOC page numbers become stale. Currently the user must manually edit TOC entries to update page references.

---

## 4. Multi-Document Editing Session

**Status:** Not started
**Priority:** Low

### Problem

Currently only one document can be open at a time. Opening a new document clears the session.

---

## 5. Requirement Traceability

**Status:** Extraction exists, linking does not
**Priority:** Future

### Remaining

- Link requirements to interfaces (provider/consumer)
- Cross-document traceability matrix
- Requirement coverage analysis

---

## 6. Production Hardening

**Status:** Ongoing
**Priority:** Medium

### Remaining
- [ ] Authentication / multi-user sessions
- [ ] Rate limiting on Bedrock API calls
- [ ] PDF upload size limits and validation
- [ ] Error recovery for failed exports
- [ ] CI/CD pipeline with test gates
- [ ] Docker health check improvements (check OpenSearch connectivity)
- [ ] Clean up stale .working_ and .test_ files from output/ on session end

---

## 7. ICD Briefing Consolidation — Phase 2-4

**Status:** Phase 1 complete (v1.5.0), Phase 2+ not started
**Priority:** Medium
**Design doc:** `flush_out/archive/ICD_BRIEFING_CONSOLIDATION.md`

### Remaining Phases

- Phase 2: Multi-revision walkthrough (D→E→F sequential)
- Phase 3: Semantic conflict detection (Bedrock embeddings + Claude)
- Phase 4: N-document scaling + interface topology graph
- PDF briefing export (Jinja2 + WeasyPrint)

---

## 8. Export Pipeline — Edit Embedding

**Status:** Known bug (discovered during v1.7.0 regression testing)
**Priority:** High

### Problem

`POST /document/export` produces a reconstructed PDF but does **not** embed
in-memory Document IR edits into the PDF text layer. The exported PDF contains
the original text, not the edited text. This is validated by:
- `test_edit_rerender_cycle.py::test_full_cycle_page5` (FAILS)
- `test_ug_pdf_output.py` (8 tests xfailed)

### Expected Behavior

After editing a block via `PUT /document/block/{id}`, the subsequent export
should produce a PDF where `page.get_text()` returns the new text.

### Likely Root Cause

The export pipeline reconstructs pages from the source PDF rather than
applying the page-patch (redact + re-insert) that the image preview uses.

---

## Completed Items (Archived)

The following have been completed and moved to `flush_out/archive/`:

- **Font Embedding** — v1.4.0: Dynamic extraction with graceful fallback chain
- **Header/Footer Editing** — v1.4.0: Panel with left/center/right fields
- **AI Model Selection** — v1.4.0: Dropdown, per-session preference, benchmark display
- **Table CRUD Operations** — v1.4.0: Panel-based add/delete row via rebuild
- **ICD Briefing Phase 1** — v1.5.0: Revision Compare panel, section diff, value extraction
- **Test Document Corpus** — Assembled: HSI H/I, IDSS E/F, TSAFE, LVC all in repo
- **Session Management** — v1.4.0: Save/load .icd-session files, persistent state
- **Editing & Rendering** — v1.4.0: Full edit→preview→export cycle
- **Page Rebuild Design** — v1.4.0: Clip-and-paste content shift
- **Table Editing Strategy** — v1.4.0: Panel-based rebuild approach
