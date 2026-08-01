# ICD Writer — Software Bill of Materials (SBOM)

Last Updated: 2026-08-01

---

## Python Core Dependencies

| Package | Version | Role in Application | Why This Package |
|---------|---------|--------------------|--------------------|
| pydantic | 2.11.3 | Data validation and serialization for the Document IR, session models, API request/response schemas | Industry-standard Python data modeling with runtime validation, JSON schema generation, and type safety |
| pyyaml | 6.0.2 | Serialize/deserialize the Document IR to YAML files on disk for persistence between sessions | Canonical format for human-readable structured data; allows manual inspection and version control of extracted documents |
| pymupdf | 1.25.5 | Core PDF engine — extracts text with character positions, images, vector drawings; applies redaction and text insertion for editing/export | Only Python library providing raw character-level extraction (rawdict), in-place page modification (redaction + insertion), and fast rendering. Alternatives (pdfplumber, PyPDF2) lack modification capabilities |
| pdfplumber | 0.11.6 | Secondary PDF analysis — table structure detection via ruled line clustering | Complements PyMuPDF for table-specific heuristics; better at identifying row/column boundaries from drawn lines |
| pikepdf | 9.7.0 | Low-level PDF object manipulation — metadata access, page stream inspection | Provides direct access to PDF internals that PyMuPDF abstracts away; used for edge cases in document analysis |
| pillow | 11.2.1 | Image processing — pixel comparison for visual fidelity testing, image format conversion | Standard Python imaging library; used in test infrastructure for rendered page comparison |
| numpy | 2.2.6 | Numerical operations for pixel-level fidelity scoring (array comparisons between rendered pages) | Required for efficient image array operations during visual comparison tests |
| weasyprint | 69.0 | HTML/CSS to PDF rendering engine — generates new pages when overflow requires full page reconstruction | The only Python HTML-to-PDF renderer that supports absolute CSS positioning at point-level precision; used only for overflow page reconstruction |
| fastapi | 0.115.12 | REST API framework — all backend endpoints for document operations, search, editing, export | Async-capable, auto-generates OpenAPI docs, Pydantic integration for request validation, high performance |
| uvicorn | 0.34.2 | ASGI server — runs the FastAPI application in production | Standard production ASGI server for FastAPI; handles concurrent requests efficiently |
| jinja2 | 3.1.6 | HTML template rendering for WeasyPrint page generation | Required by FastAPI and WeasyPrint; generates the HTML that WeasyPrint converts to PDF |
| boto3 | >=1.35.0 | AWS SDK — calls Bedrock for embeddings and RAG generation, Textract for OCR | Official AWS Python SDK; provides authenticated access to Bedrock models and Textract |
| python-multipart | >=0.0.20 | Handles multipart file uploads in FastAPI (PDF upload endpoint) | Required by FastAPI for `UploadFile` parameter support |

## Python Runtime Dependencies

| Package | Version | Role in Application | Why This Package |
|---------|---------|--------------------|--------------------|
| opensearch-py | 2.8.0 | OpenSearch client — creates indices, indexes document chunks, executes hybrid search queries | Official OpenSearch Python client; handles both BM25 keyword queries and kNN vector queries |
| requests-aws4auth | >=1.3.0 | AWS Signature V4 authentication for OpenSearch requests when running with IAM auth | Required for AWS-managed OpenSearch domains; signs HTTP requests with AWS credentials |
| httpx | >=0.28.0 | HTTP client used by FastAPI's TestClient for integration testing | Required dependency of Starlette's test infrastructure |

## Python Development Dependencies

| Package | Version | Role |
|---------|---------|------|
| pytest | 8.3.5 | Test framework — runs unit, integration, and e2e test suites |
| pytest-cov | 6.1.1 | Code coverage measurement during test runs |
| ruff | 0.11.12 | Python linter and formatter (replaces flake8 + black + isort) |
| mypy | 1.15.0 | Static type checker for Python source |

## Frontend Dependencies

| Package | Version | Role in Application | Why This Package |
|---------|---------|--------------------|--------------------|
| react | ^19.2.7 | UI component framework — renders the document viewer, editor panels, search interface | Industry-standard component library; declarative rendering, efficient DOM updates |
| react-dom | ^19.2.7 | React's DOM rendering layer | Required companion to React for browser rendering |
| zustand | ^5.0.14 | Global state management — tracks current page, edit state, undo/redo, refresh triggers | Minimal footprint state manager; simpler than Redux, no boilerplate, works well with React hooks |
| pdfjs-dist | ^6.1.200 | Client-side PDF rendering for the document viewer canvas | Mozilla's PDF rendering engine; provides accurate page display in the browser without server round-trips |

## Frontend Dev Dependencies

| Package | Version | Role |
|---------|---------|------|
| vite | ^8.1.1 | Build tool — fast HMR development server, optimized production builds |
| typescript | ~6.0.2 | Static type checking for frontend code |
| @vitejs/plugin-react | ^6.0.3 | Vite plugin for React Fast Refresh (HMR) |
| oxlint | ^1.71.0 | Fast TypeScript/React linter (Rust-based) |

## Container Images

| Image | Version | Role in Application | Why This Image |
|-------|---------|--------------------|--------------------|
| python | 3.10-slim | Backend base image | Slim variant minimizes image size; 3.10 provides required language features (match, type unions) |
| node | 22-alpine | Frontend build stage | Alpine minimizes build image; Node 22 LTS for stable npm/Vite toolchain |
| nginx | alpine | Frontend serving + API reverse proxy | Lightweight static file server; proxies `/document/*`, `/search`, `/session` to backend |
| opensearch | 2.17.0 | Vector + keyword search engine | Provides both BM25 full-text search and kNN vector similarity in a single engine; no separate vector DB needed |
| opensearch-dashboards | 2.17.0 | Search index inspection UI (development only) | Useful for debugging index contents and query behavior; not required for production |

## System Packages (Backend Container)

| Package | Role in Application | Why Required |
|---------|--------------------|--------------------|
| libpango-1.0-0, libpangocairo-1.0-0 | Text layout and rendering for WeasyPrint | WeasyPrint uses Pango for font shaping and line breaking when generating overflow pages |
| libgdk-pixbuf-2.0-0 | Image format loading (PNG, JPEG) for WeasyPrint | Required by WeasyPrint to embed images in generated PDF pages |
| libcairo2 | 2D vector graphics rendering | Core rendering backend for WeasyPrint's PDF output |
| libglib2.0-0 | GLib utilities (Pango dependency) | Required by Pango for Unicode text processing |
| libmupdf-dev | PDF rendering library headers | Required by PyMuPDF's C extension for PDF page manipulation |
| fonts-crosextra-carlito | Metric-compatible substitute for Calibri | Google's Carlito font has identical character widths to Microsoft Calibri; prevents text overflow in documents authored with Calibri |
| fonts-crosextra-caladea | Metric-compatible substitute for Cambria | Google's Caladea font matches Cambria metrics; preserves line breaks in Cambria-authored content |
| fonts-liberation2 | Metric-compatible substitutes for Arial, Times New Roman, Courier New | Liberation Sans/Serif/Mono have identical character widths to their Microsoft counterparts; critical for page patching to maintain line wrapping |
| fonts-dejavu-core | Fallback sans/serif/mono fonts | Catches any text using fonts without a specific metric-compatible substitute |
| fontconfig | Font discovery and matching | Allows PyMuPDF and WeasyPrint to find installed fonts by family name |
| curl | Container health check endpoint | Used in Docker HEALTHCHECK to verify the API is responding |

---

## AI Models

Models accessed via AWS Bedrock. No model weights are stored locally — inference runs in AWS.

### Embedding Models

| Model | Model ID | Dimensions | Role | Cost | Why This Model |
|-------|----------|-----------|------|------|----------------|
| Amazon Titan Text Embeddings V2 | amazon.titan-embed-text-v2:0 | 1024 | Primary document chunk embeddings for vector search | $0.0001/1K tokens | AWS-native, low latency from same region; good balance of quality and cost for technical documents |
| Cohere Embed English V3 | cohere.embed-english-v3 | 1024 | Alternative embedding configuration for benchmark comparison | $0.0001/1K tokens | Higher quality on English technical text in benchmarks; used as comparison baseline |

### Generation Models

| Model | Model ID | Role | Cost (approx) | Why This Model |
|-------|----------|------|---------------|----------------|
| Amazon Nova Pro | us.amazon.nova-pro-v1:0 | RAG answer generation — synthesizes answers from retrieved chunks with inline citations | ~$0.003/query | Best cost/quality ratio for structured answer generation; good at following citation format instructions |
| Amazon Nova Lite | us.amazon.nova-lite-v1:0 | Single-section diff summarization (on-demand, per-click) | ~$0.0005/summary | Cheapest option for short-form summarization where quality requirements are lower |

### OCR / Vision Models (Optional)

| Service | Role | When Used |
|---------|------|-----------|
| AWS Textract | Full-page OCR for scanned PDFs | Only when a PDF has no extractable text (scanned documents) |
| AWS Rekognition | Diagram label detection | Optional — identifies text within diagram images for indexing |
| Bedrock (classification) | Block type disambiguation | Optional — classifies ambiguous text blocks as headings vs paragraphs |

---

## Pre-commit Hooks

| Hook | Purpose |
|------|---------|
| trailing-whitespace | Removes trailing whitespace from all files |
| end-of-file-fixer | Ensures files end with a single newline |
| check-yaml, check-json, check-toml | Validates config file syntax before commit |
| check-ast | Catches Python syntax errors pre-commit |
| mixed-line-ending | Enforces consistent LF line endings |
| detect-private-key | Prevents accidental commit of private keys |
| ruff | Python linting and formatting |
| mypy | Python static type checking |
| hadolint | Dockerfile best-practice linting |
| gitleaks | Scans for accidentally committed secrets/tokens |
| oxlint | TypeScript/React linting for frontend code |
