# Requirements: Search & Retrieval (OpenSearch + Embeddings)

## 1. What This Enables

Imagine being able to ask:

- "Show me every requirement that mentions the command uplink interface"
- "Find all places where timing constraints are defined"
- "What requirements are similar to REQ-CMD-001?"
- "Which signals use milliseconds as their unit?"
- "What changed between Rev B and Rev C regarding the flight computer?"

Traditional search (Ctrl+F in a PDF) only finds exact word matches. This system adds **semantic search** — it understands *meaning*, not just matching letters.

## 2. How It Works (Plain English)

### 2.1 Indexing (Putting the Document Into Searchable Form)

When you upload an ICD, the system:

1. **Breaks the document into chunks** — each text block, requirement, table row, and diagram label becomes a searchable "document" in the index
2. **Stores the text** — for keyword search (exact word matching)
3. **Creates an embedding** — a mathematical fingerprint that captures the *meaning* of the text (a list of ~1,000 numbers)
4. **Stores metadata** — page number, section, document ID, block type, requirement ID

Think of it like a library catalog. Each chunk gets a card with:
- The exact text (for looking up specific words)
- A "meaning fingerprint" (for finding related content)
- A label (what page, what section, what type)

### 2.2 Searching (Finding What You Need)

Three search modes work together:

| Mode | How It Works | Good For |
|------|-------------|----------|
| **Keyword** | Finds exact words, uses BM25 ranking (same as Google's basic algorithm) | Protocol names, requirement IDs, acronyms, exact phrases |
| **Semantic** | Compares meaning fingerprints, finds conceptually similar text | "Find requirements about data validation" even if they don't use the word "validation" |
| **Hybrid** | Combines keyword + semantic scores | Best overall results — catches both exact matches and related content |

### 2.3 Why Not Just Use Ctrl+F?

| Ctrl+F | This System |
|--------|-------------|
| One document at a time | Search across all ICDs simultaneously |
| Exact text only | Finds synonyms and related concepts |
| No filtering | Filter by section, type, page, interface |
| No ranking | Results ranked by relevance |
| Can't find "requirements like this one" | Semantic similarity finds related requirements |
| Can't track what changed | Search within revision diffs |

## 3. Technical Architecture

```
┌─────────────────────────────────────────────────────┐
│  User Query: "command uplink timing requirements"    │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  FastAPI Search Endpoint     │
        │  1. Keyword → BM25 search    │
        │  2. Embed query → vector     │
        │  3. Hybrid score & rank      │
        │  4. Apply filters            │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  Amazon OpenSearch Service   │
        │  ┌─────────┐ ┌───────────┐  │
        │  │ Text    │ │ Vector    │  │
        │  │ Index   │ │ Index     │  │
        │  │ (BM25)  │ │ (k-NN)   │  │
        │  └─────────┘ └───────────┘  │
        └─────────────────────────────┘
```

## 4. Embedding Models

### 4.1 What Is an Embedding?

An embedding converts text into a fixed-size list of numbers (a "vector") that captures its meaning. Texts with similar meanings have similar vectors, even if they use completely different words.

Example:
- "The system shall transmit data at 1 Hz" → [0.23, -0.15, 0.87, ...]
- "Data transmission rate shall be once per second" → [0.21, -0.14, 0.85, ...]
- "The color of the spacecraft is blue" → [-0.45, 0.92, 0.03, ...]

The first two are close together (similar meaning). The third is far away (unrelated).

### 4.2 Model Options

| Model | Dimensions | Speed | Quality | Cost | Notes |
|-------|-----------|-------|---------|------|-------|
| **Amazon Titan Embeddings V2** | 1024 | Fast | Good | $0.00002/1K tokens | Native to Bedrock, no data leaves AWS |
| **Cohere Embed v3** | 1024 | Fast | Excellent | $0.0001/1K tokens | Best multilingual, available on Bedrock |
| **Amazon Titan Embeddings Lite** | 256 | Very fast | Adequate | $0.000006/1K tokens | Low cost for large corpora |
| **Self-hosted (e5-large)** | 1024 | Medium | Very good | Compute only | No API costs, full control |

### 4.3 Recommended: Amazon Titan Embeddings V2

**Why:**
- Runs entirely within AWS (no data leaves your VPC)
- Good quality for technical/engineering text
- Low cost ($0.02 per 1,000 pages of ICD text)
- No infrastructure to manage
- Supports asymmetric search (short query vs long document)

**Dimensions: 1024** — each text chunk becomes a list of 1,024 numbers. This provides enough "resolution" to distinguish between closely related but different engineering concepts.

### 4.4 Chunking Strategy

How we split the document for embedding matters enormously:

| Chunk Type | Content | Why This Size |
|-----------|---------|---------------|
| **Requirement** | Single requirement text (1-3 sentences) | Natural unit; users search for requirements |
| **Text block** | One paragraph or heading | Matches the Document IR structure |
| **Table row** | One row of a definition table | Users search for specific fields/signals |
| **Section** | Full section text (may be long) | For broad topic search |

**Overlap:** Adjacent chunks share 1 sentence of overlap so that concepts split across chunk boundaries are still findable.

## 5. OpenSearch Index Design

### 5.1 Index Schema

```json
{
  "mappings": {
    "properties": {
      "document_id": { "type": "keyword" },
      "revision": { "type": "keyword" },
      "page": { "type": "integer" },
      "section": { "type": "keyword" },
      "block_id": { "type": "keyword" },
      "block_type": {
        "type": "keyword",
        "enum": ["requirement", "paragraph", "heading", "table_row", "caption"]
      },
      "requirement_id": { "type": "keyword" },
      "text": {
        "type": "text",
        "analyzer": "english"
      },
      "text_exact": {
        "type": "keyword"
      },
      "embedding": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": {
          "name": "hnsw",
          "engine": "nmslib",
          "parameters": {
            "m": 16,
            "ef_construction": 512
          }
        }
      },
      "interfaces": { "type": "keyword" },
      "systems": { "type": "keyword" },
      "verification_method": { "type": "keyword" },
      "has_tbd": { "type": "boolean" },
      "indexed_at": { "type": "date" }
    }
  }
}
```

### 5.2 What the Parameters Mean

| Parameter | Value | What It Controls |
|-----------|-------|-----------------|
| **dimension** | 1024 | Size of the embedding vector (must match the model) |
| **m** | 16 | How many connections each vector has to neighbors. Higher = more accurate but more memory |
| **ef_construction** | 512 | How hard the system tries to build a good index. Higher = better recall but slower indexing |
| **engine** | nmslib | The algorithm for finding nearest neighbors. nmslib is fast and well-tested |
| **analyzer** | english | Applies stemming (so "requirements" matches "requirement") and removes stop words |

### 5.3 Indexes

| Index Name | Contents | Use Case |
|------------|----------|----------|
| `icd-blocks` | All text blocks from all documents | General search |
| `icd-requirements` | Only requirement blocks | Requirement-specific queries |
| `icd-tables` | Table row content | Field/signal/message lookup |
| `icd-changes` | Change records | "What changed?" queries |

## 6. Search Quality Testing

### 6.1 How We Know Search Works Correctly

We build a **test set** of queries with known correct answers:

```yaml
search_tests:
  - query: "command transfer frame"
    expected_results:
      - requirement_id: REQ-CMD-001
        page: 12
    expected_in_top_5: true

  - query: "data rate for telemetry downlink"
    expected_results:
      - section: "3.5"
        block_type: requirement
    expected_in_top_10: true

  - query: "what protocols are used"
    expected_results:
      - text_contains: "CCSDS"
      - text_contains: "TCP/IP"
    mode: semantic
```

### 6.2 Metrics

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| **Recall@5** | Of the correct results, how many appear in the top 5? | ≥80% |
| **Recall@10** | Of the correct results, how many appear in the top 10? | ≥95% |
| **MRR** (Mean Reciprocal Rank) | On average, how high is the first correct result? | ≥0.7 |
| **Precision@5** | Of the top 5 results, how many are actually relevant? | ≥60% |

### 6.3 Testing Methodology

1. **Keyword accuracy**: Search for requirement IDs, acronyms, exact phrases → must return exact matches
2. **Semantic accuracy**: Search with paraphrased queries → must find the right section
3. **Cross-document**: Search across multiple ICDs → must return results from all relevant docs
4. **Filter correctness**: Filter by page/section/type → must not return filtered-out content
5. **Regression**: Re-run test set after any index or model change → scores must not drop

## 7. Embedding Best Practices

### 7.1 For Best Search Quality

| Practice | Why |
|----------|-----|
| **Chunk at natural boundaries** | Don't split mid-sentence. Use paragraphs, requirements, table rows |
| **Include context in chunks** | Prepend section heading to each chunk so the embedding knows the topic |
| **Normalize text** | Remove excessive whitespace, fix encoding issues before embedding |
| **Use asymmetric models** | Query embeddings and document embeddings can use different modes (short vs long) |
| **Re-embed when model updates** | New model version = re-run all embeddings for consistency |

### 7.2 For Best Performance

| Practice | Why |
|----------|-----|
| **Batch embedding calls** | Send 25-50 chunks per API call, not one at a time |
| **Cache embeddings** | Store vectors in the index; don't re-compute on every search |
| **Use filters before vector search** | Narrow by document/section first, then rank by similarity |
| **Limit vector dimensions if possible** | 256-dim Titan Lite is 4x faster than 1024-dim for approximate search |
| **Monitor latency** | P95 search should be <200ms for good UX |

### 7.3 For Cost Control

| Cost Factor | Estimate for 1 ICD (35 pages) |
|-------------|-------------------------------|
| Embedding all text blocks (~500 chunks) | ~$0.01 |
| Embedding all queries (100 searches/day) | ~$0.002/day |
| OpenSearch cluster (t3.small.search) | ~$0.036/hour = $26/month |
| Storage (1 ICD indexed) | Negligible |

**Scaling:** 1,000 ICDs × 500 chunks = 500,000 vectors. Still fits on a single small OpenSearch node. The cost is dominated by the cluster, not the embeddings.

## 8. Integration with the Editor

### 8.1 Indexing Pipeline

```
PDF uploaded
    → Pipeline extracts Document IR
    → Each text block gets:
        1. Indexed as-is (keyword search)
        2. Embedded via Bedrock Titan V2 (semantic search)
        3. Tagged with metadata (page, section, type)
    → OpenSearch bulk insert
```

### 8.2 Search in the UI

```
User types in search bar
    → FastAPI receives query
    → Query embedded via Bedrock (same model)
    → Hybrid search: BM25 keyword + k-NN vector + metadata filters
    → Results ranked and returned
    → UI highlights matching blocks on the page view
```

### 8.3 "Find Similar" Feature

```
User selects a requirement block
    → Block's embedding retrieved from index
    → k-NN search finds most similar blocks across all documents
    → Shows: "These requirements are related to the one you selected"
```

## 9. OpenSearch vs Alternatives

| Option | Pros | Cons |
|--------|------|------|
| **Amazon OpenSearch** | Managed, scales, hybrid search built-in, k-NN native | Monthly cost, AWS-only |
| **PostgreSQL + pgvector** | Simpler, already in stack, lower cost | Slower at scale, less mature hybrid search |
| **Elasticsearch** | Mature, large ecosystem | Not managed on AWS (or use OpenSearch which is the fork) |
| **Pinecone/Weaviate** | Purpose-built for vectors | External service, data leaves your control |
| **In-memory (FAISS)** | Zero infrastructure | No persistence, no keyword search, single machine |

**Recommendation:** Start with **PostgreSQL + pgvector** for MVP (already need Postgres for change tracking). Move to **OpenSearch** when you have >10 documents or need sub-200ms search across large corpora.

## 10. MVP Search Scope

For Phase 2 minimum:

1. **In-memory keyword search** across the Document IR (no external services)
2. **Works immediately** after ingestion (no async indexing needed)
3. **Filters** by page, section, block type

Upgrade path:
- Add pgvector when Postgres is introduced (Phase 2 late)
- Add OpenSearch + Bedrock embeddings when scaling to multiple documents (Phase 3)
- Add semantic "find similar" when corpus is large enough to benefit (Phase 4)
