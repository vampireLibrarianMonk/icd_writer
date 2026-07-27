# Phase 6 Requirements: Document Version Detection & Differential Analysis

**Document Version:** 1.0
**Date:** 2026-07-27
**Status:** Draft

---

## Problem Statement

ICD programs produce multiple versions of the same document over time. These versions may exist in different formats (digital PDF vs. flattened/scanned PDF), different revisions (Rev C vs. Rev G), or both. Today there is no mechanism to:

- Detect when two files in the corpus are versions of the same document
- Determine whether they have the same content or have diverged
- Produce a structured report of what changed between versions
- Track whether the "delivered baseline" (often flattened) matches the "working copy" (often digital)

This creates configuration management risk: engineers may work from a stale version without knowing a newer one exists, or a contractual baseline may silently differ from the working document.

## Users & Scenarios

| Persona | Scenario |
|---------|----------|
| Configuration Manager | "Do our delivered baselines match our working copies?" |
| Systems Engineer | "What changed between the Rev C I integrated against and the new Rev G?" |
| Program Manager | "Which requirements changed since our last design review?" |
| Quality Engineer | "Were any 'shall' statements modified between revisions without formal review?" |
| New Team Member | "What's different between these two versions someone gave me?" |

---

## Architecture

```
Document Corpus
    → Version Detection (name matching, metadata comparison)
    → Quick Health Check (page count, first-page similarity)
    → User Prompt: "Found another version. Analyze differences?"
    → Text Extraction (PyMuPDF for digital, OCR for flat)
    → Structured Diff (local, zero LLM cost)
    → LLM Summarization (ONLY the diff hunks, not full docs)
    → Differential Report (exportable: text, HTML, markdown)
    → Integration (TBD dashboard, search re-index, eval harness)
```

---

## Feature 1: Version Detection

### What It Does

Automatically identifies when two or more files in the corpus appear to be versions of the same document.

### Detection Logic

1. **Filename stem normalization** — strip common suffixes:
   - `_flat`, `_flattened` (format variant)
   - `_v1`, `_v2`, `_revA`, `_revG` (version markers)
   - `_draft`, `_final`, `_baseline` (status markers)
   - Trailing dates: `_20240315`
2. **If two files reduce to the same base stem** → candidate pair
3. **Quick validation** — at least one of:
   - Same page count (strong signal)
   - Title metadata matches
   - First-page text has >50% word overlap
4. **If validated** → confirmed document family

### When Detection Triggers

- User opens a document → check for related versions
- New document uploaded → check against existing corpus
- Manual command: `python3 -m src.cli version-check`
- API endpoint: `GET /documents/families`

### Output

```json
{
  "families": [
    {
      "base_name": "HSI_SYS_015G",
      "versions": [
        {"path": "icds/digital/HSI_SYS_015G.pdf", "type": "digital", "pages": 8, "date": "2025-01-12"},
        {"path": "icds/flat/HSI_SYS_015G_flattened.pdf", "type": "flattened", "pages": 8, "date": "2024-03-15"}
      ],
      "status": "content_differs",  // or "identical", "unknown"
      "page_count_match": true
    }
  ]
}
```

### Acceptance Criteria

1. Detection identifies all related documents in `icds/digital/` and `icds/flat/` by name matching.
2. Exact duplicates (SHA-256 match) are excluded — already handled by deduplication.
3. Detection runs in < 1 second for a corpus of 50 documents.
4. False positive rate < 5% (unrelated documents incorrectly grouped).
5. Results cached — re-detection only on corpus change.

---

## Feature 2: User Prompt & Workflow

### What It Does

When a version pair is detected, prompts the user with an actionable dialog rather than silently ignoring or confusing them.

### UI Behavior

**On document open** (if a related version exists):
```
┌─────────────────────────────────────────────────┐
│  📋 Version Detected                             │
│                                                  │
│  Another version of this document exists:        │
│                                                  │
│  Current: HSI_SYS_015G.pdf (digital, 8 pages)   │
│  Other:   HSI_SYS_015G_flattened.pdf (flat, 8p) │
│                                                  │
│  [ ] Generate differential analysis report       │
│                                                  │
│  [Analyze]  [Skip]  [Don't ask again for this]   │
└─────────────────────────────────────────────────┘
```

**In the Toolbar** (persistent access):
- A "Versions" button/badge when the current document has known versions
- Opens a panel showing all versions and their comparison status

### Acceptance Criteria

1. Prompt appears on document open if related version detected.
2. User can dismiss permanently per document family ("Don't ask again"). How can we undo this if needed, or should we even have this at all?
3. "Analyze" triggers the differential analysis pipeline.
4. "Skip" continues without analysis.
5. Version indicator visible in toolbar when versions exist.

---

## Feature 3: Differential Analysis Engine

### What It Does

Produces a structured diff between two document versions using progressive disclosure: summary first (free), details on demand (free), AI enhancement only when explicitly requested (cheap).

### Progressive Disclosure Model

**Level 1: Executive Summary (always free, instant)**
```
VERSION DIFFERENTIAL SUMMARY
HSI_SYS_015G: Rev F → Rev G

• 3 sections modified, 1 section added
• 2 requirement changes (shall statements) ⚠️
• 1 new TBR introduced (TBR-UCB-110)
• 4 editorial changes (wording/formatting)
• No deletions

Sections affected: §2.1, §3.2.1, §3.3, §4.0

[Show details for §2.1] [Show details for §3.2.1] [Show all]
```

**Level 2: Section Detail (on demand, free)**
```
§3.2.1 Spectrometer Heaters (p7)
Classification: TECHNICAL ⚠️

Old: "Heater power: 25W"
New: "Heater power: 30W (TBR-UCB-110)"

[Summarize with AI — est. $0.0001]
```

**Level 3: AI Summary (only when user clicks, per-hunk cost shown)**
```
Impact: Power increased by 20%. New TBR-UCB-110 means this value
is not yet confirmed. Affects power budget and thermal dissipation
calculations. Must be resolved before CDR.
```

### Cost Model

| Action | Cost | Trigger |
|--------|------|---------|
| Generate summary overview | $0 | Automatic on compare |
| Expand one section detail | $0 | User clicks section |
| AI-summarize one section | ~$0.00005 | User clicks "Summarize with AI" |
| AI-summarize all sections | ~$0.0003 | User clicks "Summarize all with AI" (shows cost first) |
| Export report (without AI) | $0 | Anytime |
| Export report (with AI summaries) | $0 | Only includes already-generated summaries |

The user is always in control. The LLM is never called without explicit user action with estimated cost displayed.

### Stage 1: Local Diff (Zero Cost, Always Available)

All of this runs without any API calls:

1. **Extract text from both versions**
   - Digital: PyMuPDF character-level extraction
   - Flattened: use existing OCR extraction if available, or report "OCR required"
2. **Align sections** — match headings between versions to establish correspondence
3. **Compute diff** — for each aligned section, produce:
   - Added lines
   - Removed lines
   - Modified lines (with old → new)
4. **Classify structurally** (local heuristics, no LLM):
   - Section added / removed / renamed
   - Page count changed
   - Table modified (row added/removed/changed)
   - Requirement text changed (lines containing shall/will/must)
5. **Generate executive summary** — counts and affected sections

### Stage 2: LLM Summarization (Budget-Controlled, User-Initiated)

Only the **diff hunks** go to the LLM — not the full documents. Only when the user explicitly requests it.

**Input to LLM** (per diff hunk, only when user clicks):
```
Section: §3.2.1 Spectrometer Heaters
Old text: "Heater power: 25W"
New text: "Heater power: 30W (TBR-UCB-110)"
Context: This is in a thermal interface requirements section.

Classify this change and explain its impact in 2-3 sentences.
```

**LLM output:**
```
Classification: TECHNICAL
Summary: Heater power increased from 25W to 30W, with value now flagged as TBR.
Impact: May affect power budget and thermal dissipation calculations.
Risk: Introduces new TBR (UCB-110) — resolution needed before CDR.
```

### LLM Budget Controls

**1. Size gate — check before sending:**
```
MAX_DIFF_TOKENS_FOR_BULK_LLM = 5000

If user clicks "Summarize all" and diff > 5000 tokens:
  "⚠️ Large differential (15,247 tokens). Options:
   [A] Summarize first 5,000 tokens (~$0.0003)
   [B] Summarize all (~$0.0015)
   [C] Cancel — use local report only (free)"
```

**2. Similarity gate — catch unrelated documents:**
```
If text overlap < 30%:
  "⚠️ These documents share less than 30% content.
   They may not be versions of the same document.
   [Proceed anyway] [Cancel]"
```

**3. Per-hunk cost display:**
Every "Summarize with AI" button shows estimated cost before the user clicks.

**4. Running cost tracker:**
```
Total AI cost this report: $0.0004 / $0.01 cap
[Adjust cap] [Stop AI summarization]
```

**5. Per-session and per-day caps (configurable):**
```
SESSION_LLM_CAP = $0.10
DAILY_LLM_CAP = $1.00
```
When exhausted: "AI budget reached. Local-only mode. [Reset cap]"

**6. Model tiering by diff size:**

| Diff size | Default model | Rationale |
|-----------|--------------|-----------|
| < 1K tokens | Nova Lite | Cheapest, good enough |
| 1K - 5K tokens | Nova Lite | Still cheap |
| 5K - 15K tokens | Nova Lite with chunking | Break into pieces |
| > 15K tokens | Local only (no LLM default) | Too expensive; user must override |

### Key Principle

**The report is always complete without the LLM.** The structure is:

```
For each change:
  ├── Section reference        ← always present (local)
  ├── Old text                 ← always present (local)
  ├── New text                 ← always present (local)
  ├── Change classification    ← local heuristic (shall/editorial/structural)
  └── Plain-English summary    ← LLM enhancement (optional, on-demand)
```

If the LLM is never invoked, you still get a fully usable report. The AI adds plain-English interpretation — it doesn't produce the data.

### Model Selection for Diff Summarization

Uses the existing model registry and eval apparatus:
- New ground-truth category: "diff_summarization"
- Test queries: known diffs with expected classification and summary
- Metrics: classification accuracy, summary completeness, cost
- Start with Nova Lite (cheapest), compare against Nova Pro and Claude Haiku
- Same deprecation/discovery pattern as embedding models

### Acceptance Criteria

1. Executive summary (Level 1) generates in < 2 seconds with zero cost.
2. Section detail (Level 2) expands instantly (data already computed).
3. AI summary (Level 3) only triggers on explicit user click with cost shown.
4. Local diff completes without LLM for any two documents in < 5 seconds.
5. Section alignment correctly matches >90% of sections between revisions.
6. LLM summarization only receives diff hunks, never full document text.
7. Per-hunk estimated cost displayed before user confirms.
8. Budget cap stops LLM calls gracefully — remaining changes shown as raw diff.
9. LLM failure falls back to raw structured diff (still complete report).
10. Diff detects requirement changes (shall/will/must) with >95% accuracy locally.
11. New TBD/TBR items discovered in newer version flagged explicitly (no LLM needed).
12. Similarity gate catches unrelated documents before wasting budget.
13. "Summarize all" shows total estimated cost and requires confirmation.

---

## Feature 4: Differential Report

### What It Does

Produces a formatted, exportable report of all differences ordered by section (ascending).

### Report Structure

```
DOCUMENT VERSION DIFFERENTIAL REPORT
=====================================
Document Family: HSI_SYS_015G
Version A (older): icds/flat/HSI_SYS_015G_flattened.pdf
  Type: Flattened | Pages: 8 | Date: 2024-03-15 | Rev: F
Version B (newer): icds/digital/HSI_SYS_015G.pdf
  Type: Digital | Pages: 8 | Date: 2025-01-12 | Rev: G

SUMMARY
- Sections modified: 3
- Sections added: 1
- Sections removed: 0
- Requirements changed: 2 (both 'shall' statements ⚠️)
- New TBD/TBR items: 1 (TBR-UCB-110)
- Editorial changes: 4

CHANGES (section ascending)

§2.1 Applicable Documents (p2)
  [EDITORIAL] Reference updated: "ABC-001 Rev A" → "ABC-001 Rev B"
  Risk: None — administrative update.

§3.2.1 Spectrometer Heaters (p7)
  [TECHNICAL ⚠️] Heater power changed: "25W" → "30W (TBR-UCB-110)"
  Impact: Power budget affected. New TBR introduced.
  Risk: TBR-UCB-110 must be resolved before CDR.

§3.3 Temperature Requirements (p7)
  [TECHNICAL ⚠️] Non-op cold limit: "-40°C" → "-60°C"
  Impact: Relaxes survival requirement. Spacecraft thermal model may need update.
  Risk: Interface partner must acknowledge changed constraint.

§4.0 Electrical Interface (p8)
  [ADDED] New content: "The IDPU will be the single-point electrical
  interface between the spacecraft and the instruments."
  Impact: Clarification — no requirement change.

NO DELETIONS DETECTED.

---
Generated: 2026-07-27 14:05:00 UTC
Model: amazon.nova-lite-v1:0 | Input: 1,847 tokens | Cost: $0.0003
```

### Export Formats

- **Markdown** (`.md`) — for version control, README inclusion
- **HTML** — for email distribution, browser viewing
- **Plain text** (`.txt`) — for maximum compatibility
- **JSON** — for programmatic consumption by other tools

### API Endpoint

```
POST /documents/diff?version_a=<path>&version_b=<path>&format=markdown&llm=true
```

### CLI Command

```bash
python3 -m src.cli version-diff icds/flat/HSI_SYS_015G_flattened.pdf icds/digital/HSI_SYS_015G.pdf --format markdown --output report.md
```

### Acceptance Criteria

1. Report includes all changes ordered by section number ascending.
2. Each change classified: EDITORIAL, TECHNICAL, STRUCTURAL, ADDED, REMOVED.
3. Requirement changes (shall/will/must) flagged with ⚠️.
4. New TBD/TBR items explicitly called out.
5. Export works in all 4 formats (md, html, txt, json).
6. Report includes generation metadata (date, model, cost).
7. Report is reproducible — same inputs produce same output.

---

## Feature 5: Integration with Existing Systems

### TBD Dashboard

- New TBD/TBR items discovered in diff → auto-added to dashboard
- Resolved TBDs (present in old, absent in new) → flagged as potentially resolved
- Changed TBD values → flagged as "value updated between versions"

### Search Index

- When a newer version is identified, offer to re-index with updated content
- Search results indicate which version the result comes from

### Eval Harness

- New ground-truth category: `diff_summarization`
- Test cases: known document pairs with expected diff output
- Metrics: classification accuracy, summary quality, cost

### Document Selector (UI)

- Grouped display: document families with version indicators
- Current version highlighted
- "Compare versions" action accessible from selector

---

## Non-Functional Requirements

- **Performance:** Version detection across 50 documents < 2 seconds. Local diff < 5 seconds. Full report (with LLM) < 15 seconds.
- **Cost:** Per-report LLM cost < $0.01. Budget cap configurable. Fallback to raw diff if budget exceeded.
- **Accuracy:** Section alignment >90%. Change classification >85%. No false "requirement changed" flags (precision > 95%).
- **Reversibility:** Report generation is read-only — never modifies either document.
- **Offline capability:** Local diff (Stage 1) works without internet/AWS. Only LLM summarization requires cloud access.

---

## Out of Scope (Phase 6)

- **Three-way merge** (common ancestor + two diverged versions)
- **Automatic reconciliation** (deciding which version is "correct")
- **Real-time change monitoring** (watching a directory for new versions)
- **Signature/approval tracking** (who approved which version)
- **PDF visual diff** (pixel-level image comparison between rendered pages)
- **Collaborative conflict resolution** (multiple users resolving differences)

---

## Dependencies

| Dependency | Risk | Mitigation |
|-----------|------|-----------|
| OCR pipeline (for flat versions) | OCR errors affect diff accuracy | Flag low-confidence OCR regions in report |
| LLM availability | Bedrock outage blocks summarization | Stage 1 (local diff) always works without LLM |
| Section heading detection | Misaligned sections = wrong diff | Use existing heading extraction + fuzzy matching |
| Document naming conventions | Non-standard names miss detection | Manual "link versions" command as fallback |
| Large documents | Huge diffs may exceed LLM context | Chunk diff hunks; summarize in batches; budget cap |

---

## Implementation Priority

| Step | Effort | Value | Order |
|------|--------|-------|-------|
| Version detection (name matching + page count) | 1 day | High — surfaces the problem | 1st |
| User prompt (UI dialog on open) | 0.5 day | High — actionable UX | 2nd |
| Local structured diff (no LLM) | 2-3 days | High — useful alone | 3rd |
| LLM summarization of diff hunks | 1-2 days | Medium — adds clarity | 4th |
| Report generation (4 formats) | 1 day | Medium — exportable | 5th |
| Integration (TBD dashboard, search, eval) | 1-2 days | Medium — connects systems | 6th |
| Model evaluation for diff task | 1 day | Low — optimization | 7th |

**Total estimated effort:** 8-11 days

---

## Relationship to Other Phases

| Phase | Relationship |
|-------|-------------|
| Phase 4 (Search) | Diff report uses search index for section alignment; new versions trigger re-index |
| Phase 4 (TBD Dashboard) | New/changed TBDs flow into dashboard |
| Phase 4 (Model Eval) | Diff summarization becomes a new eval category |
| Phase 5 (Reflow) | Reflow operates on the chosen "working" version; version detection helps identify which to edit |

---

## Open Questions

1. **Should the system auto-detect versions on startup or only on user action?**
   Recommendation: Auto-detect on document open; background scan on startup with non-intrusive notification.

2. **What if OCR hasn't been run on the flat version yet?**
   Recommendation: Report says "Full diff requires OCR. Run OCR pipeline?" with estimated cost. Partial report (metadata + page count) available immediately.

3. **How do we handle more than two versions of the same document?**
   Recommendation: Pairwise comparison, most recent vs. each older version. Report shows full version history with diffs between consecutive versions.

4. **Should diff reports be persisted or regenerated on demand?**
   Recommendation: Persist in `output/diff_reports/`. Regenerate only if source documents change.
