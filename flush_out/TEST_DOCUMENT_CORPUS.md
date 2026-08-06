# Test Document Corpus — ICD Revision Sets

## Purpose

Define the document sets needed to test the briefing consolidation feature
at increasing levels of complexity.

## Reality of Public ICD Availability

Most real ICD programs don't publish every revision publicly. What's available:
- NASA NTRS (Technical Reports Server) has select revisions of formal documents
- The HESSI/RHESSI archive has the final revisions of each subsystem ICD
- The IDSS IDD is the best-documented progression: Rev A (2011) then D→E→F→G (2017-2026)

**Our primary test document: IDSS IDD (International Docking System Standard)**
- Consecutive chain: **D → E → F** (all publicly available, no gaps)
- Extended chain: **A → [gap] → D → E → F → G** (gaps acknowledged)

---

## Tier 1: Simplest Case (2 docs, 1 revision apart)

**Goal:** Two documents, one is the direct next revision of the other.

| Document | Revision | Pages | Source | Status |
|----------|----------|-------|--------|--------|
| IDSS_IDD_RevE.pdf | Rev E | 142 | In repo (`icds/digital/`) | Have it |
| IDSS_IDD_RevF.pdf | Rev F | 70 | In repo (`icds/digital/`) | Have it |

**What this tests:**
- Basic two-document briefing generation
- Single-step revision diff (E → F)
- TBD resolution tracking between revisions
- Cross-reference detection (same doc family)

**Notes:**
- Both are digital PDFs (native text)
- Flattened versions also available in `icds/flat/`
- Rev F is shorter (70 pages vs 142) — sections were reorganized

---

## Tier 2: Original + Next Two Revisions (3 docs, sequential)

**Goal:** First formal release plus the next two consecutive revisions.
No gaps — D, E, F are sequential under NASA configuration control.

| Document | Revision | Year | Pages | Source | Status |
|----------|----------|------|-------|--------|--------|
| IDSS_IDD_RevD.pdf | Rev D | 2017 | ~140 | [NTRS 20170001546](https://ntrs.nasa.gov/api/citations/20170001546/downloads/20170001546.pdf) | Need to download |
| IDSS_IDD_RevE.pdf | Rev E | ~2020 | 142 | In repo | Have it |
| IDSS_IDD_RevF.pdf | Rev F | 2022 | 70 | In repo | Have it |

**What this tests:**
- Three-point consecutive revision progression (no gaps)
- Multi-step diff (D→E and E→F)
- Tracking TBDs across 3 versions (introduced in D, resolved in F?)
- Section restructuring detection (F is significantly shorter than E)
- Rev D stated as "first version under NASA configuration control"

**Notes:**
- Rev D is the formal starting point of this document's controlled lifecycle
- All three are consecutive — no missing B/C problem
- Good for testing maturity progression over time

---

## Tier 3: Gapped Revisions (Pre-formal original + formal chain)

**Goal:** The earliest available version (pre-formal control) plus the formal chain.
Acknowledges that Revisions A-C were internal to the ISS partnership and are not
publicly available.

| Document | Revision | Year | Pages | Source | Status |
|----------|----------|------|-------|--------|--------|
| IDSS_IDD_RevA.pdf | Rev A | 2011 | ~50 | [law.resource.org](https://law.resource.org/pub/us/cfr/ibr/005/nasa.idss.2011.pdf) | Need to download |
| IDSS_IDD_RevD.pdf | Rev D | 2017 | ~140 | [NTRS 20170001546](https://ntrs.nasa.gov/api/citations/20170001546/downloads/20170001546.pdf) | Need to download |
| IDSS_IDD_RevE.pdf | Rev E | ~2020 | 142 | In repo | Have it |
| IDSS_IDD_RevF.pdf | Rev F | 2022 | 70 | In repo | Have it |

**What this tests:**
- Large structural changes between pre-formal and formal versions
- Document growth (50 pages → 142 pages → 70 pages)
- Handling known gaps (B, C not available — system should note this)
- Cross-era comparison (pre-NASA-control vs NASA-controlled)

**Caveat:** Revisions B and C existed but were managed internally by the
ISS Multilateral Coordination Board. They are not publicly available.
The system should handle this gracefully — show A and D as the available
points without assuming anything about B/C.

---

## Tier 4: Complete Available Chain (all public versions)

**Goal:** Every publicly available revision of the IDSS IDD.

| Document | Revision | Year | Source | Status |
|----------|----------|------|--------|--------|
| IDSS_IDD_RevA.pdf | Rev A | 2011 | law.resource.org | Need to download |
| IDSS_IDD_RevD.pdf | Rev D | 2017 | NTRS | Need to download |
| IDSS_IDD_RevE.pdf | Rev E | ~2020 | In repo | Have it |
| IDSS_IDD_RevF.pdf | Rev F | 2022 | In repo | Have it |
| IDSS_IDD_RevG.pdf | Rev G | 2026 | [nasa.gov](https://www.nasa.gov/wp-content/uploads/2026/01/m2m-idss-idd-rev-g-clean-1-23-2026.pdf) | Need to download |

**What this tests:**
- Full publicly-available document lifecycle (15 years, 5 versions)
- N-document scaling
- Long-term TBD tracking (opened in A, resolved in G?)
- Maturity curve visualization across the complete history
- Program-level briefing across all available history
- Graceful handling of known gaps (B, C missing)

**Reality check:** This is every version we can actually get. Revisions B
and C are not publicly available. The system should display:
`A (2011) → [B, C not available] → D (2017) → E (~2020) → F (2022) → G (2026)`

---

## Tier 5: Cross-Document (Different ICDs, Same Program)

**Goal:** Multiple different ICDs from the same spacecraft program.

| Document | Interface | Revision | Source | Status |
|----------|-----------|----------|--------|--------|
| HSI_SYS_015G.pdf | Spacecraft ↔ Spectrometer | Rev G | In repo | Have it |
| HSI_SYS_001H.pdf | Spacecraft ↔ IDPU | Rev H | [hesperia.gsfc.nasa.gov](https://hesperia.gsfc.nasa.gov/rhessi3/docs/official_docs/RHESSI_Documentation/Interface_Control_Documents_ICD/HSI_SYS_001H(S%EF%80%A2C%20to%20IDPU%20ICD).pdf) | Need to download |
| HSI_SYS_001I.pdf | Spacecraft ↔ IDPU | Rev I | [hesperia.gsfc.nasa.gov](https://hesperia.gsfc.nasa.gov/rhessi3/docs/official_docs/RHESSI_Documentation/Interface_Control_Documents_ICD/HSI_SYS_001I(IDPU%20ICD).pdf) | Need to download |

**What this tests:**
- Cross-document conflict detection (different interfaces, shared subsystems)
- Interface topology graph (Spacecraft → Spectrometer, Spacecraft → IDPU)
- Cross-reference detection (both reference the same IDPU)
- Program-level briefing across multiple interfaces

---

## Download Plan

### Priority Order

1. **IDSS_IDD_RevD.pdf** — Completes Tier 2 (most important for Phase 1 testing)
2. **IDSS_IDD_RevA.pdf** — Enables Tier 3 (original document)
3. **HSI_SYS_001H.pdf** — Enables Tier 5 cross-document testing
4. **HSI_SYS_001I.pdf** — Completes Tier 5
5. **IDSS_IDD_RevG.pdf** — Completes Tier 4 (latest revision)

### Storage

```
icds/
├── digital/
│   ├── IDSS_IDD_RevA.pdf      (Tier 3)
│   ├── IDSS_IDD_RevD.pdf      (Tier 2)
│   ├── IDSS_IDD_RevE.pdf      (existing)
│   ├── IDSS_IDD_RevF.pdf      (existing)
│   ├── IDSS_IDD_RevG.pdf      (Tier 4)
│   ├── HSI_SYS_001H.pdf       (Tier 5)
│   ├── HSI_SYS_001I.pdf       (Tier 5)
│   ├── HSI_SYS_015G.pdf       (existing)
│   └── ...
└── flat/
    └── (flattened versions created as needed)
```

---

## Testing Strategy Per Tier

| Tier | Briefing Test | Diff Test | Conflict Test | Graph Test |
|------|--------------|-----------|---------------|------------|
| 1 | 2-doc summary, TBD count | Single E→F diff | N/A | N/A |
| 2 | 3-doc summary, TBD progression | D→E, E→F diffs | Same-doc value changes | N/A |
| 3 | 4-doc summary, maturity curve | A→D (large gap) | Format change handling | N/A |
| 4 | 5-doc full history | All consecutive pairs | Full lifecycle | Timeline view |
| 5 | Cross-program briefing | N/A (different docs) | Cross-doc conflicts | Interface topology |

---

## Implementation Order

1. Start with **Tier 1** (already have both docs) — build and test Phase 1 briefing
2. Download Rev D → test **Tier 2** with revision diffs
3. Download Rev A → test **Tier 3** with large structural changes
4. Download HSI_SYS_001H/I → test **Tier 5** cross-document
5. Download Rev G → complete **Tier 4** full chain
