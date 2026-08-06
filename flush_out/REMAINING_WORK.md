# Remaining Work — ICD Writer

Last updated: 2026-08-05

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

**Status:** Complete (v1.4.0) — dynamic font extraction with graceful fallback  
**Priority:** Done

### What Works

- FontCache extracts embedded fonts from source PDFs on document open
- Text insertion (table rebuild, TOC add, header/footer edit) uses extracted font when available
- Falls back to system fonts (Liberation/Windows) for non-embedded fonts
- Falls back to base-14 built-in as last resort
- Text width calculations use the actual font metrics for accurate centering
- Handles PDFs with embedded fonts AND PDFs with referenced-only fonts

### Fallback Chain

1. Extracted font from source PDF (exact match — pixel-identical)
2. System font file (Liberation Serif/Sans/Mono — metrically compatible)
3. Base-14 built-in (tiro/helv/cour — always available, slightly different metrics)

---

## 3. Table Editing — Remaining Gaps

**Status:** Panel-based CRUD works (v1.4.0)  
**Priority:** Low

### What Works (v1.4.0)

- Panel-based TableEditor with auto-detection and dropdown selector
- Add row / delete row via full zone rebuild
- Cell editing via rebuild (atomic, no positioning bugs)
- Sequential edits stable (columns derived from horizontal borders)
- Undo/redo via PDF backup/restore
- Export verified (no duplicate text)
- Span merging for multi-span cells (Temperature + degree + C)
- Caption preservation during rebuild

### What Doesn't Work

- Multi-cell edits (select a range, batch change)
- Table detection as first-class IR object (still inferred from PDF geometry)
- Row/column resizing (columns are equal-width after rebuild)
- Column width preservation from original (would need font metric matching)

---

## 4. Header/Footer Editing

**Status:** Complete (v1.4.0)  
**Priority:** Done

### What Works

- HeaderFooterEditor panel with left/center/right editable fields
- PUT /document/page/{n}/header-footer persists edits to working copy
- Alignment-aware text positioning (left/center/right)
- Undo via PDF backup/restore
- Integrated into the dropdown selector panel
- Page image refreshes after edit
- Export skips double-patching for edited pages

---

## 5. Cross-Page TOC Auto-Update

**Status:** Not started  
**Priority:** Low

### Problem

When page content changes (e.g., page extension adds a page), the TOC page numbers become stale. Currently the user must manually edit TOC entries to update page references.

### What Works (v1.4.0)

- TOC detection (section numbering + leader dots + page refs)
- Add/Edit/Delete entries via panel
- Undo for TOC operations
- Export reflects TOC changes

---

## 6. Multi-Document Editing Session

**Status:** Not started  
**Priority:** Low

### Problem

Currently only one document can be open at a time. Opening a new document clears the session.

---

## 7. Requirement Traceability

**Status:** Extraction exists, linking does not  
**Priority:** Future

### Remaining

- Link requirements to interfaces (provider/consumer)
- Cross-document traceability matrix
- Requirement coverage analysis

---

## 8. Production Hardening

**Status:** Ongoing  
**Priority:** Medium

### Done (v1.4.0)
- [x] Persistent session storage (save/load .icd-session files)
- [x] Session survives backend restart (load from file)
- [x] Working copy workflow (original PDF never mutated until explicit save)
- [x] .env / .test-env environment separation
- [x] No-cache on index.html for reliable frontend deploys

### Remaining
- [ ] Authentication / multi-user sessions
- [ ] Rate limiting on Bedrock API calls
- [ ] PDF upload size limits and validation
- [ ] Error recovery for failed exports
- [ ] CI/CD pipeline with test gates
- [ ] Docker health check improvements (check OpenSearch connectivity)
- [ ] Clean up stale .working_ and .test_ files from output/ on session end

---

## 9. ICD Briefing Consolidation

**Status:** Design complete, implementation not started  
**Priority:** High — core value proposition of the tool  
**Design doc:** `flush_out/ICD_BRIEFING_CONSOLIDATION.md`

### Summary

Take N ICD documents and produce a single consolidated briefing:
document summaries, TBD aggregation, cross-references, conflict detection,
maturity scoring. Four phases from two-doc MVP to N-doc scaling with
interface graph visualization.

### Test Corpus (downloaded)

See `flush_out/TEST_DOCUMENT_CORPUS.md` for the 5-tier test plan.
All documents are downloaded to `icds/digital/`:

- **Tier 1 (ready):** IDSS IDD Rev E + Rev F
- **Tier 2 (ready):** IDSS IDD Rev D + Rev E + Rev F (consecutive, no gaps)
- **Tier 3 (ready):** IDSS IDD Rev A + D + E + F (with acknowledged B/C gap)
- **Tier 4 (ready):** IDSS IDD Rev A + D + E + F + G (full public chain)
- **Tier 5 (ready):** HSI_SYS_015G + HSI_SYS_001H + HSI_SYS_001I (cross-document)

### Next Step

Build Phase 1: two-document briefing against Tier 1 (Rev E + Rev F).
Zero AWS cost — all local processing on Document IR + TBD extraction.


---

## 10. AI Model Selection for Search

**Status:** Complete (v1.4.0)  
**Priority:** Done

### What Works

- GET /search/models returns all available models with descriptions and cost
- Search endpoint accepts `model` parameter to select which index to query
- Frontend dropdown in the Search panel shows all models with plain descriptions
- Explanation text tells users what model selection means
- Default auto-selects the recommended model (titan-v2-sliding)
- Choice persists for the session

### What Exists

- 4 embedding models configured: Titan V2, Titan V1, Cohere English V3, Cohere Multilingual V3
- 5 chunking strategies: fixed words, paragraph, section, sliding window, semantic
- Full evaluation harness (`src/search/eval_harness.py`) with ground truth queries
- ModelRegistry (`src/search/model_registry.py`) probes Bedrock for available models
- Benchmark results stored per run, best config auto-selected
- `_get_best_config()` picks the top performer from last evaluation
- Documents are indexed with ALL models simultaneously (separate indexes per model)

### How It Works (what the user needs to understand)

When a document is uploaded, its text gets split into chunks and each chunk
is converted into a mathematical fingerprint (a vector) by an AI model. This
happens once per model, creating separate search indexes.

When you search, your question is converted into the same kind of fingerprint
using the same model, then matched against the index built by that model.

Different models interpret language differently:
- One model might be better at matching technical jargon to plain questions
- Another might be cheaper but slightly less accurate
- A third might handle synonyms better

The user is choosing which index to search against. All indexes exist already.
The choice affects search quality and cost, not speed.

### What's Missing

- User cannot see which model is currently active
- User cannot switch between models from the UI
- No explanation shown of what the choice means
- No cost or quality comparison visible to the user

### Implementation

1. Add a "Search Model" dropdown to the Search panel with a brief explanation:
   "Choose which AI model interprets your search. Documents are indexed with
   all models. Different models may find different relevant passages."

2. Show each option with a plain description:
   ```
   Titan V2 (Recommended)     — Best balance of quality and cost
   Cohere English V3           — Slightly better at synonyms, 4x cost
   Titan V1                    — Cheapest, slightly lower accuracy
   Cohere Multilingual V3      — Best if searching non-English content
   ```

3. Show the benchmark score next to each (from last eval run):
   ```
   Titan V2          ████████░░ 87% match quality    $0.0001/search
   Cohere English    █████████░ 91% match quality    $0.0004/search
   ```

4. Default to "Recommended" (auto-selects best from eval harness)

5. Store preference in browser localStorage so it persists between sessions

6. Pass selected model config to the search API via query parameter

### User-Facing Copy (for the UI tooltip/help)

"Each search model converts your question into a mathematical pattern and
finds document passages with similar patterns. We index your documents with
all available models when they are uploaded. Choosing a different model here
searches a different index of the same documents. The recommended model
scored highest on our quality tests against real ICD questions."

### Effort

Small (half day). The backend already supports model selection via config.
Just need a UI dropdown, a brief explanation, and a query parameter.
