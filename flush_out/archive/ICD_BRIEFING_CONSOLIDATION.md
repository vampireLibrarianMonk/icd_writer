# ICD Briefing Consolidation — Detailed Design

## Vision

Take multiple ICD documents (digital or scanned/flattened) and produce a
single consolidated briefing document that summarizes interface status,
open items, cross-references, conflicts, and revision changes.

---

## Document Types

### Digital PDFs
- Text is in the content stream (searchable)
- Processed by: `src/pipeline.py` → `process_pdf()`
- Extraction: PyMuPDF rawdict spans with positions
- Output: Document IR (text blocks with bboxes, confidence=1.0)
- Examples: HSI_SYS_015G.pdf, IDSS_IDD_RevF.pdf, NDS_IDD_RevC.pdf

### Flattened/Scanned PDFs
- Text is rasterized into images (not searchable)
- Processed by: `src/ocr/pipeline.py` → `ocr_ingest()`
- Extraction: AWS Textract (words/lines/tables) + Rekognition (labels)
- Classification: AWS Bedrock Nova Lite (page type detection)
- Disambiguation: AWS Bedrock Claude (conflict resolution)
- Output: Same Document IR schema (text blocks with bboxes, lower confidence)
- Examples: icds/flat/ corpus

### How the Briefing Handles Both

The briefing system operates on **Document IR** — the common output of both
pipelines. It never reads raw PDF bytes directly. This means:
- Digital PDFs: indexed immediately, high confidence, exact positions
- Flattened PDFs: indexed after OCR, lower confidence, approximate positions
- The briefing marks confidence levels: "OCR-extracted (85% confidence)"
- TBD detection works the same on both (regex on IR text blocks)

---

## Existing Services & Infrastructure

| Service | Location | What It Does | Used By Briefing |
|---------|----------|--------------|-----------------|
| Document IR | `src/models/document_ir.py` | Structured page/block model | Core data source |
| TBD Tracker | `src/tbd_tracker.py` | Regex-based TBD/TBR detection | Open items aggregation |
| TBD Dashboard | `src/search/tbd_dashboard.py` | Tracks status, owner, resolution | Status reporting |
| Version Diff | `src/version_diff.py` | Compares revisions of same doc | Change summary |
| OpenSearch | Docker service (port 9200) | Full-text + vector search index | Cross-reference detection |
| Embeddings | `src/search/embeddings.py` | Amazon Titan Embed Text V2 (1024d) | Semantic similarity |
| RAG | `src/search/rag.py` | Retrieval-augmented generation | AI summaries (Phase 3+) |
| Chunking | `src/search/chunking.py` | Split docs into searchable chunks | Index preparation |
| OCR Pipeline | `src/ocr/pipeline.py` | Textract + Rekognition + Bedrock | Flattened PDF ingestion |
| WeasyPrint | Python package | HTML → PDF rendering | Briefing PDF output |
| Bedrock (LLM) | AWS us-east-1 | Nova/Claude for generation | AI summaries, conflict analysis |

---

## Phase 1: Two-Document Consolidation (MVP)

### Scope
Select 2 loaded documents → generate a structured briefing.

### Services Used

| Service | Purpose | Cost |
|---------|---------|------|
| Document IR (local) | Read metadata, text blocks | Free |
| TBD Tracker (local) | Extract TBDs/TBRs from IR | Free |
| OpenSearch (Docker) | Find cross-references between docs | Free (local) |
| WeasyPrint (local) | Render briefing HTML → PDF | Free |

No AWS costs in Phase 1. All processing is local.

### Data Flow

```
User selects 2 documents (from loaded/indexed set)
  → POST /briefing/generate { documents: ["HSI_SYS_015G", "IDSS_IDD_RevF"] }
  → Backend:
    1. Load Document IR for each (from output/{stem}_document_ir.yaml)
    2. Run TBD extraction on each IR (src/tbd_tracker.py)
    3. Extract "Applicable Documents" section from each (regex on IR text)
    4. Match cross-references (keyword: does doc A mention doc B's title?)
    5. Compute maturity scores (TBD count / total blocks per section)
    6. Build BriefingDocument model
    7. Render via Jinja2 template → HTML
    8. Convert HTML → PDF via WeasyPrint
    9. Save to output/briefings/{timestamp}_briefing.pdf
  → Returns: { briefing_id, download_url, summary }
```

### Briefing Output Structure

```
┌─────────────────────────────────────────────────┐
│ ICD INTERFACE BRIEFING                          │
│ Generated: 2026-08-05                           │
│ Documents: 2                                    │
├─────────────────────────────────────────────────┤
│ 1. DOCUMENT SUMMARY                            │
│    Table: doc name, rev, pages, date, TBD count│
│                                                 │
│ 2. OPEN ITEMS (TBDs / TBRs)                   │
│    Grouped by document, then by section         │
│    Each: ID, text context, page, owner          │
│                                                 │
│ 3. CROSS-REFERENCES                            │
│    Which docs reference each other              │
│    Shared subsystem names                       │
│                                                 │
│ 4. MATURITY ASSESSMENT                         │
│    Per-section scoring: High/Medium/Low         │
│    Overall interface readiness percentage       │
└─────────────────────────────────────────────────┘
```

### Implementation

```
src/briefing/
├── __init__.py
├── models.py           # BriefingDocument, InterfaceSummary, TbdSummary
├── consolidator.py     # gather_documents() → BriefingDocument
├── cross_reference.py  # detect_cross_refs(doc_a_ir, doc_b_ir) → list[CrossRef]
├── maturity.py         # score_maturity(ir, tbds) → MaturityScore
├── templates/
│   ├── briefing.html   # Jinja2 template for the PDF output
│   └── briefing.css    # Styling for the rendered PDF
└── renderer.py         # render_briefing(BriefingDocument) → PDF bytes
```

**Frontend:**
```
frontend/src/components/BriefingPanel.tsx
- Multi-select dropdown of loaded documents
- "Generate Briefing" button
- Preview area showing the briefing structure
- Download PDF button
```

### Digital vs Flattened Handling (Phase 1)

| Aspect | Digital PDF | Flattened PDF |
|--------|-------------|---------------|
| IR source | `process_pdf()` output | `ocr_ingest()` output |
| TBD detection | Regex on high-confidence text | Same regex, lower confidence |
| Cross-ref extraction | Exact text match in "References" section | Same, but OCR errors may reduce matches |
| Briefing note | None | "* OCR-extracted (confidence: 85%)" |
| Maturity scoring | Standard | Penalized for low-confidence blocks |

---

## Phase 2: Revision Comparison in Briefing

### Scope
For each document in the briefing set, if a previous revision exists,
show what changed.

### Services Used

| Service | Purpose | Cost |
|---------|---------|------|
| Version Diff (local) | `src/version_diff.py` — section-by-section diff | Free |
| Document IR (local) | Both revisions loaded | Free |
| TBD Tracker (local) | Compare TBD counts between revisions | Free |

### Data Flow

```
For each document in the briefing:
  1. detect_families() → find related revisions (RevE, RevF, etc.)
  2. If previous revision exists and is indexed:
     a. full_diff(rev_old, rev_new) → structured diff
     b. Count TBDs in old vs new → delta
     c. Identify new sections, removed sections, modified blocks
  3. Add "Change Summary" section to briefing
```

### Output Addition

```
5. CHANGE SUMMARY
─────────────────
IDSS_IDD_RevF (compared to RevE):
  ✓ 7 TBDs resolved (was 19, now 12)
  + 3 new requirements added (section 4.2)
  ~ 5 sections modified (4.1, 4.3, 5.1, 5.2, 6.3)
  - 0 sections removed
  ! 2 new TBDs introduced (section 5.1)
  Net progress: +5 items resolved
```

### Digital vs Flattened Handling (Phase 2)

| Aspect | Digital PDF | Flattened PDF |
|--------|-------------|---------------|
| Diff algorithm | Text-based section diffing | Same, but noisier due to OCR |
| TBD delta | Exact count comparison | Approximate (OCR may miss some) |
| Section detection | Heading font/size based | Heading detection via OCR + Bedrock classification |
| Confidence note | "Exact comparison" | "Approximate (OCR-based)" |

---

## Phase 3: Conflict Detection

### Scope
Automatically find contradictions between documents for the SAME interface.

### Services Used

| Service | Purpose | Cost |
|---------|---------|------|
| OpenSearch (Docker) | Semantic search for similar requirements | Free (local) |
| Embeddings (AWS) | Amazon Titan Embed V2 — vectorize requirements | ~$0.0001/chunk |
| Bedrock LLM (AWS) | Claude 3.5 Sonnet — analyze conflicts | ~$0.01-0.05/comparison |
| RAG pipeline (local) | `src/search/rag.py` — retrieve + generate | Orchestration only |

**Estimated cost per briefing:** $0.10-0.50 depending on document size.

### Data Flow

```
For each pair of documents in the briefing:
  1. Extract "requirements" from both (src/requirements.py)
  2. For each requirement in doc A:
     a. Embed it (Titan V2)
     b. Search doc B's index for semantically similar chunks
     c. If similarity > 0.85 AND values differ:
        → Flag as potential conflict
  3. For flagged conflicts:
     a. Send both chunks to Bedrock Claude with prompt:
        "Do these describe the same interface? If yes, are the values consistent?"
     b. Claude returns: {same_interface: bool, conflict: bool, explanation: str}
  4. Add "Conflicts" section to briefing
```

### Output Addition

```
6. CONFLICTS DETECTED
─────────────────────
⚠ POWER INTERFACE (HSI_SYS_015G p.7 vs IDSS_IDD_RevF p.23)
  Doc A: "Spectrometer heater power: 30W (TBR-UCB-110)"
  Doc B: "IDPU power budget for spectrometer: 25W allocated"
  Analysis: Values differ by 5W. Doc A has TBR (not yet resolved).
  Recommendation: Resolve TBR-UCB-110 to match IDPU budget.

⚠ DATA RATE (IDSS_IDD_RevF p.45 vs NDS_IDD_RevC p.12)
  Doc A: "Telemetry downlink: 2 Mbps"
  Doc B: "Ground station receive capability: 1.5 Mbps"
  Analysis: Ground station cannot support the specified data rate.
  Recommendation: Reduce telemetry rate or upgrade ground station.
```

### Digital vs Flattened Handling (Phase 3)

| Aspect | Digital PDF | Flattened PDF |
|--------|-------------|---------------|
| Requirement extraction | Regex + structure-based | Same regex on OCR text |
| Embedding quality | High (clean text) | Lower (OCR noise in embeddings) |
| Conflict confidence | "High confidence" | "Medium confidence (OCR source)" |
| LLM context | Exact source text | OCR text with possible errors |
| Handling | Standard pipeline | Add note: "Verify original PDF for exact values" |

### Conflict Types Detected

| Type | How Detected | Example |
|------|-------------|---------|
| Value mismatch | Same parameter, different numbers | 28V vs 32V |
| Unit mismatch | Same parameter, different units | MHz vs GHz |
| Unresolved dependency | Doc A references TBD, Doc B has a value | TBD vs 25W |
| Protocol mismatch | Same interface, different protocols | RS-422 vs RS-485 |
| Connector mismatch | Same physical interface, different parts | MDM-37 vs MDM-25 |

---

## Phase 4: N-Document Scaling + Interface Graph

### Scope
Handle 10+ documents with visual interface topology.

### Services Used

| Service | Purpose | Cost |
|---------|---------|------|
| All Phase 1-3 services | Scaled to N documents | Linear scaling |
| OpenSearch (Docker) | Cross-document search at scale | Free (local) |
| Bedrock LLM (AWS) | Subsystem extraction from titles | ~$0.01/doc |
| Frontend visualization | D3.js or similar for graph rendering | Free |

### Data Flow

```
User selects N documents → POST /briefing/generate { documents: [...] }
  → Backend:
    1. For each document: load IR, extract TBDs, extract metadata
    2. Build interface graph:
       a. Extract subsystem names from document titles/sections
          (Bedrock prompt: "What two systems does this ICD connect?")
       b. Create nodes (subsystems) and edges (ICDs)
    3. For each edge (document):
       a. Compute maturity score
       b. Count open TBDs
       c. Detect conflicts with adjacent edges
    4. Produce:
       a. Graph data (JSON: nodes + edges with metadata)
       b. Tabular briefing (same as Phase 1-3, scaled)
       c. Critical path analysis (which interfaces block program milestones)
```

### Output Addition

```
7. INTERFACE TOPOLOGY
─────────────────────

    [Spacecraft Bus] ──── HSI_SYS_015G (3 TBDs) ──── [Spectrometer]
         │                                                  │
         │── IDSS_IDD_RevF (12 TBDs) ── [IDPU] ───────────┘
         │
         │── NDS_IDD_RevC (5 TBDs) ──── [Ground Station]

Critical Path: Spacecraft → IDPU → Spectrometer (15 TBDs total)
Highest Risk: IDSS_IDD_RevF (12 open items, 3 high-priority)

8. PROGRAM READINESS
────────────────────
Overall interface maturity: 67%
Interfaces ready for CDR: 4/7
Blocking items: 8 high-priority TBDs across 3 documents
Estimated resolution timeline: 6 weeks (based on owner assignments)
```

### Digital vs Flattened Handling (Phase 4)

| Aspect | Digital PDF | Flattened PDF |
|--------|-------------|---------------|
| Subsystem extraction | Title/heading parsing | Bedrock vision on title page |
| Graph confidence | High | Medium (may need user confirmation) |
| UI treatment | Normal node | Node with "OCR" badge |
| Conflict detection | Standard | Standard (same IR schema) |

---

## API Design (All Phases)

```
# Phase 1
POST /briefing/generate
  Body: { "documents": ["HSI_SYS_015G", "IDSS_IDD_RevF"] }
  Returns: { "briefing_id": "...", "summary": {...}, "download_url": "..." }

GET /briefing/{briefing_id}
  Returns: Full briefing JSON (for in-app rendering)

GET /briefing/{briefing_id}/download
  Returns: PDF file

# Phase 2 (extension)
POST /briefing/generate
  Body: { "documents": [...], "include_revision_diff": true }

# Phase 3 (extension)
POST /briefing/generate
  Body: { "documents": [...], "detect_conflicts": true }
  Note: This triggers AWS Bedrock calls (costs money)

# Phase 4 (extension)
GET /briefing/{briefing_id}/graph
  Returns: { "nodes": [...], "edges": [...] } for frontend visualization
```

---

## Frontend Design

### Briefing Panel (new tab in the app)

```
┌─────────────────────────────────────────┐
│ [Briefing] tab                          │
├─────────────────────────────────────────┤
│ Select Documents:                       │
│ ┌─────────────────────────────────────┐ │
│ │ ☑ HSI_SYS_015G.pdf                 │ │
│ │ ☑ IDSS_IDD_RevF.pdf                │ │
│ │ ☐ NDS_IDD_RevC.pdf                 │ │
│ │ ☐ 20150010976.pdf                   │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ Options:                                │
│ ☑ Include revision comparison           │
│ ☐ Detect conflicts (uses AWS — ~$0.30) │
│                                         │
│ [Generate Briefing]                     │
│                                         │
│ ─── Briefing Preview ─────────────────  │
│ Summary: 2 documents, 15 TBDs, ...     │
│ [Download PDF] [View Full Report]       │
└─────────────────────────────────────────┘
```

---

## Cost Model

| Phase | AWS Services | Cost per Briefing (2 docs) | Cost per Briefing (10 docs) |
|-------|-------------|---------------------------|----------------------------|
| 1 | None | $0.00 | $0.00 |
| 2 | None | $0.00 | $0.00 |
| 3 | Bedrock Titan (embeddings) + Claude (analysis) | $0.10-0.30 | $0.50-2.00 |
| 4 | Bedrock Claude (subsystem extraction) | $0.05-0.10 | $0.20-0.50 |

Phase 1+2 are completely free (local processing only).
Phase 3+4 require AWS credentials and incur per-use costs.

---

## Effort Estimate

| Phase | Scope | New Code | Effort |
|-------|-------|----------|--------|
| 1 | Two-doc briefing (summary, TBDs, cross-refs, PDF output) | ~800 lines | 2-3 days |
| 2 | Revision comparison (uses existing version_diff) | ~300 lines | 1-2 days |
| 3 | Conflict detection (RAG + Bedrock LLM analysis) | ~600 lines | 3-5 days |
| 4 | N-doc scaling + graph visualization + readiness scoring | ~500 lines | 2-3 days |

**Phase 1 MVP total: 2-3 days.** Gets you a working two-document briefing
with TBD aggregation, cross-references, and a downloadable PDF.

---

## Success Criteria

### Phase 1 (Minimum)
- [x] User selects 2 documents from loaded set
- [x] Briefing generates in < 10 seconds
- [x] Shows document metadata (rev, pages, TBD count)
- [x] Lists all TBDs/TBRs with page references and context
- [x] Identifies cross-references between the two documents
- [x] Computes maturity score per section
- [x] Downloadable as PDF
- [x] Works for both digital and OCR-ingested documents

### Phase 2
- [x] Shows what changed since previous revision
- [x] Counts TBDs resolved vs introduced
- [x] Identifies new/modified/deleted sections

### Phase 3
- [x] Detects value conflicts across documents
- [x] Provides explanation and recommendation for each conflict
- [x] Estimates cost before running (user confirms)

### Phase 4
- [x] Handles 10+ documents
- [x] Visual interface topology graph
- [x] Critical path identification
- [x] Program readiness percentage


---

## Differential Briefing Walkthrough Panel

### Problem

A user lands in the app with a family of ICD documents (e.g., IDSS IDD Rev D,
Rev E, Rev F). They need to understand what changed between revisions without
reading 400 pages. They also should not be hit with a $5 AI bill or a 30-second
wait for a monolithic comparison.

The briefing must be:
- Presented one digestible piece at a time (not a wall of text)
- Ordered logically (document by document, section by section)
- Cost-controlled (process incrementally, not all at once)
- Token-safe (never send more than a section to the LLM at a time)

### User Experience: Walkthrough Panel

A new panel tab (or sub-panel within the existing Diff tab) that walks the user
through the family in order, one section at a time.

```
┌─────────────────────────────────────────────────────┐
│ [Walkthrough] tab                                   │
├─────────────────────────────────────────────────────┤
│ ICD Family: IDSS IDD                                │
│ Revisions: D (2017) → E (2020) → F (2022)         │
│                                                     │
│ ┌─── Progress ─────────────────────────────────┐   │
│ │ Section 1 ✓  Section 2 ✓  Section 3 ●  ...  │   │
│ └──────────────────────────────────────────────┘   │
│                                                     │
│ SECTION 3: Mechanical Interface                     │
│ ─────────────────────────────────────────────────  │
│                                                     │
│ Rev D → Rev E:                                      │
│   ● 2 paragraphs modified (requirements tightened) │
│   ● 1 TBD resolved (bolt torque: 25 ft-lb)        │
│   ● 1 figure added (mounting diagram)              │
│                                                     │
│ Rev E → Rev F:                                      │
│   ● Section restructured (split into 3.1, 3.2)    │
│   ● 0 TBDs changed                                 │
│   ● Dimensional tolerance updated (±0.5mm → ±0.3mm)│
│                                                     │
│ [View Full Diff]  [AI Summarize ($0.02)]           │
│                                                     │
│ ◀ Previous Section          Next Section ▶         │
└─────────────────────────────────────────────────────┘
```

### Key Design Principles

**1. Section-by-section pagination**

Never show the whole document diff at once. Present one section at a time.
The user advances with Previous/Next buttons or clicks a section in the
progress bar. Sections map to the ICD's own heading structure (1., 2., 3.,
etc.).

**2. Incremental cost control**

- The initial walkthrough is FREE (local text diff only, no LLM)
- Each section shows: paragraphs modified, TBDs changed, figures added
- The user can optionally click "AI Summarize" per section (costs ~$0.01-0.03)
- Cost shown BEFORE the click, not after
- Running total displayed: "Session AI cost: $0.07"

**3. Token budget per section**

When the user clicks "AI Summarize":
- Only that section's old and new text are sent to the LLM
- Typical section: 200-800 words = 300-1200 tokens input
- Response: 50-150 words = 75-225 tokens output
- Cost per section: ~$0.01-0.03 (Claude Sonnet pricing)
- Never exceed 4000 tokens input (truncate with "[...section continues]")

**4. Document family ordering**

The walkthrough presents revisions in chronological order:
- First pass: Rev D → Rev E (what changed in the first update)
- Second pass: Rev E → Rev F (what changed in the second update)
- Summary view: Rev D → Rev F (net changes across the full span)

User can toggle between "step by step" and "net change" views.

### Data Flow (per section)

```
User clicks "Next Section"
  → Frontend requests: GET /briefing/walkthrough/{family_id}/section/{n}
  → Backend (FREE, local):
    1. Load both revisions' IR for this section
    2. Text diff (difflib) — count added/removed/modified paragraphs
    3. TBD comparison — which TBDs appeared/resolved in this section
    4. Return structured summary (no LLM)
  → Frontend shows the structured summary

User clicks "AI Summarize" (COSTS MONEY)
  → Frontend shows cost estimate first: "This will cost ~$0.02. Proceed?"
  → User confirms
  → POST /briefing/walkthrough/{family_id}/section/{n}/summarize
  → Backend:
    1. Extract old section text + new section text
    2. Truncate each to 2000 tokens max
    3. Send to Bedrock Claude with prompt:
       "Compare these two versions of an ICD section.
        Summarize what changed in 2-3 sentences.
        Focus on: requirements changes, TBD resolutions, value changes."
    4. Return AI summary + actual cost
  → Frontend displays summary, updates running cost total
```

### Pagination Strategy

**Level 1: Document family** (top level)
- Show which documents are in the family and their revision order
- User selects which pair to compare (or "all sequential")

**Level 2: Section** (main navigation)
- Progress bar shows all sections with status:
  - ✓ No changes (skip automatically or show "unchanged")
  - ● Has changes (stop here, show details)
  - ○ Not yet reviewed
- "Skip unchanged" toggle to auto-advance past identical sections

**Level 3: Within a section** (detail view)
- Modified paragraphs shown as inline diff (red/green highlighting)
- TBD changes shown as a mini-table
- Figures/tables flagged as added/removed
- "AI Summarize" button for plain-English interpretation

### Cost Guardrails

| Guard | Mechanism |
|-------|-----------|
| No surprise charges | Cost shown BEFORE every AI call |
| Per-section budget | Max 4000 tokens input per summarize call |
| Session cap | Optional: "Stop AI calls after $X.XX" setting |
| Free first | All structural diff info is local (free) |
| Batch discount | "Summarize all changed sections" option with total cost shown upfront |

### API Endpoints

```
# Get family overview
GET /briefing/families
  Returns: list of detected document families with revision chains

# Get walkthrough structure for a family
GET /briefing/walkthrough/{family_id}
  Returns: { revisions: [...], sections: [...], change_summary_per_section }

# Get section-level diff (FREE)
GET /briefing/walkthrough/{family_id}/section/{section_idx}?rev_from=D&rev_to=E
  Returns: { paragraphs_modified, tbds_changed, figures_added, inline_diff }

# AI summarize a section (COSTS MONEY)
POST /briefing/walkthrough/{family_id}/section/{section_idx}/summarize
  Body: { rev_from: "D", rev_to: "E" }
  Returns: { summary: "...", cost_usd: 0.02, tokens_in: 800, tokens_out: 120 }
```

### Frontend Component Structure

```
frontend/src/components/
├── WalkthroughPanel.tsx        # Main panel with family selector + section nav
├── SectionDiffView.tsx         # Single section comparison (free structural diff)
├── AiSummarizeButton.tsx       # Cost-aware button with confirmation dialog
└── WalkthroughProgressBar.tsx  # Section progress indicator (✓ ● ○)
```

### Implementation Order

1. **Family detection** — reuse existing `version_diff.detect_families()`
2. **Section extraction** — parse headings from Document IR for each revision
3. **Section-level diff** — difflib comparison per section (free, local)
4. **Walkthrough API** — serve one section at a time with change metadata
5. **Frontend panel** — progress bar + section view + prev/next navigation
6. **AI summarize** — optional per-section Bedrock call with cost display
7. **Net change view** — compare first revision to last (skip intermediates)

### Effort

| Step | Effort |
|------|--------|
| Family detection + section extraction | 1 day (mostly exists) |
| Section diff API | 1 day |
| Frontend walkthrough panel | 2 days |
| AI summarize with cost controls | 1 day |
| Net change view | 0.5 day |
| **Total** | **5-6 days** |


---

## Model-Free Strategy (Running Lean)

### Principle

The entire briefing consolidation system runs without any AI model calls
by default. Every core capability uses local computation only. AI is an
optional enhancement layer that the user explicitly opts into (with cost
shown upfront).

### What Runs Free (No Model, No AWS)

| Capability | Method | Cost |
|-----------|--------|------|
| Section-level text diff | Python difflib | $0 |
| TBD/TBR tracking | Regex: `\b(TBD\|TBR\|TBC)\b` | $0 |
| Paragraph change counts | Line-by-line comparison | $0 |
| Cross-reference detection | String search in "References" sections | $0 |
| Maturity scoring | TBD_count / total_blocks | $0 |
| Section heading extraction | Font size + numbering patterns from IR | $0 |
| Document family detection | Filename stem matching | $0 |
| Value extraction | Regex: numbers + units (V, W, MHz, mm, etc.) | $0 |
| Value conflict detection | Same keyword + different number across docs | $0 |
| Walkthrough pagination | Section indexing from IR headings | $0 |
| Progress tracking | Local state (which sections reviewed) | $0 |
| PDF briefing generation | Jinja2 + WeasyPrint (local) | $0 |

### Model-Free Conflict Detection

Instead of using embeddings to find semantic matches, use structured extraction:

```python
# Step 1: Extract all spec values from both documents
specs_a = extract_specifications(doc_a_ir)
# Returns: [{"value": 30, "unit": "W", "context": "heater power", "page": 7}, ...]

# Step 2: Match by context keywords
for spec_a in specs_a:
    for spec_b in specs_b:
        if shared_keywords(spec_a.context, spec_b.context) >= 2:
            if spec_a.value != spec_b.value and spec_a.unit == spec_b.unit:
                flag_conflict(spec_a, spec_b)
```

Pattern for value extraction:
```
(\d+\.?\d*)\s*(V|W|A|mA|MHz|GHz|Mbps|kbps|mm|cm|m|kg|g|°C|K|psi|ft-lb|N|Nm)
```

This catches:
- "30W" vs "25W" (power mismatch)
- "28V" vs "32V" (voltage mismatch)
- "-30°C" vs "-25°C" (temperature limit mismatch)
- "1 Mbps" vs "2 Mbps" (data rate mismatch)

### What Costs Money (Optional, User-Initiated)

| Capability | When Used | Cost |
|-----------|-----------|------|
| AI section summary | User clicks "Summarize" per section | ~$0.02/section |
| Semantic conflict detection | User clicks "Deep scan for conflicts" | ~$0.10-0.50/pair |
| Natural language briefing | User clicks "Generate executive summary" | ~$0.05-0.10 |

### UI Indicators

The UI should clearly separate free and paid features:

```
Section 3: Mechanical Interface
───────────────────────────────
Changes detected: 2 modified, 1 TBD resolved     ← FREE (always shown)
Value change: tolerance ±0.5mm → ±0.3mm          ← FREE (regex extraction)

[AI Summarize — $0.02]                            ← PAID (user choice)
```

### Cost Display

Always visible in the panel footer:
```
Session cost: $0.00  |  All results shown are from local analysis (no AI charges)
```

Changes to:
```
Session cost: $0.07  |  3 AI summaries generated
```

Only after the user explicitly requests AI features.


---

## Hybrid Analysis Strategy (Free First, AI When Needed)

### Two-Tier Approach

**Tier 1 (Always On, Free):** Structural and numerical analysis runs automatically
on every comparison. No user action required, no cost.

**Tier 2 (On Demand, Paid):** Semantic analysis runs only when the user asks for
deeper insight. Cost shown before execution, user confirms.

### When Each Tier Fires

```
Document pair loaded for comparison
│
├── Tier 1: Automatic (FREE)
│   ├── Text diff (what paragraphs changed)
│   ├── Value extraction (30W, 28V, -30°C, 1 Mbps)
│   ├── Value-to-value comparison (same keyword, different number)
│   ├── TBD status changes (opened, resolved, modified)
│   ├── Section structure changes (added, removed, reordered)
│   └── Cross-reference matching (doc A mentions doc B by name)
│
│   Results shown immediately. User sees:
│   "3 value conflicts found, 7 TBDs resolved, 2 sections restructured"
│
└── Tier 2: User-Initiated (PAID)
    │
    ├── "Why did this change?" — User clicks on a specific modified section
    │   → Sends old + new section text to Claude
    │   → Returns: "The thermal margin was reduced from 10°C to 5°C,
    │     likely due to the updated heater power budget in section 4.2"
    │   → Cost: ~$0.02
    │
    ├── "Are these actually the same interface?" — User sees a flagged
    │   value conflict but isn't sure if the two specs refer to the same thing
    │   → Sends both contexts to Claude
    │   → Returns: "Yes, both refer to the S/C-to-instrument power bus.
    │     Doc A specifies 30W demand, Doc B allocates only 25W."
    │   → Cost: ~$0.01
    │
    └── "Summarize all changes" — User wants an executive paragraph
        → Sends section headings + change counts (not full text) to Claude
        → Returns: "Rev F reduced the document from 142 to 70 pages by
          consolidating the mechanical and thermal sections. 7 TBDs
          were resolved. The docking ring diameter tolerance was tightened."
        → Cost: ~$0.03
```

### What Tier 1 Catches Without AI

| Pattern | Example | Detection Method |
|---------|---------|-----------------|
| Exact value change | 30W → 25W | Regex + unit matching |
| Tolerance tightening | ±0.5mm → ±0.3mm | Regex for ± patterns |
| Limit change | -30°C → -25°C | Regex for negative numbers + units |
| New requirement added | Paragraph appears only in new rev | difflib |
| Requirement removed | Paragraph missing from new rev | difflib |
| TBD resolved | "TBD" in old, specific value in new | Regex + position matching |
| TBD introduced | No TBD in old, "TBD" in new | Regex |
| Section renumbered | "3.2" became "4.1" | Heading pattern tracking |
| Document reference added | New entry in "Applicable Documents" | Section text diff |
| Connector pin change | "Pin 7: 28V" → "Pin 7: 32V" | Table cell comparison |

### What Tier 2 Adds (Semantic Understanding)

| Question | Why AI is Needed | Example |
|----------|-----------------|---------|
| "Are these the same interface?" | Synonyms, rewording | "power bus" vs "electrical supply rail" |
| "Why did this change?" | Reasoning, context | Connects a tolerance change to a test failure |
| "What's the impact?" | Cross-section logic | A power change in section 3 affects thermal in section 5 |
| "Is this consistent?" | Deep reading | Two sections say conflicting things in the same revision |
| "Executive summary" | Natural language generation | Turn 20 change items into 3 sentences for a PM |

### UI Pattern: Progressive Disclosure

```
┌─────────────────────────────────────────────────────────┐
│ SECTION 4: Electrical Interface                         │
│                                                         │
│ ⚡ VALUE CHANGES (found automatically):                 │
│   ● Bus voltage: 28V → 32V                ← Tier 1    │
│   ● Power allocation: 30W → 25W           ← Tier 1    │
│   ● Pin 12 reassigned: GND → NC           ← Tier 1    │
│                                                         │
│ 📝 TEXT CHANGES:                                        │
│   ● 3 paragraphs modified                 ← Tier 1    │
│   ● 1 paragraph added (grounding req.)    ← Tier 1    │
│                                                         │
│ ✓ TBDs: 1 resolved (connector type: MDM-37)← Tier 1   │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│ Want deeper analysis?                                   │
│ [Explain these changes — $0.02]            ← Tier 2    │
│ [Check for cross-section impacts — $0.03]  ← Tier 2    │
└─────────────────────────────────────────────────────────┘
```

The user gets real, useful information immediately (value conflicts, TBD
resolutions, paragraph changes) without spending anything. AI fills the gap
only when human-like reasoning is needed to interpret WHY something changed
or whether two differently-worded specs actually conflict.


---

## Analysis Mode Toggle (Standard / Advanced)

### UI Control

A radio button pair at the top of the Walkthrough and Briefing panels:

```
┌──────────────────────────────────────────────────┐
│ Analysis Mode:                                   │
│ ○ Standard (structural comparison only)          │
│ ● Advanced (enables AI-assisted insight)         │
│   Model: [cohere-en-paragraph ▾]                 │
│   Session cost so far: $0.04                     │
└──────────────────────────────────────────────────┘
```

### Behavior

**Standard mode (default):**
- All Tier 1 results shown (diffs, value conflicts, TBD tracking)
- AI buttons are hidden throughout the panel
- Zero cost, zero network calls to Bedrock
- No model dropdown shown (irrelevant in this mode)
- Footer shows: "Standard mode: all analysis is local, no AI charges"

**Advanced mode (user opts in):**
- Same Tier 1 results shown (unchanged)
- AI action buttons appear next to each section/conflict:
  - "Explain this change ($0.02)"
  - "Check cross-section impact ($0.03)"
  - "Generate executive summary ($0.05)"
- Model dropdown appears (user picks which model to use for all AI calls)
- Running cost counter visible at all times
- Footer shows: "Advanced mode: AI features enabled. Cost: $0.04"

### Model Dropdown (Advanced mode only)

When the user selects Advanced, a model selector appears:

```
Model: [────────────────────────────────▾]
        cohere-en-paragraph — Best for synonyms and paraphrasing
        titan-v2-sliding — Best balance of quality and cost
        titan-v2-paragraph — Good for section-level context
```

The selected model is used for ALL AI calls in the session. The user
picks once, not per-question. This keeps the UI simple and avoids
confusion about which model answered which question.

### State Persistence

- Mode choice stored in browser localStorage
- Defaults to Standard on first visit
- If the user previously selected Advanced, show a reminder on load:
  "Advanced mode is active. AI calls will be charged to your AWS account."

### Implementation

```typescript
// State in the Walkthrough/Briefing panel
const [analysisMode, setAnalysisMode] = useState<"standard" | "advanced">(
  localStorage.getItem("analysisMode") || "standard"
);
const [selectedModel, setSelectedModel] = useState(
  localStorage.getItem("analysisModel") || "titan-v2-sliding"
);
const [sessionCost, setSessionCost] = useState(0);

// Save to localStorage on change
useEffect(() => {
  localStorage.setItem("analysisMode", analysisMode);
}, [analysisMode]);
```

### Visual Treatment

Standard mode: clean, minimal. Just the data.

Advanced mode: AI buttons rendered with a subtle accent border and a
cost badge. Makes it visually clear which elements cost money:

```
┌─ AI ──────────────────────────────────────────┐
│ Explain these changes                  $0.02  │
└───────────────────────────────────────────────┘
```

Buttons are styled differently from the free structural elements so
the user always knows the boundary between "included" and "costs extra."


---

## Panel Design: "Revision Compare" Tab

### Panel Name

**Revision Compare** (tab label in the right panel alongside Editor, Search, TBD, etc.)

### Panel Layout (top to bottom)

```
┌─────────────────────────────────────────────────────┐
│ [Revision Compare] tab                              │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Compare two revisions of a document family to see   │
│ what changed: value updates, resolved TBDs, added   │
│ or removed sections, and specification conflicts.   │
│ Results are shown section by section.               │
│                                                     │
│ ─── Analysis Mode ────────────────────────────────  │
│ ○ Standard (structural comparison only)             │
│ ● Advanced (AI-assisted insight)                    │
│   Model: [cohere-en-paragraph ▾]                    │
│   Session cost: $0.00                               │
│                                                     │
│ ─── Select Revisions ────────────────────────────── │
│ From: [IDSS_IDD_RevD (2017) ▾]                     │
│ To:   [IDSS_IDD_RevF (2022) ▾]                     │
│                                                     │
│ [Compare]                                           │
│                                                     │
│ ─── Results ──────────────────────────────────────  │
│ (section-by-section walkthrough appears here)       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Document Selection Logic (ordering enforcement)

The two dropdowns ("From" and "To") only allow forward-in-time selection.
The user cannot compare a newer revision against an older one.

**How ordering works:**

1. The system detects the document family from all uploaded/indexed documents
   (using `version_diff.detect_families()` which groups by filename stem)

2. Within a family, revisions are ordered by their revision letter/number:
   ```
   A < B < C < D < E < F < G
   ```
   For documents without a clear revision letter (like date-based), order by
   file modification date or page count progression.

3. **"From" dropdown:** Shows all available revisions in the family.
   When the user selects one, the "To" dropdown updates to show only
   revisions that come AFTER the selected "From" revision.

4. **"To" dropdown:** Filtered. Only shows revisions newer than "From."
   If the user picks "Rev D" in From, the To dropdown shows: Rev E, Rev F, Rev G.
   It cannot show Rev A or Rev D (same or earlier).

5. If only two revisions exist in the family, both dropdowns auto-populate
   and the Compare button is immediately available.

**Implementation:**

```typescript
const familyRevisions = ["RevA", "RevD", "RevE", "RevF", "RevG"];
// Ordered by revision (parsed from filename or document metadata)

const [fromRev, setFromRev] = useState("");
const [toRev, setToRev] = useState("");

// "To" options are only those that come after "From" in the ordered list
const toOptions = familyRevisions.filter(
  (rev) => familyRevisions.indexOf(rev) > familyRevisions.indexOf(fromRev)
);

// When "From" changes, reset "To" if it's no longer valid
useEffect(() => {
  if (fromRev && toRev) {
    if (familyRevisions.indexOf(toRev) <= familyRevisions.indexOf(fromRev)) {
      setToRev("");  // Reset — can't go backwards
    }
  }
}, [fromRev]);
```

### Edge Cases

| Case | Behavior |
|------|----------|
| Only 1 document in family | Dropdowns disabled, message: "Upload another revision to compare" |
| Only 2 documents in family | Auto-selects both, Compare button ready |
| User changes "From" to after current "To" | "To" resets to empty |
| Non-sequential revisions (A vs F) | Allowed. Shows net changes across the gap |
| Different document families shown | Only the currently loaded family appears |

### How It Connects to Existing Features

- Document upload: uses existing "Upload & Index" flow
- Family detection: uses existing `version_diff.detect_families()`
- The "Version Diff" tab (existing) does a simpler whole-doc comparison.
  This new "Revision Compare" panel replaces it with the walkthrough experience.
  The old tab can be deprecated or kept as a "quick diff" shortcut.


---

## Results Display: Collapsed Accordion

### Pattern

After clicking Compare, results appear as a list of collapsed section rows.
Each row shows a one-line summary. The user expands only the sections they
care about. No forced ordering, no pagination buttons.

```
┌─────────────────────────────────────────────────────────────┐
│ Results: IDSS_IDD_RevD → IDSS_IDD_RevF                     │
│ 12 sections compared, 7 have changes                        │
│                                                             │
│ ▸ Section 1: Introduction ─── no changes                   │
│ ▸ Section 2: Applicable Documents ─── 2 refs added         │
│ ▾ Section 3: Mechanical Interface ─── 3 values, 1 TBD      │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Values changed:                                       │  │
│ │   ● Docking ring diameter: 800mm → 812mm             │  │
│ │   ● Seal compression: 1.2mm → 1.0mm                  │  │
│ │   ● Bolt torque: TBD → 25 ft-lb (resolved)           │  │
│ │                                                       │  │
│ │ Text changes:                                         │  │
│ │   ● 2 paragraphs modified                            │  │
│ │   ● 1 paragraph added (seal material requirement)    │  │
│ │                                                       │  │
│ │ [Explain changes — $0.02]  [Cross-section check — $0.03] │
│ └───────────────────────────────────────────────────────┘  │
│ ▸ Section 4: Electrical Interface ─── 1 value changed      │
│ ▸ Section 5: Data Interface ─── 5 values, 2 TBDs          │
│ ▸ Section 6: Thermal ─── section restructured              │
│ ▸ Section 7: Requirements ─── 4 paragraphs modified        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Behavior

- All sections listed on initial load (instant, no waiting)
- Sections with no changes show "no changes" in gray (collapsed, not expandable)
- Sections with changes show a short summary: "3 values, 1 TBD"
- Click a row to expand it (shows full detail: values, text diffs, AI buttons)
- Click again to collapse
- Multiple sections can be open at once
- Changed sections sorted to the top, unchanged pushed to bottom
- Optional toggle: "Hide unchanged sections"

### One-Line Summary Format

Each collapsed row shows the most important fact at a glance:

| Summary Text | What It Means |
|-------------|---------------|
| "no changes" | Section is identical between revisions |
| "3 values changed" | Numbers with units differ |
| "1 TBD resolved" | An open item was closed |
| "2 TBDs introduced" | New open items appeared |
| "section restructured" | Subsections added/removed/reordered |
| "4 paragraphs modified" | Text changed but no values/TBDs affected |
| "section removed" | Entire section deleted in newer revision |
| "new section" | Section did not exist in older revision |

### Expanded View Content

When a section is expanded, it shows (in order):

1. **Value changes** (if any) — bullet list of old → new with units
2. **TBD changes** (if any) — resolved, introduced, or modified
3. **Text changes** — paragraph counts (modified/added/removed)
4. **AI buttons** (Advanced mode only) — with cost shown

### Why This Works

- User scans the full list in 2 seconds (just reading one-liners)
- Digs into only what matters (click to expand)
- No forced ordering or "Next" button fatigue
- Works for 5 sections or 50 sections equally well
- Unchanged sections are visible but don't waste space
- Multiple sections open at once for cross-referencing


---

## Comparing Against Unsaved Edits (Working Copy as "Latest")

### Scenario

The user has Rev E and Rev F loaded. They open Rev F, make edits (fix a TBD,
update a value, add a table row) but have NOT saved yet. Now they want to
compare Rev E against their in-progress changes to see how the document is
shaping up relative to the previous revision.

### How It Works

The working copy (with unsaved edits) acts as a virtual "latest revision"
in the comparison. The user doesn't need to save or export first.

**From dropdown options:**
```
IDSS_IDD_RevD (2017)
IDSS_IDD_RevE (2020)
IDSS_IDD_RevF (2022)
IDSS_IDD_RevF — working copy (unsaved edits)  ← new option
```

The working copy appears as the last item in the To dropdown only. It
cannot appear in the From dropdown (you can only compare forward, and
the working copy is always the newest state).

### Data Source

When the user selects "working copy" as the To revision:

- The system reads from `_get_source_path()` (the .working_ file) instead
  of the original PDF for that document
- The Document IR in memory (with all edits applied) provides the text blocks
- TBD extraction runs against the IR (already has current text)
- Section extraction uses the IR headings (reflects any structural edits)

This is instant. No extra processing needed. The working copy and IR are
always in sync because every edit (table rebuild, cell edit, TOC change)
updates both simultaneously.

### What This Enables

- "I just resolved 3 TBDs in Rev F. How does it compare to Rev E now?"
- "I added a row to the thermal limits table. Does it conflict with Rev E's values?"
- "I'm drafting Rev G edits on top of Rev F. Show me the delta from Rev E."

### UI Indicator

When the working copy is selected, show a note:

```
To: IDSS_IDD_RevF — working copy (3 unsaved edits)
    ⚠ Comparing against your unsaved changes. Save first for a permanent record.
```

### No Additional Implementation Cost

This feature requires zero new backend logic. The comparison pipeline already
reads from Document IR (which has edits) and the working copy (which has table
rebuilds). We just need to add the "working copy" option to the To dropdown
and route the read to `_get_source_path()` instead of the original file path.
