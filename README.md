# ICD Writer

**v1.1.0** — NASA Interface Control Document (ICD) editor with semantic search, TBD tracking, and version comparison.

Extracts text, tables, and structure from PDF ICDs into an editable intermediate representation, provides AI-powered search (RAG) across the corpus, tracks TBD/TBR items cross-document, compares document revisions, and exports edited PDFs.

## Quick Start (Docker)

```bash
docker compose up -d
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| OpenSearch | http://localhost:9200 |
| OpenSearch Dashboards | http://localhost:5601 |

See [USER_GUIDE.md](USER_GUIDE.md) for a full walkthrough.

## Features

- **PDF Extraction** — PyMuPDF extracts text blocks with bounding boxes, fonts, and reading order
- **Document Editing** — Click-to-edit text blocks with undo/redo, page reflow, and PDF export
- **Page Extension** — Edits that overflow a page automatically create new pages (paragraphs, lists, tables)
- **Semantic Search** — Hybrid BM25 + kNN vector search across all indexed ICDs via OpenSearch
- **RAG (AI Answers)** — Natural language questions answered with citations via AWS Bedrock
- **TBD Dashboard** — Cross-document TBD/TBR/TBC tracking with status management and correlation
- **Version Diff** — Compare document revisions, identify requirement changes, AI-summarize diffs
- **Upload & Index Pipeline** — Upload PDF → extract → embed → index with real-time progress
- **Document Management** — Add and remove documents from the system via the UI
- **Dark/Light Mode** — Full theme support across all panels

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Frontend (React + Vite, served via nginx)            │
│  localhost:3000                                       │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Backend (FastAPI + Uvicorn)                          │
│  localhost:8000                                       │
│  • PDF extraction (PyMuPDF)     • Search (OpenSearch) │
│  • Rendering (WeasyPrint)       • RAG (Bedrock)       │
│  • Text reflow + page split     • TBD tracking        │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  OpenSearch 2.17 (vector + keyword search)            │
│  localhost:9200                                       │
└──────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  AWS Bedrock (embedding + generation)                 │
│  • Amazon Titan Embed V2 (1024d vectors)              │
│  • Cohere Embed English V3                            │
│  • Amazon Nova Pro (RAG generation)                   │
└──────────────────────────────────────────────────────┘
```

## Local Development (without Docker)

```bash
# Python backend
python -m venv .venv
.venv/Scripts/activate  # Windows
source .venv/bin/activate  # Linux/Mac
pip install -e ".[dev]"
pip install opensearch-py requests-aws4auth
uvicorn src.api.app:create_app --factory --port 8000

# Frontend
cd frontend
npm install
npm run dev

# OpenSearch (required for search features)
docker compose up -d opensearch
```

## Testing

```bash
# Run all tests (219 tests)
python -m pytest tests/ -v

# Unit tests only (fast, no services needed)
python -m pytest tests/unit/ -v

# E2E tests (needs OpenSearch for some)
python -m pytest tests/e2e/ -v
```

## CLI

```bash
python -m src.cli ingest icds/digital/20130010957.pdf
python -m src.cli search "conflict detection" --mode rrf --rag
python -m src.cli search-index output/20130010957_document_ir.yaml
python -m src.cli version-diff icds/digital/IDSS_IDD_RevE.pdf icds/digital/IDSS_IDD_RevF.pdf
python -m src.cli tbd-dashboard --ingest output/*_document_ir.yaml
```

## Project Structure

```
docker/                  Dockerfiles (backend, cli, frontend)
frontend/                React app (Vite + TypeScript)
src/
  api/                   FastAPI endpoints
  extraction/            PDF text extraction
  models/                Pydantic models (Document IR, ICD IR)
  ocr/                   OCR pipeline (Textract, Rekognition, Bedrock)
  rendering/             PDF regeneration (HTML/CSS + WeasyPrint)
  search/                OpenSearch indexing, retrieval, RAG, TBD dashboard
  reflow.py              Text reflow + page extension engine
  pipeline.py            Document processing pipeline
tests/
  unit/                  Unit tests (models, reflow, search, extraction)
  e2e/                   End-to-end API tests
icds/                    Test ICD corpus (Git LFS)
schemas/                 JSON schemas for Document IR and ICD IR
```

## Requirements

- Python 3.10+
- Node.js 20+ (frontend)
- Docker (for full stack)
- AWS credentials (for Bedrock embeddings and RAG)

## License

MIT
