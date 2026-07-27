"""Tests for the search pipeline — chunking, config, and evaluation scoring.

These tests run without OpenSearch or AWS credentials.
"""

from __future__ import annotations

import pytest

from src.search.config import (
    ALL_CONFIGS,
    ChunkConfig,
    ChunkStrategy,
    EmbeddingConfig,
    EmbeddingProvider,
    IndexConfig,
    SimilarityMetric,
    TITAN_V2_PARAGRAPH,
    TITAN_V2_SECTION,
    TITAN_V2_SLIDING,
)
from src.search.chunking import Chunk, ChunkResult, chunk_document
from src.search.ground_truth import (
    ALL_GROUND_TRUTH,
    RelevanceJudgment,
    get_all_ground_truth,
)
from src.search.eval_harness import EvalHarness, QueryMetrics


# -----------------------------------------------------------------
# Test data: simplified Document IR page structures
# -----------------------------------------------------------------

SAMPLE_PAGES = [
    {
        "page_number": 1,
        "headings": [
            {"text": "Introduction", "section_number": "1.0", "y": 72},
        ],
        "text_blocks": [
            {
                "text": "This Interface Control Document defines the interface between "
                        "the LVC system and the ground segment. It covers data rates, "
                        "protocols, and electrical requirements.",
                "y": 120,
            },
            {
                "text": "The purpose of this document is to provide a complete "
                        "specification of all interfaces necessary for integration.",
                "y": 200,
            },
        ],
        "tables": [],
    },
    {
        "page_number": 2,
        "headings": [
            {"text": "Applicable Documents", "section_number": "2.0", "y": 72},
        ],
        "text_blocks": [
            {
                "text": "The following documents are applicable to this ICD.",
                "y": 120,
            },
        ],
        "tables": [
            {
                "y": 150,
                "rows": [
                    {"cells": [{"text": "Doc ID"}, {"text": "Title"}, {"text": "Rev"}]},
                    {"cells": [{"text": "ABC-001"}, {"text": "System Requirements"}, {"text": "A"}]},
                    {"cells": [{"text": "DEF-002"}, {"text": "Safety Analysis"}, {"text": "B"}]},
                ],
            },
        ],
    },
    {
        "page_number": 3,
        "headings": [
            {"text": "Electrical Interface", "section_number": "3.0", "y": 72},
            {"text": "Power Requirements", "section_number": "3.1", "y": 200},
        ],
        "text_blocks": [
            {
                "text": "The electrical interface provides 28V DC power at a maximum "
                        "current of 2.5 amperes. The connector shall be MIL-DTL-38999.",
                "y": 120,
            },
            {
                "text": "Power consumption shall not exceed 50 watts during normal "
                        "operations. Peak power during initialization is TBD.",
                "y": 250,
            },
        ],
        "tables": [],
    },
]


# -----------------------------------------------------------------
# Config tests
# -----------------------------------------------------------------

class TestConfig:
    def test_all_configs_defined(self):
        """Verify predefined configs exist."""
        assert len(ALL_CONFIGS) >= 4

    def test_index_name_generation(self):
        """Index names are deterministic from config."""
        name = TITAN_V2_PARAGRAPH.index_name
        assert "titan" in name.lower()
        assert "paragraph" in name.lower()
        assert "1024d" in name

    def test_index_names_unique(self):
        """Each config produces a unique index name."""
        names = [c.index_name for c in ALL_CONFIGS]
        assert len(names) == len(set(names))

    def test_embedding_provider_values(self):
        """Embedding providers map to valid model IDs."""
        for provider in EmbeddingProvider:
            assert "." in provider.value or "amazon" in provider.value.lower()


# -----------------------------------------------------------------
# Chunking tests
# -----------------------------------------------------------------

class TestChunking:
    def test_paragraph_chunking(self):
        """Paragraph strategy produces one chunk per text block + headings."""
        config = ChunkConfig(strategy=ChunkStrategy.PARAGRAPH, max_tokens=512)
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)

        assert isinstance(result, ChunkResult)
        assert result.document_hash == "abc123"
        assert result.document_title == "Test Doc"
        assert len(result.chunks) > 0

        # Check chunk structure
        for chunk in result.chunks:
            assert chunk.chunk_id.startswith("abc123_")
            assert chunk.text
            assert chunk.page_number > 0
            assert chunk.content_type in ("paragraph", "heading", "table")

    def test_paragraph_includes_tables(self):
        """Paragraph strategy serializes tables into chunks."""
        config = ChunkConfig(strategy=ChunkStrategy.PARAGRAPH, max_tokens=512)
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)

        table_chunks = [c for c in result.chunks if c.content_type == "table"]
        assert len(table_chunks) >= 1
        # Table chunk should contain cell content
        assert "ABC-001" in table_chunks[0].text

    def test_paragraph_heading_attribution(self):
        """Chunks carry their section heading context."""
        config = ChunkConfig(strategy=ChunkStrategy.PARAGRAPH, max_tokens=512)
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)

        # Find chunks on page 3 (under "Electrical Interface")
        page3_text_chunks = [
            c for c in result.chunks
            if c.page_number == 3 and c.content_type == "paragraph"
        ]
        assert len(page3_text_chunks) >= 1
        # Should have section context
        assert any(
            c.section_heading in ("Electrical Interface", "Power Requirements")
            for c in page3_text_chunks
        )

    def test_section_chunking(self):
        """Section strategy groups text between headings."""
        config = ChunkConfig(
            strategy=ChunkStrategy.SECTION,
            max_tokens=1024,
            include_heading=True,
        )
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)

        assert len(result.chunks) > 0
        # Sections should be fewer than paragraphs (grouped)
        para_config = ChunkConfig(strategy=ChunkStrategy.PARAGRAPH, max_tokens=512)
        para_result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", para_config)
        assert len(result.chunks) <= len(para_result.chunks)

    def test_section_heading_in_text(self):
        """Section chunks include the heading text when configured."""
        config = ChunkConfig(
            strategy=ChunkStrategy.SECTION,
            max_tokens=1024,
            include_heading=True,
        )
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)

        # At least one chunk should have heading text embedded
        assert any("Electrical Interface" in c.text for c in result.chunks)

    def test_sliding_window_chunking(self):
        """Sliding window produces overlapping chunks."""
        config = ChunkConfig(
            strategy=ChunkStrategy.SLIDING_WINDOW,
            max_tokens=50,  # Very small to force multiple windows
            overlap_tokens=15,
        )
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)

        assert len(result.chunks) >= 3  # Should produce several windows

    def test_fixed_word_chunking(self):
        """Fixed word chunking (no overlap)."""
        config = ChunkConfig(
            strategy=ChunkStrategy.FIXED_WORDS,
            max_tokens=50,
        )
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)

        assert len(result.chunks) >= 2

    def test_empty_pages(self):
        """Empty page list produces no chunks."""
        config = ChunkConfig(strategy=ChunkStrategy.PARAGRAPH, max_tokens=512)
        result = chunk_document([], "abc123", "Test Doc", config)
        assert len(result.chunks) == 0

    def test_token_estimate(self):
        """Token estimates are reasonable."""
        chunk = Chunk(
            chunk_id="test_1_0",
            text="This is a test sentence with ten words in it.",
            document_hash="test",
            document_title="Test",
            page_number=1,
        )
        # ~10 words × 1.3 = ~13 tokens
        assert 10 <= chunk.token_estimate <= 20

    def test_chunk_result_total_tokens(self):
        """ChunkResult computes total token estimate."""
        config = ChunkConfig(strategy=ChunkStrategy.PARAGRAPH, max_tokens=512)
        result = chunk_document(SAMPLE_PAGES, "abc123", "Test Doc", config)
        assert result.total_tokens_estimate > 0


# -----------------------------------------------------------------
# Ground truth tests
# -----------------------------------------------------------------

class TestGroundTruth:
    def test_ground_truth_defined(self):
        """Ground truth has queries for each test document."""
        assert len(ALL_GROUND_TRUTH) >= 6
        assert "20150010976" in ALL_GROUND_TRUTH
        assert "HSI_SYS_015G" in ALL_GROUND_TRUTH
        assert "20130010957" in ALL_GROUND_TRUTH
        assert "ICESat2_ATL03" in ALL_GROUND_TRUTH
        assert "IDSS_IDD_RevF" in ALL_GROUND_TRUTH
        assert "NDS_IDD_RevC" in ALL_GROUND_TRUTH

    def test_all_queries_have_expected(self):
        """Every query has at least one expected relevant text."""
        for queries in ALL_GROUND_TRUTH.values():
            for q in queries:
                assert len(q.relevant_texts) >= 1
                assert q.query
                assert q.query_id

    def test_get_all_ground_truth(self):
        """Aggregate getter returns all queries (core + expanded)."""
        all_q = get_all_ground_truth()
        assert len(all_q) >= 100  # Core + expanded queries


# -----------------------------------------------------------------
# Eval scoring tests
# -----------------------------------------------------------------

class TestEvalScoring:
    """Test the evaluation scoring logic directly."""

    def test_perfect_recall(self):
        """When all expected texts are found, recall = 1.0."""
        from src.search.eval_harness import EvalHarness
        from src.search.config import SearchConfig
        from src.search.retrieval import SearchHit, SearchResult, RetrievalMode

        judgment = RelevanceJudgment(
            query_id="test-001",
            query="power requirements",
            relevant_texts=["power", "28V"],
        )

        # Simulate hits that contain expected texts
        result = SearchResult(
            query="power requirements",
            mode=RetrievalMode.HYBRID,
            hits=[
                SearchHit(
                    chunk_id="c1", text="The power supply provides 28V DC",
                    score=0.9, document_hash="x", document_title="Test", page_number=1,
                ),
                SearchHit(
                    chunk_id="c2", text="Some irrelevant text here",
                    score=0.5, document_hash="x", document_title="Test", page_number=2,
                ),
            ],
        )

        harness = EvalHarness(SearchConfig())
        qm = harness._score_query(judgment, result, k=10, latency_ms=5.0)

        assert qm.recall_at_k == 1.0
        assert qm.hit is True
        assert qm.reciprocal_rank == 1.0  # First hit is relevant
        assert len(qm.relevant_found) == 2
        assert len(qm.relevant_missed) == 0

    def test_partial_recall(self):
        """When some expected texts are found."""
        from src.search.eval_harness import EvalHarness
        from src.search.config import SearchConfig
        from src.search.retrieval import SearchHit, SearchResult, RetrievalMode

        judgment = RelevanceJudgment(
            query_id="test-002",
            query="thermal limits",
            relevant_texts=["thermal", "temperature", "heater"],
        )

        result = SearchResult(
            query="thermal limits",
            mode=RetrievalMode.HYBRID,
            hits=[
                SearchHit(
                    chunk_id="c1", text="The thermal control system operates...",
                    score=0.8, document_hash="x", document_title="Test", page_number=1,
                ),
                SearchHit(
                    chunk_id="c2", text="Temperature range is -40 to +60C",
                    score=0.6, document_hash="x", document_title="Test", page_number=1,
                ),
            ],
        )

        harness = EvalHarness(SearchConfig())
        qm = harness._score_query(judgment, result, k=10, latency_ms=3.0)

        assert qm.recall_at_k == pytest.approx(2 / 3)  # Found 2 of 3
        assert qm.hit is True
        assert "heater" in qm.relevant_missed

    def test_zero_recall(self):
        """When no expected texts are found."""
        from src.search.eval_harness import EvalHarness
        from src.search.config import SearchConfig
        from src.search.retrieval import SearchHit, SearchResult, RetrievalMode

        judgment = RelevanceJudgment(
            query_id="test-003",
            query="conflict detection",
            relevant_texts=["conflict", "detection"],
        )

        result = SearchResult(
            query="conflict detection",
            mode=RetrievalMode.HYBRID,
            hits=[
                SearchHit(
                    chunk_id="c1", text="The system performs validation checks",
                    score=0.3, document_hash="x", document_title="Test", page_number=1,
                ),
            ],
        )

        harness = EvalHarness(SearchConfig())
        qm = harness._score_query(judgment, result, k=10, latency_ms=2.0)

        assert qm.recall_at_k == 0.0
        assert qm.hit is False
        assert qm.reciprocal_rank == 0.0

    def test_mrr_non_first_hit(self):
        """MRR reflects position of first relevant hit."""
        from src.search.eval_harness import EvalHarness
        from src.search.config import SearchConfig
        from src.search.retrieval import SearchHit, SearchResult, RetrievalMode

        judgment = RelevanceJudgment(
            query_id="test-004",
            query="data rate",
            relevant_texts=["data rate"],
        )

        result = SearchResult(
            query="data rate",
            mode=RetrievalMode.HYBRID,
            hits=[
                SearchHit(
                    chunk_id="c1", text="Introduction to the system",
                    score=0.9, document_hash="x", document_title="Test", page_number=1,
                ),
                SearchHit(
                    chunk_id="c2", text="More irrelevant content",
                    score=0.7, document_hash="x", document_title="Test", page_number=1,
                ),
                SearchHit(
                    chunk_id="c3", text="The data rate is 1.5 Mbps",
                    score=0.5, document_hash="x", document_title="Test", page_number=3,
                ),
            ],
        )

        harness = EvalHarness(SearchConfig())
        qm = harness._score_query(judgment, result, k=10, latency_ms=4.0)

        assert qm.recall_at_k == 1.0
        assert qm.reciprocal_rank == pytest.approx(1 / 3)  # Found at rank 3


# -----------------------------------------------------------------
# Integration test: full chunking pipeline
# -----------------------------------------------------------------

class TestChunkingIntegration:
    """Test that all strategies work on the same input without error."""

    @pytest.mark.parametrize("strategy", [
        ChunkStrategy.PARAGRAPH,
        ChunkStrategy.SECTION,
        ChunkStrategy.SLIDING_WINDOW,
        ChunkStrategy.FIXED_WORDS,
    ])
    def test_all_strategies_produce_chunks(self, strategy):
        """Every strategy produces non-empty results from sample data."""
        config = ChunkConfig(
            strategy=strategy,
            max_tokens=256,
            overlap_tokens=32,
        )
        result = chunk_document(SAMPLE_PAGES, "hash123", "NASA ICD", config)
        assert len(result.chunks) > 0
        assert result.total_tokens_estimate > 0
        assert all(c.document_hash == "hash123" for c in result.chunks)
