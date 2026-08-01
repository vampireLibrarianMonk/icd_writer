# ICD Writer — User Guide

**Version 1.1.0**

---

## Prerequisites

Start the application:

```bash
docker compose up -d
```

Wait ~30 seconds for all services to become healthy, then open http://localhost:3000.

AWS credentials must be configured (`~/.aws/credentials`) for search indexing and RAG features.

---

## 1. Upload and Indexing

Upload a PDF to extract its structure, index it for search, and detect TBD/TBR items.

### Document: `20130010957.pdf` (TSAFE ICD, 15 pages)

**Steps:**

1. Click **File > Upload & Index...**
2. Select `icds/digital/20130010957.pdf`
3. The progress modal appears with live status updates:

| Step | Status Message | What's Happening |
|------|---------------|-----------------|
| 1 | Uploading PDF | File transferred to backend |
| 2 | Extracting text & structure | PyMuPDF parses 15 pages into 81 text blocks |
| 3 | Indexing titan-v2-paragraph: embedding chunk 42/86 | Each chunk embedded via AWS Bedrock, stored in OpenSearch |
| 4 | Detecting TBD/TBR items | Regex + context scan for unresolved markers |
| 5 | Complete! 15 pages, 215 chunks indexed, 0 TBDs | Summary of what was processed |

4. Click **Open Document** — the PDF loads in the viewer
5. The document now appears in the **Open Document** dropdown for future sessions

**Expected result:** The document is searchable, viewable, and editable. The dropdown shows `20130010957.pdf`.

---

## 2. AI-Powered Search

Ask natural language questions across all indexed documents. Answers come with citations.

### Document: `20130010957.pdf` (must be indexed from Step 1)

**Steps:**

1. Click the **Search** tab (right panel)
2. The "AI answers with citations" checkbox is enabled by default
3. Type a query and press Enter

### Example: "What triggers a conflict check in TSAFE?"

**Answer (high confidence, 1939ms, $0.0028):**

> Three record types trigger a conflict check in TSAFE: Track Update (TRK), Vector Amendment (VEC), and Altitude Amendment (ALT) [1][6].
>
> For Track Update (TRK), each record triggers an immediate check for conflicts between the flight for which the record applies and all other traffic in the Center [4][5].
>
> For Vector Amendment (VEC), each record triggers an immediate check for conflicts between the flight for which the record applies and all other traffic in the Center, unless the flight is under TSAFE control [7].
>
> For Altitude Amendment (ALT), each record triggers an immediate check for conflicts between the flight for which the record applies and all other traffic in the Center (unless the flight is under TSAFE control) [7].

**Sources cited:** 8 chunks from pages 7, 8, 10, 11, 13, 15

---

### Example: "What is the input data format from radar?"

**Answer (high confidence, 1893ms, $0.0030):**

> The input data format from radar consists of a line of standard ASCII text with data fields delimited by spaces. Multiple records can be sent in a single message by separating the records with semicolons. The data fields include:
>
> 1. Time/sec
> 2. Flight ID
> 3. Relative track time
> 4. X coordinate in nautical miles (nmi)
> 5. Y coordinate in nautical miles (nmi)
> 6. Altitude in feet (ft)
> 7. Groundspeed in knots (kn)
> 8. Course angle in degrees (deg)
> 9. Altitude rate in feet per minute (fpm)
> 10. Sector number
>
> If TSAFE is configured to produce its own velocity estimates, it will ignore fields 7–9 (groundspeed, course angle, and altitude rate) [4][7].

**Sources cited:** 8 chunks from pages 3, 7, 8, 11, 12

---

### Example: "How does TSAFE predict trajectories?"

**Answer (high confidence, 1230ms, $0.0025):**

> TSAFE predicts trajectories for approximately 3 minutes into the future [1]. It uses inputs such as flight registration data, route amendments, vector amendments, altitude amendments, track updates, wind data, and IFR/VFR status changes to make these predictions [3][4].

**Sources cited:** 8 chunks from pages 3, 5, 7, 9, 13, 15

---

### How Search Results Work

Each answer includes:
- **Synthesized response** — plain English answer derived only from retrieved content
- **Inline citations** — `[N]` referencing numbered source passages
- **Confidence** — high/medium/low based on retrieval scores and answer coverage
- **Cost and timing** — per-query Bedrock cost and response time
- **Expandable sources** — click to see the raw text chunks that informed the answer

**Uncheck "AI answers with citations"** to see raw search hits instead — ranked chunks with scores, page numbers, and text previews.

---

## 3. TBD/TBR Tracking

Track unresolved items across all indexed documents with status management.

### Document: `HSI_SYS_015G.pdf` (HSI Spectrometer, 8 pages — has TBR items)

**Steps:**

1. **File > Upload & Index...** → select `icds/digital/HSI_SYS_015G.pdf`
2. Wait for ingestion to complete (fast — 8 pages)
3. Click the **TBDs** tab (right panel) — items appear automatically since the ingest pipeline detected them

**Expected result:**

- 2 TBR items appear: `TBR-UCB-102` (page 5) and `TBR-UCB-110` (page 7)
- Stats cards show: 2 Open, 0 Assigned, 0 Resolved
- The "in shall statements" warning appears (these TBRs are contractually blocking)

**Note:** If you're returning to a previous session where documents were already indexed, click **Refresh** to reload the TBD state from disk.

### Using the Filters

| Filter | Action | Result |
|--------|--------|--------|
| Document: `HSI_SYS_015G.pdf` | Shows only HSI items | 2 items |
| Type: TBR | Shows only TBR items | Filters out any TBDs |
| Status: Open | Default — shows unresolved items | All items initially |

### Navigating to a TBD Item

1. Click any TBR item row
2. The document viewer jumps to that page and highlights the element
3. The right panel **stays on the TBD tab** (doesn't switch to Editor)

### Changing Status

Use the status dropdown on each item to track progress: Open → Assigned → Resolved → Verified.

---

## 4. Editing and Page Extension

Edit text blocks directly in the PDF. If edits expand content past the page boundary, the system automatically creates a new page.

### Document: `HSI_SYS_015G.pdf` (already loaded from Step 3)

---

### 4.1 Basic Paragraph Edit

1. Navigate to **page 5** (Section 2 — Mechanical Interface)
2. Click the paragraph that begins: *"An 'all sky' field of view is also desired for the detectors..."*
3. The **Editor** tab activates showing the selected text
4. Change "reasonable effort" to "all reasonable effort" in the sentence
5. Click **Apply**
6. The document view updates with your revised text
7. **File > Undo** reverts to the original

---

### 4.2 Editing a Requirement (TBR Value)

1. Stay on **page 5** (Section 2.4.1 — Cryocooler)
2. Click the paragraph containing: *"...will not exceed (TBR-UCB-102) newtons driven at 59 Hz."*
3. In the Editor, replace `(TBR-UCB-102)` with `0.5` to resolve the TBR:
   *"...will not exceed 0.5 newtons driven at 59 Hz."*
4. Click **Apply**
5. The value is now resolved in the document view

---

### 4.3 Editing Table Data (TBR in a Table)

1. Navigate to **page 7** (Section 3.2.1 — Spectrometer Heaters)
2. Click directly on the text overlay containing the table data (not the table zone box):
   Look for the overlay showing *"Characteristic Setting Power 30W (TBR-UCB-110)..."*
3. The **Editor** tab shows the full text block
4. Find `30W (TBR-UCB-110)` and change it to `25W`
5. Click **Apply**
6. The page re-renders showing the updated value

**Tip:** If the table zone editor opens instead (showing a grid), click outside it to deselect, then click the text overlay directly. Some tables are stored as text blocks rather than structured grids.

**Note:** After resolving a TBR in the document text, go to the **TBDs** tab and update the item's status from "Open" to "Resolved" to keep the dashboard in sync.

---

### 4.4 Triggering Page Extension (Overflow)

When an edit makes a block too large for the remaining page space, overflowing content moves to a new page.

1. Navigate to **page 7** (Section 3.2.1 — Spectrometer Heaters)
2. Click the heading/paragraph starting with: *"4. Electrical Interface — The IDPU will be the single-point electrical interface..."* (near the bottom of the page)
3. Replace the text with a much longer passage — paste this:

   > The Spectrometer consists of a Cryostat that houses nine segmented high-purity Germanium detectors that provide primary science data across the energy range of 3 keV to 17 MeV. These detectors are actively cooled to liquid nitrogen temperatures (approximately 77K) by the helium-based Stirling cycle mechanical cryocooler. The cooler is electrically driven by the Cooler Power Controller (CPC), which in turn is commanded and monitored by the Instrument Data Processing Unit (IDPU). The Spectrometer assembly also includes the attenuator shutter mechanism for managing photon rates during solar flares, the Charge Sensitive Amplifiers (CSA) for signal conditioning, and the High Voltage Filters for detector biasing, all mounted externally on the Cryostat structure.

4. Click **Apply**
5. Observe:
   - The status bar shows the page count increased (e.g., "9 pages" instead of "8 pages")
   - Blocks that were pushed below the page margin are now on the new page
   - Navigate forward one page to see the displaced content

**What moves to the new page:**

| Block Type | Behavior |
|-----------|----------|
| Paragraphs | Moved if they overflow the bottom margin |
| List items | Moved (stay grouped with nearby items) |
| Captions | Moved (travel with their associated content) |
| Headings | Moved if they overflow (keeps structure with following content) |
| Tables | Moved if they extend past the boundary |
| Headers/Footers | Never moved (fixed position) |

---

### 4.5 Undo and Redo

All edits support undo/redo:

- **File > Undo** (or Ctrl+Z) — reverts the last change
- **File > Redo** (or Ctrl+Y) — re-applies an undone change
- The undo stack tracks each individual edit
- Page extensions are also undone (the extra page is removed)

---

## 5. Version Comparison

Compare two revisions of the same document to identify what changed.

### Documents: `IDSS_IDD_RevE.pdf` + `IDSS_IDD_RevF.pdf`

**Steps:**

1. **File > Upload & Index...** → select `icds/digital/IDSS_IDD_RevE.pdf`
2. Wait for ingestion (~100 pages, takes longer)
3. **File > Upload & Index...** → select `icds/digital/IDSS_IDD_RevF.pdf`
4. Wait for ingestion
5. Open `IDSS_IDD_RevF.pdf` from the **Open Document** dropdown
6. Click the **Diff** tab — it automatically detects Rev E as a related version
7. Click **Compare** next to Rev E

**Expected result:**

The diff summary shows:
- Sections modified / added / removed
- Requirement changes (flagged with ⚠️)
- TBD changes
- Text overlap percentage
- Estimated AI summary cost

**Per-section details:**

Each changed section is expandable:
- **Orange border** = modified
- **Green border** = added
- **Red border** = removed

Click a section to see old vs. new text. Click **Summarize with AI** for a plain-English explanation of what changed (small per-section cost).

### Change Classifications

| Icon | Classification | Example |
|------|---------------|---------|
| ⚠️ | Technical | Requirement value changed |
| 🔧 | Structural | Section reorganized or split |
| 📝 | Editorial | Wording or formatting change |

---

## 6. Exporting

Generate a PDF with all your edits applied.

### Steps:

1. Make edits to the loaded document (any document)
2. **File > Export PDF...**
3. The browser downloads `<filename>_edited.pdf`
4. If pages were added during editing, they're included in the export

**Note:** Pages without edits are copied pixel-perfect from the source. Only edited pages go through re-rendering.

---

## 7. Document Management

### Removing a Document

1. Open the document from the dropdown
2. **File > Remove Document...**
3. Confirmation dialog shows what will be removed:
   - Search index data (all OpenSearch chunks)
   - Extracted document structure (IR file)
   - Associated TBD/TBR items
4. Click OK
5. The document disappears from the dropdown

**Note:** PDFs in `icds/digital/` are never deleted from disk (source-controlled). Only uploaded PDFs in `uploads/` are removed.

---

## 8. Additional Features

### Dark Mode

Click **🌙** in the toolbar to toggle. All panels including Diff tab callouts adapt.

### Search Across Multiple Documents

Once multiple documents are indexed, search queries return results from all of them. RAG answers synthesize across documents with per-source citations.

### Cross-Document TBD Correlation

With multiple documents indexed, the TBD dashboard can identify:
- Related TBD items across documents (same topic, different docs)
- Conflicts (same item resolved differently in different documents)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Browser (localhost:3000)                            │
│  React + Vite → nginx                              │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  Backend (localhost:8000)     │
        │  FastAPI + Uvicorn           │
        │  - PDF extraction (PyMuPDF)  │
        │  - Rendering (WeasyPrint)    │
        │  - Text reflow + page split  │
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

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Failed to fetch" on search | Ensure OpenSearch is running: `docker compose ps` should show `icd-opensearch` healthy |
| "No document loaded" on export | Open a document from the dropdown before exporting |
| Upload stalls at "Indexing" | Check AWS credentials: `aws sts get-caller-identity` |
| Documents not in dropdown | Only indexed documents appear — upload via File > Upload & Index |
| TBD dashboard empty | Click Refresh after uploading documents with TBD/TBR markers |
| Diff tab says "No related versions" | Both versions must be uploaded and indexed (not just on disk) |

---

## Test Documents Reference

| File | Pages | Content | Best For |
|------|-------|---------|----------|
| `20130010957.pdf` | 15 | TSAFE ICD (conflict detection) | Quick upload, search demo |
| `HSI_SYS_015G.pdf` | 8 | Spectrometer ICD (thermal) | TBD/TBR tracking, editing |
| `20150010976.pdf` | 35 | LVC Gateway ICD (messages) | TBD items, larger doc |
| `IDSS_IDD_RevE.pdf` | ~100 | Docking System IDD Rev E | Version diff (pair with Rev F) |
| `IDSS_IDD_RevF.pdf` | ~100 | Docking System IDD Rev F | Version diff (pair with Rev E) |
| `ICESat2_ATL03.pdf` | ~150 | ATL03 Algorithm Document | Scalability testing |
| `NDS_IDD_RevC.pdf` | ~100 | NASA Docking System IDD | Multi-interface search |
