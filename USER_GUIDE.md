# ICD Writer — User Guide

A walkthrough of the ICD Writer application using the included NASA Interface Control Documents.

---

## Prerequisites

Start the full application stack:

```bash
docker compose up -d
```

Wait for all services to be healthy (~30 seconds), then open:

- **Application**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **OpenSearch Dashboard**: http://localhost:5601

---

## 1. Uploading and Indexing a Document

The first step is uploading a PDF so the system can extract its structure, index it for search, and detect TBD/TBR items.

### Steps

1. Click **File** in the top-left menu bar
2. Select **Upload & Index...**
3. Choose a PDF from the `icds/digital/` folder — start with `20130010957.pdf` (TSAFE ICD, 15 pages, small and fast)
4. The **progress modal** appears showing the pipeline stages:
   - **Uploading PDF** — file transfer to backend
   - **Extracting text & structure** — PDF parsed into structured Document IR
   - **Indexing into OpenSearch** — text chunked, embedded via AWS Bedrock, stored in 4 search configurations
   - **Detecting TBD/TBR items** — scans for unresolved items
   - **Complete** — shows summary: pages, text blocks, chunks indexed, TBD/TBR counts
5. The document automatically opens in the viewer

### What Happens Behind the Scenes

| Stage | What it does | Output |
|-------|-------------|--------|
| Extract | PyMuPDF parses the PDF into text blocks with bounding boxes, fonts, reading order | `output/<stem>_document_ir.yaml` |
| Index | Text is chunked (paragraph, section, sliding window), embedded via Amazon Titan V2, stored in OpenSearch | 4 search indices |
| TBD Scan | Regex + context analysis finds TBD/TBR/TBC markers | Items added to TBD Dashboard |

### Recommended Demo Order

| Document | Pages | Description | Notable Features |
|----------|-------|-------------|-----------------|
| `20130010957.pdf` | 15 | TSAFE Interface Control Document | Fast to index, good for search demo |
| `HSI_SYS_015G.pdf` | 8 | HSI Spectrometer ICD | Contains TBR items, thermal requirements |
| `20150010976.pdf` | 35 | LVC (Live Virtual Constructive) ICD | TBD items, larger doc, message definitions |
| `IDSS_IDD_RevE.pdf` | ~100 | IDSS Docking System IDD Rev E | Large doc, version diff with Rev F |
| `IDSS_IDD_RevF.pdf` | ~100 | IDSS Docking System IDD Rev F | Pair with Rev E for diff comparison |
| `ICESat2_ATL03.pdf` | ~150 | ICESat-2 ATL03 Algorithm Document | Very large, tests scalability |
| `NDS_IDD_RevC.pdf` | ~100 | NASA Docking System IDD | Thermal, electrical, data interfaces |

---

## 2. Opening an Indexed Document

Once a document has been indexed, it appears in the **Open Document** dropdown in the toolbar.

1. Click the **— Open Document —** dropdown
2. Select any previously indexed document
3. The viewer loads with the PDF rendered page-by-page on the left and the editing panel on the right

---

## 3. Viewing and Navigating

### Document Viewer (Left Panel)

- **Page navigation**: Use the page controls at the top of the viewer (Previous / Next / page number input)
- **Element highlighting**: Hover over text blocks to see their bounding boxes; click to select for editing
- **Zoom**: The page renders at 150 DPI for readability

### Right Panel Tabs

| Tab | Purpose |
|-----|---------|
| **Editor** | Edit selected text blocks, undo/redo |
| **Search** | Semantic search + RAG across all indexed documents |
| **TBDs** | Cross-document TBD/TBR tracking dashboard |
| **Diff** | Version comparison between related documents |

---

## 4. Editing Text

1. Click on any text block in the document viewer — it highlights in blue
2. The **Editor** tab activates with the selected text
3. Edit the text in the editing area
4. Click **Apply** to save the change
5. The document view updates immediately
6. Use **Undo/Redo** (File menu or Ctrl+Z/Ctrl+Y) to revert

### Page Extension (Automatic)

When an edit makes a text block long enough to push content past the bottom of the page, the system automatically creates a new page:

1. Open `HSI_SYS_015G.pdf` and navigate to **page 4**
2. Click any paragraph block in the body area
3. Replace the text with a very long passage (e.g., paste the same sentence 50+ times)
4. Click **Apply**
5. The response will show:
   - `page_added: true` — a new page was created
   - `new_page_number` — the inserted page number
   - `total_pages` — the updated document length
6. Navigate to the new page — it contains the overflowing paragraph blocks

**How it works:**
- The reflow engine calculates word-wrap height for the edited block
- Subsequent blocks are shifted down to accommodate the new height
- If any paragraph block's bottom edge exceeds the page margin (72pt from bottom), the system:
  - Creates a new page with the same dimensions
  - Moves all overflowing paragraph blocks to the new page
  - Repositions them starting at the top margin
  - Renumbers all subsequent pages
- Headers and footers are never moved
- Export PDF includes the new pages rendered from the document structure

**Currently supported block types for page extension:**
- Paragraphs (Phase 1)
- Tables (Phase 2)
- Lists (Phase 2)

### Exporting

After making edits:
1. **File > Export PDF...** generates a new PDF with your changes applied
2. The browser downloads the edited PDF
3. If pages were added during editing, the exported PDF will include those additional pages

---

## 5. Semantic Search (Search Tab)

Search across all indexed documents using natural language.

### Example Queries for Demo

With `20130010957.pdf` (TSAFE) indexed:

| Query | What it finds |
|-------|--------------|
| "What triggers a conflict check in TSAFE?" | Track Update, Vector, and Altitude Amendments |
| "conflict detection algorithm" | Algorithm description and parameters |
| "input data format from radar" | Radar data interface specification |

With `HSI_SYS_015G.pdf` indexed:

| Query | What it finds |
|-------|--------------|
| "thermal operating limits for the spectrometer" | Temperature ranges and constraints |
| "heater circuit specifications" | Heater power, thermostat settings |
| "detector characteristics" | Germanium detector specs |

With `20150010976.pdf` (LVC) indexed:

| Query | What it finds |
|-------|--------------|
| "What is the message code for MsgFlightState?" | Message code 5310 |
| "What interfaces does the LVC system provide?" | Message and packet interfaces |
| "What are the TBD items?" | Wind direction, wind speed fields |

### RAG Mode

Toggle **RAG** on (enabled by default) to get synthesized answers with citations instead of raw search results. The AI:
- Only answers from retrieved content (no hallucination)
- Cites source document, section, and page for every claim
- Preserves "shall" statement wording verbatim
- Notes TBD items explicitly
- Includes a confidence indicator (high/medium/low)

---

## 6. TBD Dashboard (TBDs Tab)

Tracks all TBD, TBR, TBC, and TBS items across every indexed document.

### Walkthrough

1. Click the **TBDs** tab
2. If empty, click **Refresh** to scan all indexed documents
3. Use the three filter dropdowns:
   - **Status**: Open / Assigned / Resolved / Verified
   - **Type**: TBD / TBR
   - **Document**: Filter to a specific document
4. Click any item to navigate to its location in the document (page jumps, element highlights)
5. Change item status via the dropdown on each row (track resolution progress)

### What Gets Detected

- `TBD` — To Be Determined (value not yet known)
- `TBR` — To Be Reviewed (value needs verification)
- `TBC` — To Be Confirmed
- `TBS` — To Be Supplied

Items in "shall" statements are flagged as contractually blocking.

### Cross-Document Correlation

When multiple documents are indexed, the dashboard identifies:
- Related TBD items across documents (same topic, different docs)
- Conflicts (same item resolved differently in different documents)

---

## 7. Version Diff (Diff Tab)

Compare two versions of the same document to identify what changed.

### Demo with IDSS IDD

1. Upload and index both `IDSS_IDD_RevE.pdf` and `IDSS_IDD_RevF.pdf`
2. Open `IDSS_IDD_RevF.pdf` from the dropdown
3. The **Diff** tab automatically detects Rev E as a related version
4. Click **Compare** next to Rev E
5. The diff shows:
   - **Summary**: counts of modified/added/removed sections, requirement changes, TBD changes
   - **Per-section diffs**: expandable rows showing old vs new text
   - **AI Summarize**: click to get an AI explanation of what changed in each section (small cost per section)

### Change Classifications

| Icon | Classification | Meaning |
|------|---------------|---------|
| ⚠️ | Technical | Requirement or interface change |
| 🔧 | Structural | Section reorganization |
| 📝 | Editorial | Wording/formatting change |

---

## 8. Dark Mode

Click the **🌙** button in the toolbar to toggle dark mode. All panels, including the Diff tab callouts, adapt to the dark theme.

---

## 9. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Browser (localhost:3000)                            │
│  React + Vite → nginx                              │
└──────────────────────┬──────────────────────────────┘
                       │ /session, /document, /search,
                       │ /tbd-dashboard, /documents
        ┌──────────────▼──────────────┐
        │  Backend (localhost:8000)     │
        │  FastAPI + Uvicorn           │
        │  - PDF extraction (PyMuPDF)  │
        │  - Rendering (WeasyPrint)    │
        │  - Search (OpenSearch + kNN) │
        │  - RAG (Bedrock Nova Pro)    │
        │  - TBD tracking              │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  OpenSearch (localhost:9200)  │
        │  - BM25 keyword index        │
        │  - kNN vector index (1024d)  │
        │  - 4 index configurations    │
        └─────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  AWS Bedrock                 │
        │  - Titan Embed V2 (vectors)  │
        │  - Cohere Embed V3 (vectors) │
        │  - Nova Pro (RAG answers)    │
        └─────────────────────────────┘
```

---

## 10. CLI Commands (Advanced)

The backend also exposes a CLI for batch operations:

```bash
# Ingest a PDF into Document IR
docker run --rm -v ./icds:/app/icds -v ./output:/app/output icd_writer-backend \
  python -m src.cli ingest icds/digital/20130010957.pdf

# Search from command line
docker run --rm --network icd_writer_default icd_writer-backend \
  python -m src.cli search "conflict detection" --mode rrf -k 5

# Run search evaluation benchmark
docker run --rm --network icd_writer_default icd_writer-backend \
  python -m src.cli search-eval

# Check for new embedding models on Bedrock
docker run --rm icd_writer-backend \
  python -m src.cli search-models

# Compare two document versions
docker run --rm -v ./icds:/app/icds icd_writer-backend \
  python -m src.cli version-diff icds/digital/IDSS_IDD_RevE.pdf icds/digital/IDSS_IDD_RevF.pdf
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Failed to fetch" on search | Ensure OpenSearch is running: `docker compose ps` should show `icd-opensearch` healthy |
| "No document loaded" on export | Open a document from the dropdown before exporting |
| Upload progress stalls at "Indexing" | Check AWS credentials are configured (`~/.aws/credentials`) |
| Documents not appearing in dropdown | Only indexed documents appear — upload via File > Upload & Index |
| TBD dashboard empty | Click Refresh, or upload documents that contain TBD/TBR markers |

---

## Included Test Documents

| File | Source | Content |
|------|--------|---------|
| `20130010957.pdf` | NASA TM 2013-216034 | TSAFE (Tactical Separation Assisted Flight Environment) ICD V2.0 |
| `20150010976.pdf` | NASA/TM-2015-218951 | LVC (Live Virtual Constructive) Gateway ICD |
| `HSI_SYS_015G.pdf` | NASA/JPL | Hyperspectral Infrared Spectrometer System ICD |
| `ICESat2_ATL03.pdf` | NASA GSFC | ICESat-2 ATL03 Geolocated Photon Algorithm |
| `IDSS_IDD_RevE.pdf` | NASA | International Docking System Standard IDD Rev E |
| `IDSS_IDD_RevF.pdf` | NASA | International Docking System Standard IDD Rev F |
| `NDS_IDD_RevC.pdf` | NASA | NASA Docking System Interface Definition Document Rev C |
