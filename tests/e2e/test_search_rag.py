"""E2E Test: Search and RAG

Tests the search pipeline through the API:
- Basic keyword search
- Vector search
- Hybrid RRF search
- RAG (answer with citations)
- Result structure validation

Requires: OpenSearch running locally with indexed documents.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


def opensearch_available() -> bool:
    """Check if OpenSearch is running."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("localhost", 9200))
        s.close()
        return True
    except Exception:
        return False


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.mark.skipif(not opensearch_available(), reason="OpenSearch not running")
class TestSearch:
    """Search endpoint without RAG."""

    def test_search_returns_hits(self, client):
        """POST /search returns hits for a valid query."""
        res = client.post("/search?query=thermal+limits&k=5&mode=rrf&rag=false")
        assert res.status_code == 200
        data = res.json()
        assert data["type"] == "search"
        assert data["query"] == "thermal limits"
        assert "hits" in data
        assert len(data["hits"]) > 0

    def test_search_hit_structure(self, client):
        """Each search hit has required fields."""
        res = client.post("/search?query=spectrometer&k=3&mode=rrf&rag=false")
        data = res.json()
        for hit in data["hits"]:
            assert "chunk_id" in hit
            assert "text" in hit
            assert "score" in hit
            assert "document_title" in hit
            assert "page_number" in hit
            assert "content_type" in hit
            assert hit["score"] > 0

    def test_search_keyword_mode(self, client):
        """Keyword-only search works without embeddings."""
        res = client.post("/search?query=heater+circuit&k=5&mode=keyword&rag=false")
        assert res.status_code == 200
        data = res.json()
        assert len(data["hits"]) > 0

    def test_search_vector_mode(self, client):
        """Vector-only search returns semantically relevant results."""
        res = client.post("/search?query=temperature+constraints&k=5&mode=vector&rag=false")
        assert res.status_code == 200
        data = res.json()
        assert len(data["hits"]) > 0

    def test_search_hybrid_mode(self, client):
        """Hybrid search combines keyword and vector."""
        res = client.post("/search?query=power+requirements&k=5&mode=hybrid&rag=false")
        assert res.status_code == 200
        data = res.json()
        assert len(data["hits"]) > 0

    def test_search_respects_k(self, client):
        """K parameter limits result count."""
        res = client.post("/search?query=interface&k=3&mode=rrf&rag=false")
        data = res.json()
        assert len(data["hits"]) <= 3

    def test_search_empty_query(self, client):
        """Empty query returns a valid (possibly empty) response."""
        res = client.post("/search?query=&k=5&mode=keyword&rag=false")
        # Should not crash
        assert res.status_code in (200, 400, 422)


@pytest.mark.skipif(not opensearch_available(), reason="OpenSearch not running")
class TestRAG:
    """RAG (Retrieval-Augmented Generation) endpoint."""

    def test_rag_returns_answer(self, client):
        """POST /search with rag=true returns a synthesized answer."""
        res = client.post(
            "/search?query=What+are+the+thermal+operating+limits&k=5&mode=rrf&rag=true"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["type"] == "rag"
        assert "answer" in data
        assert len(data["answer"]) > 20  # Non-trivial answer

    def test_rag_has_citations(self, client):
        """RAG answers include citations."""
        res = client.post(
            "/search?query=Who+is+responsible+for+thermal+design&k=5&mode=rrf&rag=true"
        )
        data = res.json()
        assert "citations" in data
        assert len(data["citations"]) > 0

    def test_rag_citation_structure(self, client):
        """Each citation has required fields."""
        res = client.post(
            "/search?query=heater+specifications&k=5&mode=rrf&rag=true"
        )
        data = res.json()
        for citation in data["citations"]:
            assert "label" in citation
            assert "document_title" in citation
            assert "page_number" in citation
            assert citation["page_number"] > 0

    def test_rag_has_confidence(self, client):
        """RAG response includes confidence indicator."""
        res = client.post(
            "/search?query=spectrometer+mass&k=5&mode=rrf&rag=true"
        )
        data = res.json()
        assert "confidence" in data
        assert data["confidence"] in ("high", "medium", "low")

    def test_rag_has_cost_and_timing(self, client):
        """RAG response includes cost and timing metadata."""
        res = client.post(
            "/search?query=data+rate&k=5&mode=rrf&rag=true"
        )
        data = res.json()
        assert "cost_usd" in data
        assert "time_ms" in data
        assert data["cost_usd"] >= 0
        assert data["time_ms"] > 0

    def test_rag_warnings_field(self, client):
        """RAG response includes warnings array."""
        res = client.post(
            "/search?query=what+is+TBD&k=5&mode=rrf&rag=true"
        )
        data = res.json()
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
