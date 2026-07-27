# Test Results

**Run Date:** 2026-07-27
**Runner:** pytest 8.3.5, Python 3.10.12
**Platform:** linux (x86_64)
**Duration:** 42.26s

## Summary

```
147 passed, 0 failed, 0 skipped, 5 warnings
```

| Suite | Tests | Passed | Failed | Skipped |
|-------|-------|--------|--------|---------|
| E2E — Session | 4 | 4 | 0 | 0 |
| E2E — Document Loading | 10 | 10 | 0 | 0 |
| E2E — Element Selection | 11 | 11 | 0 | 0 |
| E2E — Editing (Undo/Redo) | 8 | 8 | 0 | 0 |
| E2E — Search & RAG | 13 | 13 | 0 | 0 |
| E2E — TBD Dashboard | 9 | 9 | 0 | 0 |
| Unit — Models | 7 | 7 | 0 | 0 |
| Unit — Search (chunking, eval) | 25 | 25 | 0 | 0 |
| Integration — Pipeline | 30 | 30 | 0 | 0 |
| Integration — Text Accuracy | 30 | 30 | 0 | 0 |
| **Total** | **147** | **147** | **0** | **0** |

## Detailed Results by Workflow

### 1. Session Management ✅ (4/4)
- Start session → creates unique ID
- Get session info → returns metadata
- No session → graceful 404
- Undo/redo state → starts clean

### 2. Document Loading & Navigation ✅ (10/10)
- Open HSI ICD (8 pages) → success
- Open LVC ICD (35 pages) → success
- Non-existent PDF → 404
- Path recorded in session → verified
- All 8 pages accessible → verified
- Page images render as PNG → verified
- Text blocks have id, text, bbox → verified
- Invalid page number → graceful error
- Large document mid-pages → have content

### 3. Element Selection & Page Analysis ✅ (11/11)
- Page analysis returns type → verified (title_page, text, table, table_of_contents)
- Header/footer detection → verified (left/center/right)
- TOC page detection (page 3) → verified
- All 8 pages return valid analysis → no crashes
- Clickable overlays generated → verified
- Overlay fields complete (type, label, text, id, bbox) → verified
- Header elements present → verified
- Element IDs unique per page → verified
- Table zones endpoint works → verified
- Table page has zones → verified
- Title page has no zones → verified

### 4. Text Editing ✅ (8/8)
- Edit block → API returns success
- Edited text persisted → re-fetch confirms
- Edit count tracked → increments correctly
- Non-existent block → graceful error
- Undo → restores original text
- Redo → re-applies edit
- Undo with nothing → no crash
- Undo/redo state flags → correctly reported

### 5. Search & RAG ✅ (13/13)
- RRF search returns hits → verified
- Hit structure (chunk_id, text, score, document, page) → verified
- Keyword mode → works
- Vector mode → works
- Hybrid mode → works
- K parameter respected → verified
- Empty query → no crash
- RAG returns answer → verified (>20 chars)
- RAG has citations → verified
- Citation structure (label, doc, page) → verified
- Confidence indicator → verified (high/medium/low)
- Cost and timing tracked → verified
- Warnings field → verified (array)

### 6. TBD Dashboard ✅ (9/9)
- Dashboard returns stats + items + correlations → verified
- Stats have all required fields → verified
- Items have id, type, status, context, in_shall → verified
- Filter by status → returns only matching
- Filter by type (TBD/TBR) → returns only matching
- Ingest endpoint → scans documents successfully
- Stats consistent with items → verified
- Update status → success
- Non-existent item → 404

## Test Documents Used

| Document | Pages | Type | Used By |
|----------|-------|------|---------|
| HSI_SYS_015G.pdf | 8 | Digital | All e2e tests, integration |
| 20150010976.pdf (LVC) | 35 | Digital | Loading, integration, search |
| 20130010957.pdf (TSAFE) | 15 | Digital | Integration, search |
| HSI_SYS_015G_flattened.pdf | 8 | Scanned | Integration |
| 20150010976_flattened.pdf | 35 | Scanned | Integration |
| 20130010957_flat.pdf | 15 | Scanned | Integration |

## Environment

- OpenSearch 2.17.0 (local Docker) — required for search/RAG tests
- AWS Bedrock (us-east-1) — required for RAG tests
- Titan Embed Text V2 — embeddings
- Amazon Nova Pro — RAG generation
- All indices populated (4 indices, ~1,054 chunks)

## Warnings (non-critical)

All 5 warnings are Python deprecation notices from the `swig` bindings in PyMuPDF:
```
DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute
DeprecationWarning: builtin type SwigPyObject has no __module__ attribute
DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```
These are upstream issues in PyMuPDF's SWIG layer and do not affect functionality.

## Reproducing

```bash
# Prerequisites
source .venv/bin/activate
docker compose up -d  # OpenSearch
pip install httpx     # For TestClient

# Run full suite
python3 -m pytest tests/ -v

# Run only e2e
python3 -m pytest tests/e2e/ -v

# Run a specific workflow
python3 -m pytest tests/e2e/test_editing.py -v
```
