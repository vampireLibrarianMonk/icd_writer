# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.6.0] — 2026-08-07

### Added
- **Document Manager panel** (`📁 Docs` tab): file-explorer style with multi-select
  checkboxes, bulk delete, upload (multi-file), sort by name/size, filter, status bar
  showing selection count and total size. Double-click to open.
- **Loading indicator**: bottom-left status bar shows spinning ring + progress messages
  ("Opening...", "Extracting text...", "Rendering page 1 of N...") during document open.
- **Undo/Redo buttons** in the Session panel (below session info, above timeline).
- **Element type regression tests** (`tests/unit/test_element_classification.py`): 17 tests
  covering TOC entries, giant blocks, merged content, captions, footers.
- **Document audit scripts** for verifying element classification across all test corpus.

### Changed
- **Element type detection pipeline revamped** (`src/extraction/text_extractor.py`):
  - New `_split_block_by_style()` splits blocks on font-size transitions and heading patterns
  - TOC entries (4+ consecutive dots) classified as `list_item` not `heading`
  - Height guard: blocks >80px classified as `paragraph` (prevents merged heading+body misclass)
  - Audit results: 183 issues → 18 (90% reduction across 7 documents)
- **Table row shift uses clip-and-paste** instead of lossy redact+re-insert:
  - `show_pdf_page()` moves content below the table as an exact block
  - Preserves fonts, drawings, images perfectly — no more overlaps or missing text
- **TOC detection tightened**: `/document/page/{n}/toc` now requires 3+ entries with actual
  page references (from leader dots), not just any text spans. Prevents false TOC editor
  on normal content pages.
- **Overlay borders removed**: element overlays use `border: none` by default (were
  `1px solid transparent` which rendered as faint artifacts on some displays).

### Fixed
- **Table row height_delta calculation**: uses `max(original_table_y1, req.y_max)` as
  reference instead of border-detected bottom. Caption rows no longer confuse the math.
- **Text overlap after table shift**: same-line spans (split across PDF content streams)
  no longer overlap when re-inserted — resolved by switching to clip-and-paste approach.
- **TOC misclassification on content pages**: pages with numbered sections + body text
  no longer trigger the TOC editor dropdown.
- **Editor dropdown shows all page elements**: heading/paragraph/caption blocks listed
  by type and count, not just special sections (header/footer/table/TOC).
- **Header/footer zone elements excluded** from body dropdown (prevents unclickable
  items like "Heading 1" pointing to header-zone text).

---

## [1.5.0] — 2026-08-07

### Added
- **Revision Compare panel** (`📊 Compare` tab): replaces old Diff tab with full
  section-by-section analysis: value extraction, TBD deltas, text snippets, boilerplate
  filtering, cross-references, value conflicts, maturity scoring.
- **Standard/Advanced analysis modes**: Standard is free (structural only), Advanced
  reveals per-section AI summarize buttons with cost display.
- **Document highlight overlay**: clicking a page link in Compare opens the document,
  navigates to the page, and highlights the section with an orange overlay.
- **Boilerplate detection**: repeated header/footer stamps extracted as "Global Changes"
  and excluded from per-section diffs.
- **Section extraction overhaul** (`src/version_diff.py`): numbered headings require
  alphabetic title text, bullets/measurements/dates excluded, font threshold raised.
- **Filename revision extraction**: ICD naming conventions (HSI_SYS_001H → Rev H)
  recognized for family grouping.
- **75 tests** covering briefing, version diff, element classification, and integration.

### Changed
- **Old Diff tab removed** — functionality merged into the Compare panel with OCR
  handling, AI summarize, and progressive disclosure.
- **Classification accuracy**: spec-value pattern case-sensitive, no bare A/g/K units,
  `_has_requirement_change` only fires on shall/must count changes.

---

## [1.3.0] — 2026-08-01

### Added
- **Table inline cell editor**: click directly on a table cell in the document viewer
  to edit it in-place (no sidebar needed). Green dashed overlays show editable cells.
- **Session management**: top-level Session menu with Save, Save As, Load, New Session.
  Sessions persist to `.icd-session` files and can be restored across restarts.
- **Session tab**: right panel tab showing a live action timeline (edit, undo, redo events
  with timestamps, page numbers, and change descriptions).
- **TOC editing** (4.5): edit Table of Contents entries (title and page reference) via the
  TOC Editor panel. Changes appear in preview and export with correct indentation.
- GET /document/page/{n}/table-cells endpoint for per-cell detection
- GET /session/journal, POST /session/save-as, POST /session/load, GET /session/files
- PUT /document/page/{n}/toc endpoint for TOC entry editing

### Fixed
- **Undo/redo preview**: undone edits no longer show in the page preview. Fixed by
  filtering `get_page_edits_from_session` to only include active (not undone) edits.
- **Undo/redo navigation**: undo/redo now navigates to the affected page automatically.
- **Table cell alignment**: cell values centered at original text center-x position.
- **Table structure preservation**: multi-line blocks always use fragment extraction
  (prevents paragraph reflow from destroying table layout).
- **TOC entry preservation**: TOC edits use inline redact (not paragraph reflow),
  section numbers preserved at x=90, titles at x=114.
- **Font rendering**: all text insertion uses PDF base-14 fonts (Times-Roman, Helvetica,
  Courier) for universal viewer compatibility. No more "Liberation Serif not found" errors.
- **Table cell borders**: redaction rect shrunk by 0.5-1pt to avoid covering thin border rects.
- **Image cache**: nginx proxy sends no-cache headers, image URLs use Math.random() for
  guaranteed fresh fetches.
- **TBD Dashboard filter**: initializes from currently opened document on mount.
- Block overlays hidden when table cell overlays are present in same zone.

### Changed
- File menu simplified (removed Save/Undo/Redo — moved to Session menu)
- Session menu is now a top-level toolbar item (Save, Save As, Load, New, Undo, Redo)
- Docker compose mounts `./src:/app/src` for live code reloading during development
- 21 integration tests (3 new for session persistence, 1 for TOC indentation)

---

## [1.2.1] — 2026-08-01

### Fixed
- **Export pipeline**: switched from broken full-page rawdict rebuild to targeted patch
  approach (redact+insert). Unedited content now stays pixel-perfect in exports.
- **Heading preservation**: section headings (e.g., "4. Electrical Interface") in bold/
  sans-serif font are no longer destroyed when the paragraph below them is edited.
  The heading stays in its original font at its original position.
- **Overflow merging**: when edited text overflows page N, the overflow now appears at
  the top of page N+1 with existing content pushed down (not superimposed on top of it).
  Total page count stays the same when overflow fits on the next page.
- **Page 8 preview**: the document viewer now detects overflow from the previous page
  and rebuilds the next page's preview image with overflow content prepended.
- **Table cell border preservation**: the redaction rect for table cell edits is now
  shrunk by 0.5–1pt to avoid whiting out the thin filled rectangles that form cell borders.
- **Frontend image refresh**: `applyEdit` and `redo` now increment `refreshTrigger`,
  ensuring the page image reloads in the viewer after every edit/undo/redo action.

### Changed
- Export-download route uses `_apply_edit_to_page` directly on the source document
  (same approach as `POST /document/export`), no more page_rebuild for export.
- `page_rebuild.py` rewritten with system fonts (TextWriter + Liberation/Windows TTF),
  heading/paragraph splitting, and overflow span propagation — used only for overflow
  page reconstruction (prepending overflow onto the next page).
- Docker compose mounts `./src:/app/src` for live code reloading during development.
- `editorStore.ts` redo action now fetches undo/redo availability from backend.

### Added
- Integration test suite: `tests/integration/test_page_rebuild_pipeline.py` (13 tests)
  covering page preview, heading preservation, overflow handling, undo/redo cycle,
  and export consistency. Runs in 3.6s using local TestClient (no Docker needed).

---

## [1.2.0] — 2026-07-31

### Added
- 1:1 page patching engine: edits now redact and replace text directly on the source PDF
  - Preserves all original formatting, fonts, colors, and positions
  - Table cells center-aligned within column (matches original alignment)
  - Paragraph text uses full block reflow with justified word-wrap
- Paragraph reflow on edit: entire paragraph block retypeset with `insert_textbox` + justify
- Alignment detection: auto-distinguishes table cells (center) from paragraph text (justify)
- System font matching: Liberation Serif (Docker) / Times New Roman (Windows) for metric-identical rendering
- Color preservation: inserted text uses the original span's color
- Comprehensive test suite: 577 tests pass locally, 66 Docker-only tests
- Docker test infrastructure: `@pytest.mark.docker_only` marker, auto-skip, runner script
- Auto-indexing: all ICD PDFs indexed before test session via `pytest_sessionstart`

### Changed
- Page image endpoint uses PyMuPDF redaction+insertion instead of WeasyPrint full re-render
- Export endpoint uses same 1:1 patching (unedited pages byte-identical to source)
- Footer blocks no longer incorrectly moved during page split (pre-shift position check)
- Fragment detection uses character-level diff with word-boundary expansion
- Dockerfile includes test dependencies and full tests/ directory

### Fixed
- Table 4.3 edit (30W→25W): renders centered in column with correct font and color
- Paragraph 4.1 edit: no longer overflows past line end (full paragraph reflow)
- Paragraph 4.2 edit (TBR→value): no whitespace gap (full line rewrite with justify)
- Footer reflow bug: footer blocks at y>page_height-50 stay in place during page split
- OpenSearch availability check uses socket (no more test hangs on Windows)
- All 19 pre-existing test failures fixed

---

## [1.1.0] — 2026-07-29

### Added
- Page extension: edits that overflow a page boundary automatically create new pages
  - Phase 1: paragraph blocks moved to new page
  - Phase 2: list items, captions, and tables moved to new page
- Document delete via UI (File > Remove Document) — removes from OpenSearch, IR, and TBD dashboard
- Per-chunk embedding progress during indexing ("embedding chunk 42/86")
- 25 unit tests for page split logic
- 3 e2e tests for page extension via API

### Changed
- Overflow detection no longer misclassifies reflowed blocks as footers
- Reflow engine uses `reflow_and_split()` as the main entry point (combines reflow + split)
- Renderer handles pages with no source PDF (fully IR-rendered for split pages)
- Edit API response now includes `total_pages`, `page_added`, and `new_page_number`

---

## [1.0.0] — 2026-07-28

### Added
- Docker containerization: backend, frontend, and OpenSearch in docker-compose
- Document upload and ingestion pipeline with progress modal (upload → extract → index → TBD detect)
- Per-config indexing progress in status polling
- File menu (traditional dropdown) with Upload, Save, Export, Undo, Redo
- Status bar with real-time ingestion progress
- Document list filtering: only indexed documents appear in the dropdown
- TBD dashboard document filter (third dropdown)
- Pre-commit config: hadolint, gitleaks, oxlint, check-ast, mixed-line-ending
- 13 unit tests for text extractor heading split
- 7 e2e tests for ingest endpoint
- 9 e2e tests for document list and TBD filters
- USER_GUIDE.md with full demo walkthrough

### Fixed
- UTF-8 encoding across all file I/O (Windows cp1252 compatibility)
- Text extraction: split blocks when section headings appear mid-text (fixes misattributed TBDs)
- Export PDF: handle missing session gracefully with clear error message
- TBD dashboard: use filename instead of PDF metadata for document_title
- TBD navigation: stay on TBD tab (don't switch to editor or diff)
- TBD document switch: correct same-document detection using page range
- Dark mode: Diff tab callout colors now theme-aware
- Frontend API base: uses relative URLs through nginx proxy in containers
- OpenSearch connection: configurable via OPENSEARCH_HOST/PORT/SCHEME env vars

### Changed
- Toolbar redesigned: separate Upload button removed (lives in File menu only)
- Documents endpoint only returns indexed documents
- Dockerfiles organized into `docker/` directory with descriptive headers

---

## [0.9.0] — 2026-07-27

### Added
- Phase 3: TBD/TBR tracker with semantic validation
- Phase 4: Search pipeline, RAG, TBD dashboard, model benchmarking
- Phase 5: Text reflow engine (word wrap, block push-down, overflow detection)
- Phase 6: Document version detection and differential analysis
- Backend API: search, RAG, TBD dashboard, version diff, reflow integration
- Frontend: search panel, TBD dashboard, version diff, element navigation
- Comprehensive test suite: 290 tests across 7 documents
- ICD test corpus expansion (7 documents) with Git LFS

---

## [0.3.0] — 2026-07-26

### Added
- Export PDF with browser save-as dialog
- Table cell editing with Apply button
- Undo/redo for all edit types
- Dark/light mode toggle
- Header/footer detection and editing
- Page content analysis (labels elements by type)
- TOC editor
- Unified click-to-edit interface (replaces 3 separate editors)
- Paragraph merging for body text editing
- Grid density table detection

### Fixed
- Block edit 422 errors (EditRequest model placement)
- Table cell persistence across undo/redo
- TOC page overlay handling
- Two-column page element detection

---

## [0.2.0] — 2026-07-26

### Added
- Working UI: PDF viewer, table editor, file upload
- FastAPI backend with session journal and model configuration
- React frontend scaffold
- Phase 2: edit-to-export loop and requirement extraction

---

## [0.1.0] — 2026-07-25

### Added
- Initial PDF extraction pipeline (PyMuPDF)
- Document IR intermediate representation (YAML/JSON)
- Faithful PDF rendering via HTML/CSS + WeasyPrint
- Page classification (text, scanned, table, diagram)
- Character-level text positioning
- Image extraction with border detection
- Visual fidelity comparison reports
