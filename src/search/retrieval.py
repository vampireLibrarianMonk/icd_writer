"""Hybrid search — combines BM25 keyword search with kNN vector similarity.

Supports multiple retrieval modes:
- keyword_only: BM25 text search
- vector_only: kNN nearest neighbor
- hybrid: combined score (configurable boost)
- hybrid_rrf: Reciprocal Rank Fusion (position-based, no score normalization needed)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from opensearchpy import OpenSearch

from .config import IndexConfig
from .embeddings import EmbeddingClient


class RetrievalMode(str, Enum):
    """How to retrieve results."""

    KEYWORD_ONLY = "keyword_only"
    VECTOR_ONLY = "vector_only"
    HYBRID = "hybrid"
    HYBRID_RRF = "hybrid_rrf"  # Reciprocal Rank Fusion


@dataclass
class SearchHit:
    """A single search result."""

    chunk_id: str
    text: str
    score: float
    document_hash: str
    document_title: str
    page_number: int
    section_heading: str | None = None
    section_number: str | None = None
    content_type: str = "paragraph"
    metadata: dict[str, Any] = field(default_factory=dict)
    # For eval: which retrieval mode produced this hit
    source: str = ""


@dataclass
class SearchResult:
    """Complete search result set."""

    query: str
    mode: RetrievalMode
    hits: list[SearchHit]
    total_hits: int = 0
    took_ms: int = 0
    index_name: str = ""
    # For eval comparison
    config_name: str = ""


class HybridSearcher:
    """Execute searches against an OpenSearch index."""

    def __init__(self, client: OpenSearch, embedding_client: EmbeddingClient,
                 index_config: IndexConfig) -> None:
        self.client = client
        self.embedding_client = embedding_client
        self.index_config = index_config
        self.index_name = index_config.index_name

    def search(self, query: str, k: int = 10,
               mode: RetrievalMode = RetrievalMode.HYBRID,
               filters: dict[str, Any] | None = None) -> SearchResult:
        """Execute a search query.

        Args:
            query: Natural language search query
            k: Number of results to return
            mode: Retrieval mode (keyword, vector, hybrid, RRF)
            filters: Optional field filters (e.g., {"content_type": "requirement"})
        """
        if mode == RetrievalMode.KEYWORD_ONLY:
            return self._keyword_search(query, k, filters)
        elif mode == RetrievalMode.VECTOR_ONLY:
            return self._vector_search(query, k, filters)
        elif mode == RetrievalMode.HYBRID:
            return self._hybrid_search(query, k, filters)
        elif mode == RetrievalMode.HYBRID_RRF:
            return self._hybrid_rrf(query, k, filters)
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def _keyword_search(self, query: str, k: int,
                        filters: dict[str, Any] | None) -> SearchResult:
        """BM25 text search."""
        must = [{"match": {"text": {"query": query, "operator": "or"}}}]
        filter_clauses = self._build_filters(filters)

        body: dict[str, Any] = {
            "size": k,
            "query": {
                "bool": {
                    "must": must,
                    "filter": filter_clauses,
                },
            },
        }

        response = self.client.search(index=self.index_name, body=body)
        return self._parse_response(response, query, RetrievalMode.KEYWORD_ONLY)

    def _vector_search(self, query: str, k: int,
                       filters: dict[str, Any] | None) -> SearchResult:
        """kNN vector similarity search."""
        query_vector = self.embedding_client.embed_query(query)
        filter_clauses = self._build_filters(filters)

        body: dict[str, Any] = {
            "size": k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_vector,
                        "k": k,
                    },
                },
            },
        }

        # Add filters if present
        if filter_clauses:
            body["query"] = {
                "bool": {
                    "must": [body["query"]],
                    "filter": filter_clauses,
                },
            }

        response = self.client.search(index=self.index_name, body=body)
        return self._parse_response(response, query, RetrievalMode.VECTOR_ONLY)

    def _hybrid_search(self, query: str, k: int,
                       filters: dict[str, Any] | None) -> SearchResult:
        """Combined BM25 + kNN with configurable boost."""
        query_vector = self.embedding_client.embed_query(query)
        filter_clauses = self._build_filters(filters)

        bm25_boost = self.index_config.bm25_boost
        knn_boost = self.index_config.knn_boost

        body: dict[str, Any] = {
            "size": k,
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "text": {
                                    "query": query,
                                    "boost": bm25_boost,
                                },
                            },
                        },
                        {
                            "knn": {
                                "embedding": {
                                    "vector": query_vector,
                                    "k": k,
                                    "boost": knn_boost,
                                },
                            },
                        },
                    ],
                    "filter": filter_clauses,
                },
            },
        }

        response = self.client.search(index=self.index_name, body=body)
        return self._parse_response(response, query, RetrievalMode.HYBRID)

    def _hybrid_rrf(self, query: str, k: int,
                    filters: dict[str, Any] | None) -> SearchResult:
        """Reciprocal Rank Fusion — position-based merging without score normalization.

        RRF formula: score(d) = sum(1 / (rank_i + K)) for each ranking list
        K=60 is the standard constant.
        """
        # Get both result sets (fetch more than k to have good fusion coverage)
        fetch_k = min(k * 3, 100)
        keyword_result = self._keyword_search(query, fetch_k, filters)
        vector_result = self._vector_search(query, fetch_k, filters)

        # RRF merge
        K = 60
        rrf_scores: dict[str, float] = {}
        hit_data: dict[str, SearchHit] = {}

        for rank, hit in enumerate(keyword_result.hits):
            rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0) + 1 / (rank + K)
            hit_data[hit.chunk_id] = hit

        for rank, hit in enumerate(vector_result.hits):
            rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0) + 1 / (rank + K)
            hit_data[hit.chunk_id] = hit

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        hits = []
        for chunk_id in sorted_ids[:k]:
            hit = hit_data[chunk_id]
            hit.score = rrf_scores[chunk_id]
            hit.source = "rrf"
            hits.append(hit)

        return SearchResult(
            query=query,
            mode=RetrievalMode.HYBRID_RRF,
            hits=hits,
            total_hits=len(sorted_ids),
            index_name=self.index_name,
            config_name=self.index_config.name,
        )

    def _build_filters(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Convert simple filter dict to OpenSearch filter clauses."""
        if not filters:
            return []
        clauses = []
        for field_name, value in filters.items():
            if isinstance(value, list):
                clauses.append({"terms": {field_name: value}})
            else:
                clauses.append({"term": {field_name: value}})
        return clauses

    def _parse_response(self, response: dict[str, Any], query: str,
                        mode: RetrievalMode) -> SearchResult:
        """Parse OpenSearch response into SearchResult."""
        hits_data = response.get("hits", {})
        took = response.get("took", 0)
        total = hits_data.get("total", {}).get("value", 0)

        hits: list[SearchHit] = []
        for hit in hits_data.get("hits", []):
            source = hit.get("_source", {})
            hits.append(SearchHit(
                chunk_id=source.get("chunk_id", hit.get("_id", "")),
                text=source.get("text", ""),
                score=hit.get("_score", 0.0),
                document_hash=source.get("document_hash", ""),
                document_title=source.get("document_title", ""),
                page_number=source.get("page_number", 0),
                section_heading=source.get("section_heading"),
                section_number=source.get("section_number"),
                content_type=source.get("content_type", "paragraph"),
                metadata=source.get("metadata", {}),
                source=mode.value,
            ))

        return SearchResult(
            query=query,
            mode=mode,
            hits=hits,
            total_hits=total,
            took_ms=took,
            index_name=self.index_name,
            config_name=self.index_config.name,
        )
