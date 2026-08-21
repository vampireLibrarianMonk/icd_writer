# Enterprise Connectors & Search Engine Modernization

**Priority:** High
**Status:** Not started
**Last updated:** 2026-08-21

---

## Overview

Three interconnected capabilities:

1. **Confluence & SharePoint connectors** — Pull documents (PDF, DOCX, PPTX, images) from enterprise document management systems into the ICD Writer corpus
2. **Document lineage view** — A new pane showing which source documents feed which ICD sections, and what upstream changes affect downstream content
3. **OpenSearch engine migration** — Move from deprecated NMSLIB to Lucene or Faiss for vector search (breaking change in OpenSearch 3.0)

---

## Part 1: Enterprise Document Connectors

### Problem

ICD documents don't live in isolation. Teams maintain requirements in Confluence wikis, share interface drawings on SharePoint, and distribute specifications as Word/PowerPoint/PDF attachments. Currently, users must manually download files and upload them to ICD Writer.

### Goal

Connect to Confluence and SharePoint, browse available document libraries, select documents for import, and pull them into the ICD Writer pipeline (extract → index → track).

### Confluence Integration

**API:** Atlassian REST API v2 (Cloud) or v1 (Data Center/Server)
**Python SDK:** `atlassian-python-api` (PyPI, actively maintained)
**Auth:** OAuth 2.0 (Cloud) or Personal Access Token (Data Center)

**Capabilities needed:**
- List spaces and pages the user has access to
- Export pages as PDF (via `/wiki/rest/api/content/{id}/export/pdf`)
- Download page attachments (PDF, DOCX, PPTX, images)
- Get page body as storage format (HTML) for direct text extraction
- Watch pages for changes (webhook or polling via `lastModified`)

**Key endpoints:**
```
GET  /wiki/api/v2/spaces                    → list spaces
GET  /wiki/api/v2/spaces/{id}/pages         → list pages in space
GET  /wiki/rest/api/content/{id}/child/attachment → list attachments
GET  /wiki/rest/api/content/{id}/export/pdf → export page as PDF
GET  /wiki/rest/api/content/{id}?expand=body.storage → page HTML body
```

**Document types from Confluence:**
- Pages exported as PDF (full formatting preserved)
- Attached PDFs, Word docs, PowerPoint, images
- Page body HTML (lightweight — for requirements text extraction)

### SharePoint Integration

**API:** Microsoft Graph API v1.0
**Python SDK:** `msgraph-sdk` (official Microsoft, GA since Nov 2023) or `Office365-REST-Python-Client`
**Auth:** OAuth 2.0 with MSAL (Azure AD app registration required)

**Capabilities needed:**
- List sites, document libraries, and folders
- Download files (PDF, DOCX, PPTX, XLSX, images)
- Get file metadata (modified date, author, version history)
- Delta queries for change detection (what's new since last sync)

**Key endpoints:**
```
GET  /sites/{site-id}/drives                        → list document libraries
GET  /drives/{drive-id}/root/children               → list root folder
GET  /drives/{drive-id}/items/{item-id}/content     → download file
GET  /drives/{drive-id}/items/{item-id}/versions    → version history
GET  /drives/{drive-id}/root/delta                  → changed items since last sync
```

**Document types from SharePoint:**
- PDF, DOCX, PPTX, XLSX files directly
- OneNote notebooks (export as PDF via Graph)
- Images (PNG, JPG, TIFF) — feed to OCR pipeline

### Implementation Architecture

```
src/connectors/
├── __init__.py
├── base.py              # Abstract ConnectorBase (list, download, watch)
├── confluence.py        # Confluence connector (REST API)
├── sharepoint.py        # SharePoint connector (Microsoft Graph)
├── auth/
│   ├── oauth_confluence.py  # OAuth 2.0 flow for Atlassian Cloud
│   └── oauth_sharepoint.py  # MSAL auth flow for Azure AD
├── sync.py              # Sync engine (poll, diff, pull new/changed docs)
└── converters/
    ├── docx_to_pdf.py   # python-docx + WeasyPrint or LibreOffice
    ├── pptx_to_pdf.py   # python-pptx → images → PDF
    └── xlsx_extract.py  # openpyxl → structured text for IR
```

**Backend endpoints:**
```
GET  /connectors                          → list configured connectors
POST /connectors/confluence/configure     → set URL, auth token, spaces
POST /connectors/sharepoint/configure     → set tenant, client, site
GET  /connectors/{id}/browse              → file/folder tree
POST /connectors/{id}/import              → pull selected docs into pipeline
GET  /connectors/{id}/sync-status         → last sync, pending changes
POST /connectors/{id}/sync               → pull latest changes
```

**Frontend: Connector Panel**
- New tab "Sources" in the left panel
- Tree view of connected Confluence spaces / SharePoint libraries
- Checkboxes to select documents for import
- "Sync" button to pull latest changes
- Status indicators: synced, pending, conflict

### Document Conversion Pipeline

Not all source docs are PDF. Conversion strategy:

| Source Format | Conversion Method | Output |
|--------------|-------------------|--------|
| PDF | None (direct ingest) | Document IR |
| DOCX | python-docx text extraction OR LibreOffice headless → PDF | Document IR |
| PPTX | python-pptx slide extraction → text + images | Document IR (per-slide) |
| XLSX | openpyxl → structured table text | Document IR (table blocks) |
| Images (PNG/JPG/TIFF) | OCR pipeline (Textract or Tesseract) | Document IR |
| Confluence HTML | BeautifulSoup parse → structured sections | Document IR |

### Configuration Storage

```yaml
# .env or config file
CONFLUENCE_URL=https://yourcompany.atlassian.net
CONFLUENCE_TOKEN=<personal-access-token>
CONFLUENCE_SPACES=ENG,ICD,SPEC

SHAREPOINT_TENANT_ID=<azure-tenant-id>
SHAREPOINT_CLIENT_ID=<app-registration-client-id>
SHAREPOINT_CLIENT_SECRET=<client-secret>
SHAREPOINT_SITE=https://yourcompany.sharepoint.com/sites/Engineering
```

---

## Part 2: Document Lineage & Traceability View

### Problem

When a Confluence page updates (e.g., a requirements spec changes), which ICD sections are affected? When an ICD is edited locally, which upstream sources is it derived from? There's no visibility into these relationships.

### Goal

A new panel/view showing:
1. **Upstream sources** — Which Confluence pages / SharePoint files feed into each indexed ICD
2. **Downstream impact** — When a source changes, which ICD sections/blocks may need updates
3. **Staleness detection** — Highlight ICD content that's older than its upstream source
4. **Change propagation** — Show a diff between the current ICD text and the updated source

### Data Model

```python
@dataclass
class DocumentLink:
    """A relationship between an upstream source and a downstream ICD block."""
    source_connector: str          # "confluence" or "sharepoint"
    source_id: str                 # page ID, file ID, or URL
    source_title: str              # human-readable name
    source_last_modified: datetime # when the source was last changed
    target_document: str           # ICD stem (e.g., "HSI_SYS_015G")
    target_page: int | None        # page number in the ICD
    target_block_id: str | None    # specific block, or None = whole doc
    link_type: str                 # "derived_from", "references", "supersedes"
    confidence: float              # 0-1, how certain is this link
    created_by: str                # "auto" (detected) or "manual" (user-defined)
```

### Detection Methods

1. **Explicit links** — User manually links a Confluence page to an ICD section
2. **Cross-reference scanning** — Detect mentions of source doc titles in ICD text
3. **Semantic similarity** — Embedding-based match between source paragraphs and ICD blocks (using existing OpenSearch vector index)
4. **Filename/title matching** — Source filename matches ICD reference section entries

### Lineage View UI

```
┌─────────────────────────────────────────────────────────────┐
│  📊 Document Lineage                                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  HSI_SYS_015G.pdf                                           │
│  ├── Section 2.1 (Mechanical Interface)                     │
│  │   ← Confluence: "HESSI Mech Requirements" (⚠️ STALE)     │
│  │     Source updated: 2026-08-15                           │
│  │     ICD last synced: 2026-07-20                          │
│  │     [View Diff] [Pull Update]                            │
│  │                                                          │
│  ├── Section 4.1 (Power Interface)                          │
│  │   ← SharePoint: "Power_Budget_v3.xlsx"                   │
│  │     ✅ Up to date                                         │
│  │                                                          │
│  └── Section 5.2 (Command Protocol)                         │
│      ← Confluence: "IDPU Command Set Rev H"                 │
│        ✅ Up to date                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Backend Endpoints

```
GET  /lineage/{doc_stem}                    → all links for a document
POST /lineage/link                          → create manual link
DELETE /lineage/link/{link_id}              → remove a link
GET  /lineage/stale                         → all documents with stale upstream sources
POST /lineage/detect/{doc_stem}            → auto-detect links via cross-ref + similarity
GET  /lineage/diff/{link_id}               → compare current ICD block vs updated source
POST /lineage/pull/{link_id}               → update ICD block from source (creates edit)
```

---

## Part 3: OpenSearch Engine Migration (NMSLIB → Lucene/Faiss)

### Problem

Our current index configuration uses `"engine": "nmslib"` for k-NN vector search. Per OpenSearch documentation:
- **NMSLIB is deprecated as of OpenSearch 2.19** (marked legacy)
- **NMSLIB will be removed in OpenSearch 3.0**
- **Faiss became the default engine in OpenSearch 2.18**
- We're running OpenSearch **2.17.0** — one minor version from the deprecation

### Current Configuration

```python
# src/search/indexing.py (line 103)
"engine": "nmslib",

# src/search/benchmark.py (line 643)
"engine": "nmslib",
```

Both hardcoded to nmslib with HNSW algorithm, cosinesimil space type.

### Engine Comparison

| Feature | NMSLIB | Lucene | Faiss |
|---------|--------|--------|-------|
| Status | **Deprecated** (2.19) | Active | Active (**default since 2.18**) |
| Language | C++ (JNI) | Java (native) | C++ (JNI) |
| Algorithms | HNSW only | HNSW only | HNSW + IVF |
| Filtering | Post-filter only | **Native filter during search** | Post-filter (HNSW), Pre-filter (IVF) |
| Memory | Off-heap (mmap) | On-heap + OS page cache | Off-heap (mmap) |
| Index size | Larger | **Smallest** | Medium |
| Latency (small dataset) | Good | **Best** | Good |
| Throughput (indexing) | Good | Good | **Best** |
| Quantization | No | No | Yes (PQ, SQ) |
| On-disk mode | Yes | Yes | Yes |
| Segment merging | External | **Native Lucene merges** | External |
| Concurrent search | Supported | Supported | Supported |

### Recommendation

**Migrate to Lucene** for our use case:
- Our corpus is small (thousands of documents, not millions)
- We need native filtering (filter by document, page range, content type during search)
- Smallest index size (matters for Docker deployments)
- Best latency for datasets under a few million vectors
- Native Lucene segment merging (no JNI overhead)
- GitLab chose Lucene over Faiss for the same filtering reason in their OpenSearch 3.0 migration

**Alternative: Faiss** if we later scale to millions of vectors or need IVF/quantization.

### Migration Steps

1. **Make engine configurable** — Add `knn_engine` field to `IndexConfig`/`SearchConfig`
   ```python
   knn_engine: str = "lucene"  # "lucene", "faiss", or "nmslib" (deprecated)
   ```

2. **Update space_type naming** — Lucene uses `"cosinesimil"` → `"cosinesimil"` (same), but verify distance function naming between engines

3. **Update index mapping builder** in `src/search/indexing.py`:
   ```python
   "method": {
       "name": "hnsw",
       "space_type": "cosinesimil",
       "engine": config.knn_engine,  # was hardcoded "nmslib"
       "parameters": {"ef_construction": 512, "m": 16},
   }
   ```

4. **Re-index existing documents** — Engine change requires new indexes (can't migrate in-place). Strategy:
   - Create new indexes with Lucene engine
   - Re-run ingest pipeline for all documents
   - Delete old nmslib indexes
   - Or: support parallel old+new during transition

5. **Update docker-compose** — Bump to OpenSearch 2.19+ (or 3.0 when stable) for best Lucene/Faiss support

6. **Add engine selection to UI** — In Settings/Admin panel, let user choose engine (for future-proofing)

7. **Benchmark** — Run existing eval harness comparing nmslib vs lucene vs faiss on our corpus
   - Recall@10 comparison
   - Latency p50/p99 comparison
   - Index size comparison

### Filtering Benefit (Why Lucene Matters)

Currently our hybrid search does post-filtering (retrieve k results then filter). With Lucene:
```python
# Current (nmslib) — post-filter, wastes retrieved slots
results = search(query_vector, k=100)
filtered = [r for r in results if r.document == target_doc][:10]

# With Lucene — filter during search, all k results are relevant
results = search(query_vector, k=10, filter={"document": target_doc})
```

This directly improves search quality when filtering by document, page range, or content type.

---

## Implementation Priority

| Phase | Work | Effort | Dependency |
|-------|------|--------|-----------|
| **Phase 0** | OpenSearch engine migration (nmslib → lucene) | 1-2 days | None — do first |
| **Phase 0.5** | Build mock Confluence + SharePoint servers | 2-3 days | None — can parallel |
| **Phase 0.5** | Generate/collect test document corpus | 1-2 days | None — can parallel |
| **Phase 1** | Confluence connector (auth + browse + import) | 3-4 days | Mock server for testing |
| **Phase 2** | SharePoint connector (auth + browse + import) | 3-4 days | Mock server for testing |
| **Phase 3** | Document format converters (DOCX, PPTX, XLSX) | 2-3 days | Connectors + corpus |
| **Phase 4** | Lineage data model + manual linking | 2 days | Connectors |
| **Phase 5** | Auto-detection (cross-ref + similarity matching) | 3 days | Phase 4 + search |
| **Phase 6** | Lineage UI panel + staleness alerting | 2-3 days | Phase 4-5 |
| **Phase 7** | Change sync (pull updates, diff view) | 2-3 days | Phase 6 |

### Phase 0 is urgent — NMSLIB is already deprecated and will break on OpenSearch 3.0.
### Phase 0.5 unblocks all connector development (can test without real services).

---

## Dependencies & Prerequisites

| Dependency | Purpose | Install |
|-----------|---------|---------|
| `atlassian-python-api` | Confluence REST client | `pip install atlassian-python-api` |
| `msgraph-sdk` | Microsoft Graph API client | `pip install msgraph-sdk` |
| `msal` | Azure AD auth for SharePoint | `pip install msal` |
| `python-docx` | DOCX text extraction | `pip install python-docx` |
| `python-pptx` | PPTX slide extraction | `pip install python-pptx` |
| `openpyxl` | XLSX table extraction | `pip install openpyxl` |
| `beautifulsoup4` | Confluence HTML parsing | Already installed |

---

## Security Considerations

- OAuth tokens stored in environment variables (never committed)
- SharePoint requires Azure AD app registration with minimal scopes (`Files.Read.All`, `Sites.Read.All`)
- Confluence Cloud tokens are user-scoped (personal access tokens or OAuth app)
- Connector credentials stored in `.env` (gitignored) or Docker secrets
- All API calls use HTTPS
- Downloaded files stored in `imports/` directory (gitignored)
- Lineage links stored locally (no PII sent to external services)

---

## Part 4: Mock Confluence & SharePoint Servers (Test Infrastructure)

### Problem

We can't run integration tests against real Confluence Cloud or SharePoint Online:
- Requires paid licenses and tenant configurations
- Network-dependent (can't run in CI/CD without credentials)
- Flaky tests from rate limits and auth token expiry
- Can't seed predictable test data in a shared tenant

Real Confluence Server/DC in Docker is possible (`atlassian/confluence:latest`) but it's **heavy** (~2GB image, needs license, 2GB+ RAM, slow startup). Not suitable for a test sidecar.

### Solution: FastAPI-based Faux Servers

Build lightweight Python (FastAPI) services that implement the subset of Confluence REST API and Microsoft Graph API that our connectors actually call. These are:
- Small (~200 lines each)
- Instant startup
- Seed with predictable test documents
- Containerized for docker-compose inclusion
- No licenses, no external dependencies

### Confluence Mock Server

Implements only the endpoints our connector calls:

```python
# mock_servers/confluence/app.py
from fastapi import FastAPI
from pathlib import Path

app = FastAPI(title="Mock Confluence API")

# Seeded test data lives in mock_servers/confluence/data/
SPACES = [...]
PAGES = [...]
ATTACHMENTS_DIR = Path("data/attachments")

@app.get("/wiki/api/v2/spaces")
def list_spaces(): ...

@app.get("/wiki/api/v2/spaces/{space_id}/pages")
def list_pages(space_id: str): ...

@app.get("/wiki/rest/api/content/{page_id}/child/attachment")
def list_attachments(page_id: str): ...

@app.get("/wiki/rest/api/content/{page_id}/export/pdf")
def export_page_pdf(page_id: str): ...

@app.get("/wiki/rest/api/content/{page_id}")
def get_page_content(page_id: str, expand: str = ""): ...

@app.get("/download/attachments/{attachment_id}/{filename}")
def download_attachment(attachment_id: str, filename: str): ...
```

### SharePoint Mock Server (Microsoft Graph API subset)

Implements the Graph API drive/items endpoints:

```python
# mock_servers/sharepoint/app.py
from fastapi import FastAPI
from pathlib import Path

app = FastAPI(title="Mock SharePoint (Graph API)")

FILES_DIR = Path("data/files")

@app.get("/sites/{site_id}/drives")
def list_drives(site_id: str): ...

@app.get("/drives/{drive_id}/root/children")
def list_root(drive_id: str): ...

@app.get("/drives/{drive_id}/items/{item_id}/children")
def list_folder(drive_id: str, item_id: str): ...

@app.get("/drives/{drive_id}/items/{item_id}/content")
def download_file(drive_id: str, item_id: str): ...

@app.get("/drives/{drive_id}/items/{item_id}/versions")
def file_versions(drive_id: str, item_id: str): ...

@app.get("/drives/{drive_id}/root/delta")
def delta_query(drive_id: str, token: str = ""): ...
```

### Directory Structure

```
mock_servers/
├── confluence/
│   ├── Dockerfile            # python:3.10-slim + uvicorn
│   ├── app.py                # FastAPI mock endpoints
│   ├── data/
│   │   ├── spaces.json       # Seeded space definitions
│   │   ├── pages.json        # Seeded pages with metadata
│   │   └── attachments/      # Actual files served as downloads
│   │       ├── requirements_spec.pdf
│   │       ├── interface_drawing.docx
│   │       └── power_budget.xlsx
│   └── requirements.txt      # fastapi, uvicorn
├── sharepoint/
│   ├── Dockerfile
│   ├── app.py                # FastAPI mock Graph API
│   ├── data/
│   │   ├── drives.json       # Seeded drive/library definitions
│   │   ├── items.json        # File/folder tree with metadata
│   │   └── files/            # Actual files served as downloads
│   │       ├── system_architecture.pptx
│   │       ├── test_report_v2.pdf
│   │       ├── signal_parameters.xlsx
│   │       └── meeting_notes.docx
│   └── requirements.txt
└── README.md                 # How to run, seed, and extend
```

### Docker Compose Integration

```yaml
# Added to docker-compose.yml
  mock-confluence:
    build: ./mock_servers/confluence
    container_name: icd-mock-confluence
    ports:
      - "8090:8090"
    volumes:
      - ./mock_servers/confluence/data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-s", "http://localhost:8090/wiki/api/v2/spaces"]
      interval: 5s
      retries: 3

  mock-sharepoint:
    build: ./mock_servers/sharepoint
    container_name: icd-mock-sharepoint
    ports:
      - "8091:8091"
    volumes:
      - ./mock_servers/sharepoint/data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-s", "http://localhost:8091/sites/default/drives"]
      interval: 5s
      retries: 3
```

### Test Strategy

```python
# tests/integration/test_ug_connectors.py
# Configure connector to hit mock servers (env vars or test fixture)
CONFLUENCE_URL = "http://localhost:8090"
SHAREPOINT_URL = "http://localhost:8091"

def test_confluence_list_spaces(connector_client):
    spaces = connector_client.list_spaces()
    assert len(spaces) >= 2
    assert any("Engineering" in s["name"] for s in spaces)

def test_sharepoint_download_file(connector_client):
    content = connector_client.download("drive-1", "item-pptx-001")
    assert len(content) > 1000
    # Verify it's a real PPTX (ZIP magic bytes)
    assert content[:4] == b"PK\x03\x04"
```

### Why Not WireMock/MockServer?

WireMock (Java) or MockServer (Java/Node) would work but add:
- Java runtime dependency (we're Python-native)
- Separate stub definition language (JSON mappings)
- Can't serve actual binary files easily from seeded directories
- Harder to extend with custom logic (pagination, delta queries)

A FastAPI mock is the same stack we already use — trivial to maintain, debug, and extend.

---

## Part 5: Test Document Corpus (Multi-Format)

### Problem

We need a realistic collection of documents across all supported formats to:
1. Test the connector import pipeline end-to-end
2. Test document conversion (DOCX→IR, PPTX→IR, etc.)
3. Seed the mock servers with real content
4. Validate that search/indexing works across heterogeneous document types
5. Demonstrate the tool to stakeholders with realistic content

### Document Type Coverage

Your original listing of document types is solid. Here's the expanded matrix with rationale:

| Format | Role in ICD Ecosystem | Source Strategy | Needed |
|--------|----------------------|-----------------|--------|
| **PDF** | Primary ICD documents, formal specifications | Already have (NASA NTRS) | ✅ Have 7+ |
| **DOCX** | Requirements specs, meeting minutes, design docs | Create + NASA NTRS | Need 5-8 |
| **PPTX** | Design reviews, architecture overviews, CDR/PDR | Create + public NASA | Need 3-5 |
| **XLSX** | Parameter budgets, interface tables, test matrices | Create from ICD data | Need 3-5 |
| **Images (PNG/JPG/TIFF)** | Interface drawings, block diagrams, photos | Extract from PDFs + create | Need 5-10 |
| **HTML/Confluence** | Wiki-style requirements, living specs | Create for mock server | Need 5-8 |

### Recommended Corpus Composition

#### Tier A: Generated from Existing ICD Content (Most Realistic)

Derive test documents from our existing NASA ICD corpus — this gives us realistic aerospace content without copyright issues (all NASA work is public domain):

| Document | Format | Derived From | Content |
|----------|--------|-------------|---------|
| `HSI_Power_Budget.xlsx` | XLSX | HSI_SYS_015G Section 3.1 | Power interface parameters in tabular form |
| `HSI_Mechanical_Requirements.docx` | DOCX | HSI_SYS_015G Section 2 | Mechanical interface requirements as a Word doc |
| `IDSS_Architecture_Overview.pptx` | PPTX | IDSS_IDD_RevF overview sections | 10-slide architectural overview |
| `TSAFE_Data_Format_Spec.docx` | DOCX | 20130010957 Section 3 | Input/output data format specification |
| `TSAFE_Test_Matrix.xlsx` | XLSX | 20130010957 test cases | Test case matrix with pass/fail columns |
| `Cryocooler_Interface_Drawing.png` | PNG | HSI_SYS_015G Section 2.4 | Block diagram of cryocooler interface |
| `Docking_Mechanism_Photo.jpg` | JPG | IDSS public photos | Docking system hardware photo |
| `Design_Review_Presentation.pptx` | PPTX | Mixed sources | CDR-style review deck |
| `Meeting_Notes_2026-07.docx` | DOCX | Generated | Interface review meeting minutes |
| `Signal_Parameters_RevC.xlsx` | XLSX | NDS_IDD_RevC tables | Signal/timing parameters extracted to spreadsheet |

#### Tier B: Public Domain Downloads (Real-World Diversity)

| Source | Format | URL/Location | Notes |
|--------|--------|-------------|-------|
| NASA NTRS presentations | PPTX | ntrs.nasa.gov (filter by "Presentation") | Real CDR/PDR decks |
| NASA NTRS tech reports | PDF | Already in repo | 200K+ available |
| openpreserve/format-corpus | Mixed | github.com/openpreserve/format-corpus | CC0 licensed sample files for every format |
| getsamplefiles.com | All | getsamplefiles.com | Lightweight format test files |
| US Government Excel data | XLSX | data.gov | Public domain government spreadsheets |

#### Tier C: Synthetic Generation Script

A Python script that auto-generates realistic test documents:

```python
# scripts/generate_test_corpus.py

def generate_requirements_docx(icd_ir, section_range, output_path):
    """Generate a Word doc from ICD Document IR section text."""
    from docx import Document
    doc = Document()
    doc.add_heading("Requirements Specification", 0)
    for section in icd_ir.sections[section_range]:
        doc.add_heading(section.title, level=1)
        for block in section.blocks:
            doc.add_paragraph(block.text)
    doc.save(output_path)

def generate_parameter_xlsx(icd_ir, table_pages, output_path):
    """Extract table data from ICD into an Excel workbook."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Parameters"
    # ... extract table data from IR
    wb.save(output_path)

def generate_overview_pptx(icd_ir, output_path):
    """Generate a presentation from ICD overview sections."""
    from pptx import Presentation
    prs = Presentation()
    # Title slide
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = icd_ir.metadata.filename
    # ... add content slides
    prs.save(output_path)
```

### Corpus Directory Layout

```
test_corpus/
├── README.md                          # What's here, licensing, how to regenerate
├── pdf/                               # Already in icds/digital/ (symlinked)
│   └── (existing ICD PDFs)
├── docx/
│   ├── HSI_Mechanical_Requirements.docx
│   ├── TSAFE_Data_Format_Spec.docx
│   ├── Meeting_Notes_2026-07.docx
│   ├── Requirements_Change_Request.docx
│   └── Interface_Agreement.docx
├── pptx/
│   ├── IDSS_Architecture_Overview.pptx
│   ├── Design_Review_Presentation.pptx
│   └── CDR_Thermal_Analysis.pptx
├── xlsx/
│   ├── HSI_Power_Budget.xlsx
│   ├── TSAFE_Test_Matrix.xlsx
│   ├── Signal_Parameters_RevC.xlsx
│   └── Mass_Properties_Tracker.xlsx
├── images/
│   ├── Cryocooler_Interface_Drawing.png
│   ├── Docking_Mechanism_Photo.jpg
│   ├── Block_Diagram_Power.png
│   └── Connector_Pinout_J1.tiff
├── html/
│   ├── confluence_requirements_page.html
│   ├── confluence_design_decisions.html
│   └── wiki_interface_status.html
└── scripts/
    ├── generate_corpus.py             # Auto-generate from existing ICD IRs
    └── download_public_sources.py     # Fetch from NTRS, format-corpus, etc.
```

### Is Your Document Type Listing Satisfactory?

**Yes, with one addition.** Your original list (PDF, PPT, DOC, images) covers the core 80% of what an aerospace engineering team produces. The expanded list adds:

| Addition | Why |
|----------|-----|
| **XLSX** | Critical — parameter budgets, test matrices, and compliance trackers live in spreadsheets. Most ICD table data originates from Excel. |
| **HTML (Confluence pages)** | Important — many teams keep living requirements in wikis, not static documents. The connector pulls these natively. |
| **TIFF** | Edge case — scanned engineering drawings from legacy programs often come as TIFF. Worth including for OCR pipeline coverage. |

**Not needed for initial scope:**
- CAD files (STEP, IGES) — future, requires specialized viewers
- Visio (.vsdx) — rare, can be exported as PNG
- LaTeX — rare in ICD world (more academic)
- OneNote — can export as PDF via Graph API

### Success Criteria

The test corpus is sufficient when:
1. Each format has ≥3 representative files with realistic aerospace content
2. Mock servers can serve all formats and the import pipeline handles them
3. After import, all documents appear in the ICD Writer document list
4. Search returns results across all indexed document types
5. The lineage view can track relationships between PDF ICDs and their source DOCX/XLSX/PPTX files

---

## References

- [OpenSearch k-NN methods and engines](https://docs.opensearch.org/latest/field-types/supported-field-types/knn-methods-engines/) — NMSLIB deprecated
- [OpenSearch vector search performance tuning](https://docs.opensearch.org/latest/vector-search/performance-tuning/) — Engine comparison
- [Switch default engine nmslib→faiss (OpenSearch issue #2163)](https://github.com/opensearch-project/k-NN/issues/2163)
- [Atlassian REST API examples](https://developer.atlassian.com/cloud/confluence/rest-api-examples/)
- [Microsoft Graph Python SDK (GA)](https://devblogs.microsoft.com/microsoft365dev/introducing-the-microsoft-graph-python-sdk/)
- [Office365-REST-Python-Client](https://github.com/vgrem/Office365-REST-Python-Client) — alternative SharePoint SDK
