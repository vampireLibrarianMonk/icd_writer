# Exhaustive Embedding Model Benchmark Results

**Run Date:** 2026-07-27
**Eval ID:** 20260727_211401
**Duration:** 416 seconds (~7 minutes)
**Total Cost:** ~$0.22 (indexing + evaluation)

---

## Test Parameters

| Parameter | Value |
|-----------|-------|
| Queries | 251 (adversarially reviewed, 3 independent passes) |
| Documents | 7 NASA ICDs (566 pages total, 7,593 chunks) |
| Embedding Models | 3 (Titan V2, Cohere English v3, Cohere Embed v4) |
| Chunking Strategies | 4 (paragraph, section, sliding window, fixed words) |
| Retrieval Modes | 4 (keyword-only, vector-only, hybrid boost, hybrid RRF) |
| Total Configurations | 20 (4×4 + Cohere v4 paragraph×3 modes) |
| K (results evaluated) | 10 |
| Statistical Confidence | ±4.4% (95% CI) — detects >9% differences |

---

## Documents Indexed

| Document | Pages | Chunks (paragraph) | Description |
|----------|-------|-------|-------------|
| ICESat-2 ATL03 | 188 | 3,340 | Algorithm basis doc (photon science) |
| IDSS IDD Rev E | 142 | 1,870 | Docking standard (older revision) |
| NDS IDD Rev C | 108 | 1,295 | NASA Docking System interface |
| IDSS IDD Rev F | 70 | 678 | Docking standard (current revision) |
| LVC ICD | 35 | 260 | Flight simulation messages |
| TSAFE | 15 | 86 | Air traffic conflict detection |
| HSI ICD | 8 | 64 | Spectrometer interface |

---

## Final Rankings

| Rank | Configuration | Recall@10 | MRR | Hit Rate | Latency (p50) |
|------|--------------|-----------|-----|----------|---------------|
| **1** | **Titan V2 + Sliding Window + Hybrid** | **78.9%** | **0.844** | **92.4%** | 91ms |
| 2 | Titan V2 + Sliding Window + Keyword Only | 78.8% | 0.836 | 92.4% | 9ms |
| 3 | Titan V2 + Sliding Window + RRF | 78.6% | 0.830 | 92.4% | 130ms |
| 4 | Titan V2 + Section + Keyword Only | 76.9% | 0.793 | 91.2% | 9ms |
| 5 | Titan V2 + Section + Hybrid | 76.5% | 0.798 | 90.8% | 94ms |
| 6 | Titan V2 + Section + RRF | 76.3% | 0.807 | 90.4% | 134ms |
| 7 | Titan V2 + Sliding Window + Vector Only | 73.9% | 0.817 | 90.4% | 91ms |
| 8 | Titan V2 + Section + Vector Only | 72.2% | 0.798 | 90.8% | 92ms |
| 9 | Cohere English v3 + Paragraph + RRF | 71.4% | 0.748 | 88.0% | 140ms |
| 10 | Cohere Embed v4 + Paragraph + RRF | 69.3% | 0.734 | 86.5% | ~130ms |
| 11 | Cohere English v3 + Paragraph + Vector Only | 69.4% | 0.785 | 87.6% | 122ms |
| 12 | Cohere Embed v4 + Paragraph + Vector Only | 67.4% | 0.726 | 86.5% | ~90ms |
| 13 | Titan V2 + Paragraph + RRF | 66.9% | 0.742 | 84.5% | 132ms |
| 14 | Titan V2 + Paragraph + Vector Only | 65.7% | 0.741 | 84.1% | 94ms |
| 15 | Titan V2 + Paragraph + Hybrid | 65.2% | 0.705 | 84.1% | 95ms |
| 16 | Cohere English v3 + Paragraph + Hybrid | 65.1% | 0.700 | 84.9% | 128ms |
| 17 | Titan V2 + Paragraph + Keyword Only | 63.5% | 0.689 | 83.3% | 10ms |
| 18 | Cohere English v3 + Paragraph + Keyword Only | 63.5% | 0.689 | 83.3% | 6ms |
| 19 | Cohere Embed v4 + Paragraph + Keyword Only | 63.5% | 0.689 | 83.3% | ~6ms |

---

## Key Findings

### 1. Chunking Strategy is the #1 Factor

| Strategy | Best Recall | Worst Recall | Avg |
|----------|-------------|--------------|-----|
| **Sliding Window** | 78.9% | 73.9% | 77.6% |
| Section | 76.9% | 72.2% | 75.5% |
| Paragraph | 71.4% | 63.5% | 66.3% |

**Conclusion:** Sliding window's overlapping context captures cross-sentence relationships that paragraph boundaries break. This is a 12-15% improvement over paragraph chunking — well above our confidence threshold.

### 2. Keyword Search is Surprisingly Effective for ICDs

| Mode | Best Config Recall | Latency |
|------|-------------------|---------|
| Hybrid | 78.9% | 91ms |
| Keyword Only | 78.8% | 9ms |
| RRF | 78.6% | 130ms |
| Vector Only | 73.9% | 91ms |

**Conclusion:** BM25 keyword matching (78.8%) matches hybrid search (78.9%) within noise. ICDs use precise terminology — when a user searches "MsgFlightState 5310", exact term matching is as good as semantic embedding. Vector-only search is 5% worse because it loses exact-match precision.

**Cost implication:** Keyword-only requires NO embedding API call per query ($0/query vs $0.00001/query). For high-volume usage, this is significant.

### 3. Cohere v4 (1536d) Does NOT Beat Titan V2 (1024d)

| Model | Best Recall | Dimensions | Cost |
|-------|-------------|-----------|------|
| Titan V2 | 78.9% | 1024 | $0.0001/1K tokens |
| Cohere English v3 | 71.4% | 1024 | $0.0001/1K tokens |
| Cohere Embed v4 | 69.3% | 1536 | $0.0001/1K tokens |

**Conclusion:** The 78.9% vs 69.3% gap (9.6%) exceeds our 9% detection threshold. Titan V2 is statistically significantly better than Cohere v4 on this ICD corpus. More dimensions (1536 vs 1024) does not help — likely because ICD text is domain-specific and Titan V2's training data includes more technical/engineering content.

### 4. Section Chunking is the #2 Choice

Section chunking (76-77%) offers a good balance between paragraph (63-67%) and sliding window (78-79%). It produces fewer chunks (274 vs 1,295 per large document) which means lower indexing cost, while capturing full section context.

**Use case:** If indexing cost matters more than the last 2% recall, section chunking is the cost-optimized choice.

---

## Recommendations

### Primary: Keep Current Configuration
- **Model:** Amazon Titan Embed Text V2 (1024d)
- **Chunking:** Sliding Window (256 tokens, 64 token overlap)
- **Retrieval:** Hybrid (BM25 + kNN combined)
- **Recall:** 78.9%

### Cost-Optimized Alternative
- **Model:** Amazon Titan Embed Text V2 (1024d)
- **Chunking:** Sliding Window
- **Retrieval:** Keyword Only (BM25)
- **Recall:** 78.8% (functionally identical)
- **Benefit:** Zero per-query embedding cost, 10x lower latency (9ms vs 91ms)

### Do NOT Switch To
- Cohere v4 (9.6% worse recall, no benefit)
- Cohere English v3 (7.5% worse recall)
- Paragraph chunking (12-15% worse than sliding window)

---

## Comparison to Previous Benchmark

| Metric | Previous (3 docs, 13 queries) | Current (7 docs, 251 queries) |
|--------|------|---------|
| Best config | Titan V2 sliding + hybrid | Titan V2 sliding + hybrid ✅ |
| Best recall | 92.3% | 78.9% |
| Confidence | ±12.2% (low) | ±4.4% (high) |

The drop from 92.3% to 78.9% is expected — the larger corpus with more documents and harder queries (specific part numbers, cross-doc discrimination) is a more realistic benchmark. The previous 92.3% was inflated by a small, easy query set.

---

## Raw Data

Full per-query results: `tests/results/search_eval/eval_20260727_211401.json`
Previous run: `tests/results/search_eval/eval_20260727_143939.json`
Benchmark reports: `tests/results/search_eval/benchmark_*.json`
