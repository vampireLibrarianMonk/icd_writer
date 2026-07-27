# Search Pipeline & Evaluation Harness

## The Problem

Embedding models get released and deprecated constantly. A search pipeline that's "good enough" today degrades tomorrow when:
- Your embedding model gets deprecated (like Claude Sonnet vision did during this project)
- A new model arrives that's 15% better for technical document retrieval
- Your chunking strategy doesn't fit a new document's structure
- Score boosting parameters drift as the corpus grows

## The Solution: Continuous Benchmarking

The search pipeline is built around an **evaluation harness** that scores every combination of:

| Dimension | Options |
|-----------|---------|
| Embedding model | Titan V2, Titan V1, Cohere English, Cohere Multilingual, (new models auto-discovered) |
| Chunking strategy | Paragraph, Section, Sliding window, Fixed words, Semantic |
| Retrieval mode | BM25 keyword, kNN vector, Hybrid (boosted), Hybrid RRF |

Against a **ground truth dataset** of known-answer queries derived from our test ICDs.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Evaluation Harness                          │
│                                                              │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────┐ │
│  │Model Registry│  │ Ground Truth    │  │ Historical Runs  │ │
│  │(Bedrock probe)│  │ (known answers)│  │ (JSON on disk)   │ │
│  └──────┬───────┘  └───────┬────────┘  └────────┬────────┘ │
│         │                   │                     │          │
│         v                   v                     v          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │               EvalHarness.evaluate(k=10)                 ││
│  │                                                          ││
│  │  For each (model × chunk_strategy × retrieval_mode):     ││
│  │    1. Embed query                                        ││
│  │    2. Search OpenSearch                                  ││
│  │    3. Score against ground truth                         ││
│  │    4. Record: Recall@K, MRR, nDCG, latency, cost        ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          v                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Comparison & Recommendation                  ││
│  │                                                          ││
│  │  - Best config overall                                   ││
│  │  - Delta vs previous run                                 ││
│  │  - Category breakdown (requirements, architecture, TBD)  ││
│  │  - Cost/quality tradeoff                                 ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Workflow

### 1. First-time setup

```bash
# Start local OpenSearch
docker compose up -d

# Ingest your test ICDs (produces Document IR YAML)
python3 -m src.cli ingest icds/20150010976.pdf --output-dir output --format yaml
python3 -m src.cli ingest icds/HSI_SYS_015G.pdf --output-dir output --format yaml

# Index into all configured search indices
python3 -m src.cli search-index output/20150010976_document_ir.yaml
python3 -m src.cli search-index output/HSI_SYS_015G_document_ir.yaml
```

### 2. Run evaluation benchmark

```bash
python3 -m src.cli search-eval -k 10
```

Output:
```
Evaluation Run: 20260727_141532 (2026-07-27T14:15:32+00:00)
Queries: 13, K=10

Config                              Recall@K       MRR    nDCG  Hit Rate   p50ms     Cost
-----------------------------------------------------------------------------------------------
titan-v2-section/hybrid_rrf            85.3%     0.782   0.801    92.3%     45    $0.0023
titan-v2-paragraph/hybrid_rrf          80.2%     0.714   0.735    84.6%     42    $0.0021
cohere-en-paragraph/hybrid             76.9%     0.689   0.712    84.6%     38    $0.0019
titan-v2-sliding/vector_only           72.1%     0.612   0.648    76.9%     51    $0.0028
titan-v2-paragraph/keyword_only        65.4%     0.523   0.556    69.2%      8    $0.0000
...

🏆 Best: titan-v2-section/hybrid_rrf (Recall@10 = 85.3%)
```

### 3. Check for new models

```bash
python3 -m src.cli search-models
```

Output:
```
Model Availability Report (2026-07-27T14:20:00+00:00)
Region: us-east-1
Known embedding models: 4
  Available: 4
  Deprecated: 0

🆕 New models (1):
  - amazon.titan-embed-text-v3:0 (Amazon)

📊 Needs benchmarking (1):
  - amazon.titan-embed-text-v3:0
```

When a new model is found:
1. Add it to `EmbeddingProvider` enum in `config.py`
2. Add a config entry to `ALL_CONFIGS`
3. Re-run `search-index` and `search-eval`
4. The harness tells you if it's better

### 4. When a model is deprecated

The harness detects it via `check_availability()`:
```
⚠️  Deprecated (1):
  - cohere.embed-english-v3
```

Action: switch active search to the next-best config from your eval history.

### 5. Search the corpus

```bash
# Default: uses best config from last eval run
python3 -m src.cli search "thermal operating limits"

# Specific mode
python3 -m src.cli search "power requirements" --mode keyword
```

## Adding Ground Truth

The eval harness is only as good as its ground truth. Add queries to `src/search/ground_truth.py` whenever you:
- Encounter a real question someone asks about an ICD
- Find a search result that was wrong (add the query + correct answer)
- Ingest a new document (add 3-5 characteristic queries)

```python
RelevanceJudgment(
    query_id="lvc-006",
    query="connector type for power interface",
    relevant_texts=["MIL-DTL-38999", "connector"],
    relevant_pages=[5],
    category="requirements",
)
```

## Metrics Explained

| Metric | What it measures | Why it matters |
|--------|-----------------|----------------|
| Recall@K | % of relevant docs in top K results | "Did we find it?" |
| MRR | 1/rank of first relevant hit | "How quickly do we find it?" |
| nDCG@K | Position-weighted relevance | "Are good results ranked higher?" |
| Hit Rate | % of queries with ≥1 relevant result | "How often do we completely miss?" |
| p50/p95 latency | Search response time | UX quality |
| Cost | Embedding API charges per query | Budget control |

## File Layout

```
src/search/
├── __init__.py
├── config.py           # Models, strategies, index configs (add new models here)
├── chunking.py         # Document → chunks (all strategies)
├── embeddings.py       # Bedrock embedding client (all providers)
├── indexing.py         # OpenSearch index management
├── retrieval.py        # Hybrid search (BM25 + kNN + RRF)
├── pipeline.py         # Orchestrator (ingest, search, eval)
├── eval_harness.py     # Scoring, aggregation, comparison
├── ground_truth.py     # Known-answer queries (the test suite)
└── model_registry.py   # Bedrock model discovery + deprecation detection

tests/
├── unit/test_search.py          # Chunking + scoring tests (no AWS needed)
└── results/search_eval/         # Historical eval run JSONs
    ├── eval_20260727_141532.json
    └── model_registry.json

docker-compose.yml               # Local OpenSearch
```

## Design Decisions

1. **Ground truth as test suite** — same philosophy as visual fidelity tests. Regressions are caught immediately.

2. **All configs indexed in parallel** — costs more upfront but means benchmarking is instant (no re-indexing to compare).

3. **Historical tracking** — every eval run saved to JSON. You can plot improvement over time and correlate with model releases.

4. **RRF over score normalization** — Reciprocal Rank Fusion doesn't require score calibration between BM25 and kNN, making it robust across model changes.

5. **Model registry probes Bedrock API** — doesn't rely on documentation; queries the actual service for what's available right now.

6. **Category-level scoring** — breaks down performance by query type (requirements, architecture, TBD, metadata) to identify where specific strategies excel.
