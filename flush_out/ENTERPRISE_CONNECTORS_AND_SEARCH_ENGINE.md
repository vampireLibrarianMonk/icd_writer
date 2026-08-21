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
| **Phase 1** | Confluence connector (auth + browse + import) | 3-4 days | None |
| **Phase 2** | SharePoint connector (auth + browse + import) | 3-4 days | None |
| **Phase 3** | Document format converters (DOCX, PPTX, XLSX) | 2-3 days | Connectors |
| **Phase 4** | Lineage data model + manual linking | 2 days | Connectors |
| **Phase 5** | Auto-detection (cross-ref + similarity matching) | 3 days | Phase 4 + search |
| **Phase 6** | Lineage UI panel + staleness alerting | 2-3 days | Phase 4-5 |
| **Phase 7** | Change sync (pull updates, diff view) | 2-3 days | Phase 6 |

### Phase 0 is urgent — NMSLIB is already deprecated and will break on OpenSearch 3.0.

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

## References

- [OpenSearch k-NN methods and engines](https://docs.opensearch.org/latest/field-types/supported-field-types/knn-methods-engines/) — NMSLIB deprecated
- [OpenSearch vector search performance tuning](https://docs.opensearch.org/latest/vector-search/performance-tuning/) — Engine comparison
- [Switch default engine nmslib→faiss (OpenSearch issue #2163)](https://github.com/opensearch-project/k-NN/issues/2163)
- [Atlassian REST API examples](https://developer.atlassian.com/cloud/confluence/rest-api-examples/)
- [Microsoft Graph Python SDK (GA)](https://devblogs.microsoft.com/microsoft365dev/introducing-the-microsoft-graph-python-sdk/)
- [Office365-REST-Python-Client](https://github.com/vgrem/Office365-REST-Python-Client) — alternative SharePoint SDK
