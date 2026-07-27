# End-to-End Test Suite Overview

## Purpose

This test suite validates the ICD Writer application from the **user's perspective** — simulating exactly what the React frontend does when a user interacts with the editor. Each test module maps to a distinct user workflow.

## Test Philosophy

- **Black-box testing**: Tests call the same REST API endpoints the frontend calls, in the same sequence a user would trigger them.
- **Real documents**: Tests run against actual NASA ICD PDFs in `icds/digital/`, not synthetic data.
- **No mocks for core logic**: The PDF extraction, rendering, search, and RAG pipelines execute for real. Only external services (AWS Bedrock) are tested live when available.
- **Graceful skipping**: Tests that require OpenSearch or specific documents skip cleanly with a reason message rather than failing.

## Test Organization

```
tests/
├── e2e/                          # End-to-end API tests (this suite)
│   ├── __init__.py               # Shared fixtures
│   ├── test_session.py           # Session lifecycle
│   ├── test_document_loading.py  # Open, navigate, render pages
│   ├── test_element_selection.py # Click targets, page analysis, table zones
│   ├── test_editing.py           # Edit text, undo, redo
│   ├── test_search_rag.py        # Search modes + RAG answers
│   └── test_tbd_dashboard.py     # TBD tracking dashboard
├── unit/                         # Unit tests (models, chunking, eval)
│   ├── test_models.py
│   └── test_search.py
├── integration/                  # Pipeline integration tests
│   ├── test_pipeline.py
│   └── test_text_accuracy.py
└── results/                      # Persisted evaluation data
    └── search_eval/
```

## Module Descriptions

### test_session.py — Session Management
**User story**: "I open the app and start working."

| Test | What it validates |
|------|-------------------|
| `test_start_session` | App creates a session with unique ID |
| `test_get_session_after_start` | Session info is retrievable |
| `test_get_session_before_start_returns_error` | Graceful error without session |
| `test_actions_initially_empty` | Undo/redo state starts clean |

### test_document_loading.py — Open & Navigate Documents
**User story**: "I open a PDF and browse its pages."

| Test | What it validates |
|------|-------------------|
| `test_open_document_success` | PDF loads with correct page count |
| `test_open_nonexistent_returns_404` | Bad path gives clear error |
| `test_open_records_in_session` | Session tracks which doc is loaded |
| `test_get_page_data` | Page returns text blocks |
| `test_get_page_blocks_have_required_fields` | Blocks have id, text, bbox |
| `test_get_page_image_returns_png` | Page renders as image |
| `test_all_pages_accessible` | Every page 1–8 works |
| `test_invalid_page_number` | Out-of-range pages fail gracefully |
| `test_open_lvc` | Large 35-page document loads |
| `test_lvc_page_15_has_content` | Mid-document pages have content |

### test_element_selection.py — Click-to-Edit Targets
**User story**: "I click on text in the PDF and it becomes editable."

| Test | What it validates |
|------|-------------------|
| `test_analysis_returns_page_type` | Page classified (text, table, TOC) |
| `test_analysis_returns_header_footer` | Headers/footers identified |
| `test_toc_page_detected` | Table of Contents page recognized |
| `test_all_pages_return_valid_analysis` | No crashes on any page |
| `test_elements_endpoint_returns_list` | Clickable overlays generated |
| `test_elements_have_required_fields` | Each overlay has type, text, bbox |
| `test_elements_include_headers` | Header elements are present |
| `test_element_ids_are_unique_per_page` | No duplicate IDs |
| `test_table_zones_endpoint` | Table zone detection works |
| `test_table_page_has_zones` | Pages with tables detected |
| `test_non_table_page_has_no_zones` | Title page has no table zones |

### test_editing.py — Edit, Undo, Redo
**User story**: "I edit text, change my mind, and undo."

| Test | What it validates |
|------|-------------------|
| `test_edit_block_succeeds` | Edit API returns success |
| `test_edit_reflected_in_page_data` | Edited text visible on re-fetch |
| `test_edit_increments_count` | Session tracks edit count |
| `test_edit_nonexistent_block` | Bad block ID gives error |
| `test_undo_reverts_edit` | Undo restores original text |
| `test_redo_restores_edit` | Redo re-applies undone edit |
| `test_undo_with_nothing_to_undo` | No crash when nothing to undo |
| `test_undo_redo_state_reported` | Frontend can show undo/redo buttons |

### test_search_rag.py — Search & AI Answers
**User story**: "I search for information across all my ICDs and get an answer."

| Test | What it validates |
|------|-------------------|
| `test_search_returns_hits` | Basic search finds results |
| `test_search_hit_structure` | Hits have score, document, page |
| `test_search_keyword_mode` | BM25 keyword search works |
| `test_search_vector_mode` | Semantic vector search works |
| `test_search_hybrid_mode` | Combined search works |
| `test_search_respects_k` | K parameter limits results |
| `test_search_empty_query` | Empty input doesn't crash |
| `test_rag_returns_answer` | RAG generates a text answer |
| `test_rag_has_citations` | Answer cites source documents |
| `test_rag_citation_structure` | Citations have doc, page, section |
| `test_rag_has_confidence` | Confidence level reported |
| `test_rag_has_cost_and_timing` | Cost and latency tracked |
| `test_rag_warnings_field` | TBD/contractual warnings included |

### test_tbd_dashboard.py — TBD Tracking
**User story**: "I see all unresolved TBDs across my program's ICDs."

| Test | What it validates |
|------|-------------------|
| `test_get_dashboard_returns_structure` | Dashboard loads with stats + items |
| `test_stats_have_required_fields` | All tracking counters present |
| `test_items_have_required_fields` | Items have id, type, status, context |
| `test_filter_by_status` | Status filter works |
| `test_filter_by_type` | Type filter (TBD vs TBR) works |
| `test_ingest_endpoint` | Document scanning for TBDs works |
| `test_stats_consistency` | Counts match actual items |
| `test_update_status_success` | Status can be changed |
| `test_update_nonexistent_item` | Bad ID gives 404 |

## Running

```bash
# All e2e tests
python3 -m pytest tests/e2e/ -v

# Full suite (unit + integration + e2e)
python3 -m pytest tests/ -v

# Just one module
python3 -m pytest tests/e2e/test_editing.py -v

# With coverage
python3 -m pytest tests/e2e/ --cov=src --cov-report=term-missing
```

## Prerequisites

- PDFs in `icds/digital/` (HSI_SYS_015G.pdf, 20150010976.pdf, 20130010957.pdf)
- For search/RAG tests: OpenSearch running (`docker compose up -d`)
- For RAG tests: AWS credentials with Bedrock access
- Python packages: `httpx` (for FastAPI TestClient)

## Adding New Tests

When adding a new feature or fixing a bug:
1. Identify which user workflow is affected
2. Add test(s) to the appropriate module
3. Follow the pattern: fixture sets up state, test calls API, asserts response
4. Use `pytest.mark.skipif` for optional dependencies (OpenSearch, AWS)
