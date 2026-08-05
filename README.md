# ICD Writer

NASA Interface Control Document (ICD) editor with semantic search, TBD tracking, version comparison, and faithful PDF export.

Extracts text, tables, and structure from PDF ICDs into an editable intermediate representation, provides AI-powered search (RAG) across the corpus, tracks TBD/TBR items cross-document, compares document revisions, and exports edited PDFs with pixel-perfect fidelity for unedited content.

## Quick Start

```bash
docker compose up -d
```

Wait ~30 seconds for services to become healthy, then open http://localhost:3000.

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:3000 | Browser UI |
| Backend API | http://localhost:8000 | REST endpoints |
| OpenSearch | http://localhost:9200 | Search engine |
| OpenSearch Dashboards | http://localhost:5601 | Index inspection |

AWS credentials must be configured (`~/.aws/credentials`) for embedding and RAG features.

See [USER_GUIDE.md](USER_GUIDE.md) for a full walkthrough with examples.

## Features

- **PDF Extraction** — Text blocks with bounding boxes, fonts, and reading order
- **Document Editing** — Click-to-edit paragraphs, table cells (inline), and TOC entries with undo/redo
- **Table Cell Editor** — Click directly on table cells in the viewer for instant inline editing
- **Session Management** — Save/Load editing sessions across restarts with full action timeline
- **Page Extension** — Edits that overflow a page merge naturally onto the next page
- **Heading Preservation** — Section headings stay in their original bold font when paragraphs below are edited
- **Semantic Search** — Hybrid keyword + vector search across all indexed ICDs
- **RAG (AI Answers)** — Natural language questions answered with inline citations
- **TBD Dashboard** — Cross-document TBD/TBR tracking with status management and conflict detection
- **Version Diff** — Compare document revisions, flag requirement changes, AI-summarize diffs
- **Upload & Index** — Upload PDF → extract → embed → index with real-time progress
- **Faithful Export** — Unedited pages are byte-identical to source; only edited text is re-rendered

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Frontend (React + Vite, served via nginx)            │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Backend (FastAPI + Uvicorn)                          │
│  • PDF extraction      • Page patching (export)       │
│  • Text reflow         • Search (OpenSearch)          │
│  • TBD tracking        • RAG (Bedrock)                │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  OpenSearch (vector + keyword hybrid search)          │
└──────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  AWS Bedrock (embedding + generation models)          │
└──────────────────────────────────────────────────────┘
```

## Local Development (without Docker)

```bash
# Python backend
python -m venv .venv
.venv/Scripts/activate       # Windows
source .venv/bin/activate    # Linux/Mac
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
# Integration tests (fast, no Docker needed for most)
python -m pytest tests/integration/ -v

# Full suite
python -m pytest tests/ -v

# Page rebuild pipeline specifically
python -m pytest tests/integration/test_page_rebuild_pipeline.py -v
```

## Project Structure

```
docker/                  Dockerfiles (backend, frontend, cli)
frontend/                React app (TypeScript + Zustand)
src/
  api/                   FastAPI endpoints + session management
  models/                Pydantic models (Document IR, ICD IR)
  rendering/             Page patching + rebuild engine
  search/                OpenSearch indexing, retrieval, RAG, TBD dashboard
  reflow.py              Text reflow + page extension
  pipeline.py            Document processing pipeline
tests/
  unit/                  Model, reflow, search tests
  integration/           Edit → preview → export cycle tests
  e2e/                   Full API tests
icds/                    Test ICD corpus (Git LFS)
docs/                    Phase requirements, design documents
```

## Documentation

| Document | Purpose |
|----------|---------|
| [USER_GUIDE.md](USER_GUIDE.md) | Step-by-step usage walkthrough |
| [STRATEGY.md](STRATEGY.md) | Architecture and design decisions |
| [SBOM.md](SBOM.md) | Software Bill of Materials |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## Requirements

- Python 3.10+
- Node.js 20+ (frontend)
- Docker (for full stack)
- AWS credentials (for Bedrock embeddings and RAG)

## License

MIT
