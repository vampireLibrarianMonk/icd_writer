# ICD Writer Strategy

## 1. Project Objective

Build a web-based editor for NASA Interface Control Documents (ICDs). The system ingests PDF ICDs, extracts their structure into an editable intermediate representation, provides AI-powered search across the corpus, tracks unresolved items (TBD/TBR), compares document revisions, and exports edited PDFs with pixel-perfect fidelity for unedited content.

### Origin

The v1 attempt (icd_venture) proved that digitally-generated PDFs already contain all information needed for faithful reproduction — exact character coordinates, vector geometry, embedded images. No layout inference or OCR is needed. The v2 approach (this project) builds on that insight: extract what the PDF knows, make it editable, and write it back.

### Current State

The system is operational with a full Docker deployment (frontend + backend + OpenSearch). Users can upload PDFs, search across them with AI-generated answers, edit text in-place (paragraphs, tables, TOC entries), track TBD/TBR items across documents, compare revisions, and export edited PDFs.

---

## 2. Core Architecture

```text
Browser (React)  →  Backend API (FastAPI)  →  OpenSearch (search index)
                                            →  AWS Bedrock (embeddings + RAG)
                                            →  Source PDFs (on disk)
```

### Editing Pipeline

```text
Source PDF (read-only on disk)
    → PyMuPDF extraction → Document IR (in-memory Pydantic model)
    → User edits block text in the UI → IR updated
    → Preview: patch source page in-place (redact + insert) → PNG
    → Export: same patch approach → save modified PDF
```

The key insight for editing: **don't rebuild the whole page**. Patch only the edited text on the source PDF page. Unedited content stays pixel-perfect because it's never touched.

### Search Pipeline

```text
Document IR → chunking (paragraph/sliding window) → embeddings (Bedrock Titan V2)
    → OpenSearch kNN index (1024d vectors) + BM25 keyword index
    → Hybrid retrieval (RRF fusion) → RAG generation (Nova Pro) → Answer + Citations
```

---

## 3. Delivery Phases

### Phase 1: Foundation — COMPLETE

PDF extraction, Document IR, HTML/CSS rendering, visual fidelity comparison, font substitution, Docker containerization.

### Phase 2: Editing Pipeline — COMPLETE

- Click-to-edit text blocks in the browser
- Paragraph reflow (word-wrap within block width)
- Page extension (overflow creates new pages)
- Undo/redo with session journal
- PDF export with 1:1 page patching
- Table cell editing (centered, border-preserving)
- TOC entry editing (title + page reference)
- Heading preservation (bold headings stay intact when paragraph below is edited)

### Phase 3: Semantic Layer — COMPLETE

- TBD/TBR/TBC/TBS detection and tracking
- Cross-document correlation and conflict detection
- Status management (Open → Assigned → Resolved → Verified)
- Requirement extraction from "shall" statements
- Version comparison (structured diff with AI summaries)

### Phase 4: Search and Intelligence — COMPLETE

- OpenSearch hybrid indexing (BM25 + kNN vector)
- Multiple index configurations (paragraph, sliding window, Titan V2, Cohere V3)
- RAG pipeline with citations and confidence scoring
- Upload & Index pipeline with real-time progress
- TBD Dashboard (cross-document, filterable, navigable)
- Cost tracking per operation

### Phase 5: Production Hardening — IN PROGRESS

- Integration test suite (17 tests covering edit/preview/export/undo/redo/overflow/TOC)
- Docker compose with volume mounts for development
- Frontend refresh triggers on all edit operations
- Overflow content merges onto next page (no superimposition)

---

## 4. Key Design Decisions

### Patch vs Rebuild

The system patches the source PDF page in-place (redact old text → insert new text) rather than reconstructing pages from scratch. This preserves all fonts, images, drawings, and formatting exactly. Only the edited text is re-rendered.

### Fragment-Level Edits

The session records the full block's old/new text for undo, but computes the **smallest changed fragment** for PDF patching. This ensures `page.search_for()` finds the correct text to redact, even on pages with repeated words.

### Overflow Handling

When edited text grows beyond the page boundary, overflow lines are prepended to the top of the next page. The original next-page content is shifted down using a full rawdict rebuild (TextWriter with system fonts). Headers/footers stay at fixed positions.

### System Fonts for Metric Fidelity

When pages must be rebuilt (overflow), the system uses Liberation family fonts (Linux) or Windows core fonts — these are metrically identical to the document's embedded fonts. Text is written via `fitz.TextWriter` + `fitz.Font(fontfile=...)` for exact character positioning.

---

## 5. What Limits Visual Fidelity

| Factor | Impact | Mitigation |
|--------|--------|-----------|
| Font glyph shape | Subpixel antialiasing differences | Use metric-compatible fonts (same widths, different outlines) |
| Rebuilt pages | Text re-rendered with substitute fonts | Only rebuild when overflow requires it; all other pages patched |
| Table border proximity | Redaction can clip adjacent 0.5pt borders | Shrink redaction rect by 0.5-1pt |
| TOC leader dots | Dots not regenerated on title edit | Only the title text is replaced; dots/numbers stay |

---

## 6. Repository Structure

```
icd_writer/
├── docker-compose.yml       Full-stack deployment
├── docker/                  Dockerfiles (backend, cli, frontend)
├── frontend/                React app (Vite + TypeScript + Zustand)
├── src/
│   ├── api/                 FastAPI endpoints + session management
│   ├── models/              Pydantic models (Document IR, ICD IR)
│   ├── ingestion/           PDF reading, hashing, metadata
│   ├── rendering/           Page patching (page_patch.py) + rebuild (page_rebuild.py)
│   ├── search/              OpenSearch indexing, retrieval, RAG, TBD dashboard
│   ├── reflow.py            Text reflow + page extension engine
│   └── pipeline.py          Document processing pipeline
├── tests/
│   ├── unit/                Model tests, reflow, search
│   ├── integration/         Edit → preview → export cycle tests (17 tests)
│   └── e2e/                 Full API tests
├── icds/                    Test ICD corpus (Git LFS)
├── schemas/                 JSON schemas for Document IR
├── docs/                    Phase requirements, design docs
├── SBOM.md                  Software Bill of Materials
├── USER_GUIDE.md            Full user walkthrough
└── CHANGELOG.md             Release history
```
