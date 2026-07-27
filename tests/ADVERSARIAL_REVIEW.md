# Ground Truth Evaluation Set — Adversarial Review Record

**Date:** 2026-07-27
**Final Query Count:** 251
**Documents Covered:** 6
**Adversarial Reviews:** 3 independent passes

---

## Statistical Confidence

| Queries | Standard Error | 95% CI | Detectable Difference |
|---------|---------------|--------|----------------------|
| 33 (original) | ±6.2% | ±12.2% | >24% |
| 100 (series 1) | ±3.6% | ±7.0% | >14% |
| 171 (series 1+2) | ±2.7% | ±5.4% | >11% |
| **251 (final)** | **±2.3%** | **±4.4%** | **>9% (95% conf)** |

At 251 queries, we can reliably distinguish models that differ by 9%+ recall with 95% confidence, or 7%+ with 90% confidence.

---

## Review 1: Initial Set Validation (33 queries)

**Findings:**
- 3 weak queries with only 1 relevant text → fixed (added 2+ texts each)
- 7 queries with match texts <4 characters (TBD, kg, HCS, Btu, H&S) → fixed
- TBD category underrepresented → accepted (TBDs are rare by nature)
- No negative/trick queries → accepted for this benchmark scope

**Actions taken:** All identified issues fixed. Zero weak queries remaining.

---

## Review 2: Batch 2 Adversarial (75 queries → 71 after review)

**Critical issues found and resolved:**

| Issue | Query | Problem | Resolution |
|-------|-------|---------|-----------|
| 🔴 HALLUCINATED | batch2_lvc_005 | NED velocity components don't exist in LVC | REMOVED |
| 🔴 HALLUCINATED | batch2_ice_012 | "first-photon bias" not in ATL03 ATBD | REMOVED |
| 🔴 REDUNDANT | batch2_tsafe_001 | Duplicates existing tsafe-006 | REMOVED |
| 🔴 REDUNDANT | batch2_lvc_013 | 5th query targeting same MsgFlightState struct | REMOVED |
| 🟡 CROSS-DOC | batch2_idss_001,005,006 | Generic terms match both IDSS and NDS | Added "IDSS" discriminator |
| 🟡 CROSS-DOC | batch2_nds_009 | "power bus" matches HSI content | Added "NDS" discriminator |
| 🟡 GENERIC | batch2_lvc_006 | "coordinate" matches TSAFE | Changed to "decimal" |
| 🟡 GENERIC | batch2_hsi_007 | "power" and "level" too broad | Changed to "15W", "coldplate" |
| 🟡 UNVERIFIED | batch2_tsafe_007 | "short-term" may not be in doc | Changed to "minutes", "future" |
| 🟡 UNVERIFIED | batch2_tsafe_012 | "conformance" not verified | Changed to "conformance", "track", "monitor" |

**Systematic issues identified:**
1. Cross-document contamination between IDSS and NDS (share terminology: latch, seal, capture, hook)
2. Over-concentration on MsgFlightState struct (5+ queries targeting same content area)
3. Generic relevant_texts that match multiple documents

---

## Review 3: Batch 3 Rules (80 queries)

**Rules enforced at generation time (proactive, not reactive):**

1. ❌ NO generic single-word relevant_texts (power, time, field, data, system)
2. ✅ Multi-word phrases or document-specific terms required
3. ✅ ALL IDSS queries include "IDSS" in relevant_texts
4. ✅ ALL NDS queries include "NDS" or "NASA Docking" in relevant_texts
5. ❌ NO queries about unverified content
6. ✅ Each query has 2-3 relevant_texts, each 4+ characters
7. ✅ Even distribution (~13 per document)

**No issues found requiring removal** — rules prevented problems at generation time.

---

## Category Distribution

| Category | Count | % | Coverage |
|----------|-------|---|----------|
| architecture | 98 | 39% | System design, algorithms, components |
| requirements | 71 | 28% | Shall statements, specifications, limits |
| interface | 65 | 26% | Message formats, connectors, signals |
| metadata | 13 | 5% | Authors, revisions, dates, document control |
| tbd | 4 | 2% | Unresolved items |

**Assessment:** Architecture and requirements dominate (67% combined) which reflects actual ICD content distribution. Interface queries are well-represented for testing precise retrieval of specific values (message codes, part numbers). Metadata and TBD are lower but covered by dedicated queries that specifically test those retrieval paths.

---

## Document Distribution

| Document | Base | Expanded | Batch 2 | Batch 3 | Total |
|----------|------|----------|---------|---------|-------|
| LVC ICD (35pg) | 5 | 10 | 11 | 14 | 40 |
| HSI ICD (8pg) | 5 | 8 | 12 | 13 | 38 |
| TSAFE (15pg) | 3 | 7 | 11 | 13 | 34 |
| ICESat-2 (188pg) | 6 | 12 | 12 | 13 | 43 |
| IDSS IDD Rev F (70pg) | 7 | 12 | 13 | 13 | 45 |
| NDS IDD Rev C (108pg) | 7 | 12 | 12 | 14 | 45 |

**Assessment:** Well-balanced. No single document dominates. Slight bias toward larger documents (IDSS, NDS, ICESat-2) which is appropriate given their complexity.

---

## Known Limitations

1. **No negative queries** — all queries have answers in the corpus. Adding "unanswerable" queries would test the system's ability to say "I don't know" but would require different scoring logic.

2. **Correlated queries** — some query pairs target the same chunk (e.g., multiple queries about HSI heaters). These are not fully independent observations, which slightly inflates our effective sample size estimate.

3. **Substring matching limitations** — queries whose answers span multiple chunks (multi-hop reasoning) may score poorly even with correct retrieval of one chunk.

4. **Category imbalance** — TBD queries (4) are too few for category-level confidence. TBD retrieval results should be interpreted with wide error bars.

5. **No difficulty calibration** — we don't know a priori which queries are "easy" (keyword match) vs "hard" (semantic understanding). The benchmark treats all queries equally.

---

## Recommendations for Future Expansion

To reach 5% detection confidence:
- Expand to ~400 queries (need 150 more)
- Source from real user questions (RAG query log)
- Add cross-document queries (answer requires multiple docs)
- Add negative queries (unanswerable)
- Add paraphrase pairs (same question, different wording) to test semantic robustness
