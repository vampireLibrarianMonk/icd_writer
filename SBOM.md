# ICD Writer — Software Bill of Materials (SBOM)

Version: 1.1.0
Generated: 2026-07-29
Runtime: Python 3.10+ / Node.js 22+

---

## Python Core Dependencies (pinned in pyproject.toml)

| Package | Version | Purpose |
|---------|---------|---------|
| pydantic | 2.11.3 | Data models and validation |
| pyyaml | 6.0.2 | Document IR serialization |
| pymupdf | 1.25.5 | PDF text/image extraction |
| pdfplumber | 0.11.6 | PDF table extraction |
| pikepdf | 9.7.0 | PDF manipulation |
| pillow | 11.2.1 | Image processing |
| numpy | 2.2.6 | Numerical operations |
| weasyprint | 69.0 | HTML-to-PDF rendering |
| fastapi | 0.115.12 | REST API framework |
| uvicorn | 0.34.2 | ASGI server |
| jinja2 | 3.1.6 | HTML templating |
| boto3 | >=1.35.0 | AWS SDK (Bedrock, Textract) |
| python-multipart | >=0.0.20 | File upload handling |

## Python Runtime Dependencies (installed separately)

| Package | Version | Purpose |
|---------|---------|---------|
| opensearch-py | 2.8.0 | OpenSearch client |
| requests-aws4auth | >=1.3.0 | AWS request signing for OpenSearch |
| httpx | >=0.28.0 | HTTP client (TestClient requirement) |

## Python Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | 8.3.5 | Test framework |
| pytest-cov | 6.1.1 | Coverage reporting |
| ruff | 0.11.12 | Linter and formatter |
| mypy | 1.15.0 | Static type checker |

## Frontend Dependencies (package.json)

| Package | Version | Purpose |
|---------|---------|---------|
| react | ^19.2.7 | UI framework |
| react-dom | ^19.2.7 | React DOM rendering |
| zustand | ^5.0.14 | State management |
| pdfjs-dist | ^6.1.200 | PDF rendering in browser |

## Frontend Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| vite | ^8.1.1 | Build tool |
| typescript | ~6.0.2 | Type checking |
| @vitejs/plugin-react | ^6.0.3 | React HMR |
| oxlint | ^1.71.0 | TypeScript/React linter |

## Container Images

| Image | Version | Purpose |
|-------|---------|---------|
| python | 3.10-slim | Backend base |
| node | 22-alpine | Frontend build |
| nginx | alpine | Frontend serving + API proxy |
| opensearchproject/opensearch | 2.17.0 | Vector + keyword search engine |
| opensearchproject/opensearch-dashboards | 2.17.0 | Search visualization (optional) |

## System Dependencies (apt packages in backend container)

| Package | Purpose |
|---------|---------|
| libpango-1.0-0, libpangocairo-1.0-0 | WeasyPrint text rendering |
| libgdk-pixbuf-2.0-0 | Image format handling |
| libffi-dev | Foreign function interface |
| libcairo2 | 2D graphics library |
| libglib2.0-0 | GLib utilities |
| libmupdf-dev | PDF rendering (PyMuPDF) |
| fonts-crosextra-carlito | Calibri substitute (Google Carlito) |
| fonts-crosextra-caladea | Cambria substitute (Google Caladea) |
| fonts-liberation2 | Arial/Times/Courier substitutes |
| fonts-dejavu-core | Fallback sans/serif/mono |
| fontconfig | Font discovery and configuration |
| curl | Health check in container |

## AWS Services Used

| Service | Purpose | Cost Model |
|---------|---------|-----------|
| Bedrock — Titan Embed V2 | Document chunk embeddings (1024d) | $0.0001/1K tokens |
| Bedrock — Cohere Embed V3 | Alternative embeddings (1024d) | $0.0001/1K tokens |
| Bedrock — Nova Pro | RAG answer generation | Per-token (input + output) |
| Textract | OCR for scanned PDFs (optional) | $0.0015/page |
| Rekognition | Diagram label detection (optional) | Per-image |

## Pre-commit Hooks

| Hook | Source | Purpose |
|------|--------|---------|
| trailing-whitespace | pre-commit-hooks | File hygiene |
| end-of-file-fixer | pre-commit-hooks | Consistent EOF |
| check-yaml, check-json, check-toml | pre-commit-hooks | Syntax validation |
| check-ast | pre-commit-hooks | Python syntax |
| mixed-line-ending | pre-commit-hooks | LF normalization |
| detect-private-key | pre-commit-hooks | Security |
| ruff | ruff-pre-commit | Python lint + format |
| mypy | mirrors-mypy | Type checking |
| hadolint | hadolint | Dockerfile linting |
| gitleaks | gitleaks | Secrets scanning |
| oxlint | local | TypeScript/React linting |
