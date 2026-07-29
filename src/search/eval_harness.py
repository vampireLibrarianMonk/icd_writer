"""Search evaluation harness.

The core apparatus for continuous model/strategy evaluation. Scores every
configured (embedding model × chunking strategy × retrieval mode) combination
against the ground truth dataset, producing comparable metrics.

Run this whenever:
- A new embedding model becomes available on Bedrock
- You want to try a new chunking strategy
- You want to tune hybrid search boost parameters
- A model gets deprecated and you need to pick its successor

Metrics:
- Recall@K: fraction of relevant docs found in top K
- MRR (Mean Reciprocal Rank): average 1/rank of first relevant result
- nDCG@K: normalized Discounted Cumulative Gain
- Hit Rate: fraction of queries with at least one relevant result
- Latency (p50, p95)
- Cost per query (embedding API calls)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import IndexConfig, ALL_CONFIGS, SearchConfig
from .embeddings import EmbeddingClient
from .ground_truth import RelevanceJudgment, get_all_ground_truth
from .indexing import IndexManager
from .retrieval import HybridSearcher, RetrievalMode, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Metrics for a single query evaluation."""

    query_id: str
    query: str
    recall_at_k: float = 0.0
    reciprocal_rank: float = 0.0
    ndcg_at_k: float = 0.0
    hit: bool = False
    latency_ms: float = 0.0
    relevant_found: list[str] = field(default_factory=list)
    relevant_missed: list[str] = field(default_factory=list)


@dataclass
class ConfigMetrics:
    """Aggregated metrics for one configuration."""

    config_name: str
    index_name: str
    embedding_model: str
    chunk_strategy: str
    retrieval_mode: str
    # Aggregated
    mean_recall_at_k: float = 0.0
    mean_mrr: float = 0.0
    mean_ndcg_at_k: float = 0.0
    hit_rate: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    # Per-query breakdown
    query_metrics: list[QueryMetrics] = field(default_factory=list)
    # Category breakdown
    category_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class EvalRun:
    """A complete evaluation run across all configurations."""

    run_id: str
    timestamp: str
    k: int
    total_queries: int
    configs_evaluated: int
    results: list[ConfigMetrics]
    # Winner
    best_config: str = ""
    best_recall: float = 0.0
    # Comparison to previous run
    improvement_vs_previous: float | None = None

    def summary_table(self) -> str:
        """Format results as a comparison table."""
        lines = [
            f"Evaluation Run: {self.run_id} ({self.timestamp})",
            f"Queries: {self.total_queries}, K={self.k}",
            "",
            f"{'Config':<35} {'Recall@K':>9} {'MRR':>7} {'nDCG':>7} "
            f"{'Hit Rate':>9} {'p50ms':>7} {'Cost':>8}",
            "-" * 95,
        ]
        for r in sorted(self.results, key=lambda x: x.mean_recall_at_k, reverse=True):
            lines.append(
                f"{r.config_name:<35} {r.mean_recall_at_k:>8.1%} "
                f"{r.mean_mrr:>7.3f} {r.mean_ndcg_at_k:>7.3f} "
                f"{r.hit_rate:>8.1%} {r.p50_latency_ms:>6.0f} "
                f"${r.total_cost_usd:>7.4f}"
            )
        lines.append("")
        lines.append(f"🏆 Best: {self.best_config} (Recall@{self.k} = {self.best_recall:.1%})")
        return "\n".join(lines)


class EvalHarness:
    """Evaluation harness for search pipeline configurations.

    Usage:
        harness = EvalHarness(search_config)
        # Index documents first (one-time per config)
        harness.index_document(pages, doc_hash, doc_title)
        # Run evaluation
        run = harness.evaluate(k=10)
        print(run.summary_table())
        # Save results
        harness.save_run(run, "tests/results/search_eval/")
    """

    def __init__(self, search_config: SearchConfig,
                 configs: list[IndexConfig] | None = None,
                 modes: list[RetrievalMode] | None = None) -> None:
        self.search_config = search_config
        self.configs = configs or ALL_CONFIGS
        self.modes = modes or [
            RetrievalMode.KEYWORD_ONLY,
            RetrievalMode.VECTOR_ONLY,
            RetrievalMode.HYBRID,
            RetrievalMode.HYBRID_RRF,
        ]
        self.index_manager = IndexManager(search_config)
        self._embedding_clients: dict[str, EmbeddingClient] = {}

    def get_embedding_client(self, config: IndexConfig) -> EmbeddingClient:
        """Get or create embedding client for a config."""
        key = config.embedding_config.provider.value
        if key not in self._embedding_clients:
            self._embedding_clients[key] = EmbeddingClient(
                config.embedding_config,
                region=self.search_config.aws_region,
            )
        return self._embedding_clients[key]

    def setup_indices(self) -> list[str]:
        """Create all configured indices. Returns list of index names."""
        names = []
        for config in self.configs:
            name = self.index_manager.create_index(config)
            names.append(name)
        return names

    def index_document(self, pages: list[dict[str, Any]], doc_hash: str,
                       doc_title: str) -> dict[str, int]:
        """Index a document into all configured indices.

        Returns: {index_name: chunk_count}
        """
        from .chunking import chunk_document

        results = {}
        for config in self.configs:
            index_name = config.index_name

            # Chunk
            chunk_result = chunk_document(pages, doc_hash, doc_title, config.chunk_config)
            if not chunk_result.chunks:
                logger.warning(f"No chunks produced for {doc_title} with {config.name}")
                results[index_name] = 0
                continue

            # Embed
            embed_client = self.get_embedding_client(config)
            texts = [c.text for c in chunk_result.chunks]
            embeddings = embed_client.embed_texts(texts)

            # Index
            count = self.index_manager.index_chunks(
                index_name, chunk_result.chunks, embeddings
            )
            results[index_name] = count
            logger.info(
                f"  {config.name}: {count} chunks, "
                f"~{chunk_result.total_tokens_estimate} tokens, "
                f"${embed_client.total_cost_usd:.4f} embed cost"
            )

        return results

    def evaluate(self, k: int = 10,
                 ground_truth: list[RelevanceJudgment] | None = None) -> EvalRun:
        """Run full evaluation across all configs × all modes × all queries.

        This is the main entry point. Call after indexing documents.
        """
        queries = ground_truth or get_all_ground_truth()
        if not queries:
            raise ValueError("No ground truth queries defined")

        all_results: list[ConfigMetrics] = []
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        for config in self.configs:
            embed_client = self.get_embedding_client(config)
            searcher = HybridSearcher(
                self.index_manager.client, embed_client, config
            )

            for mode in self.modes:
                config_name = f"{config.name}/{mode.value}"
                query_metrics: list[QueryMetrics] = []

                for judgment in queries:
                    start = time.perf_counter()
                    try:
                        result = searcher.search(
                            judgment.query, k=k, mode=mode
                        )
                        latency = (time.perf_counter() - start) * 1000
                    except Exception as e:
                        logger.warning(f"Search failed for {config_name}: {e}")
                        query_metrics.append(QueryMetrics(
                            query_id=judgment.query_id,
                            query=judgment.query,
                            latency_ms=0,
                        ))
                        continue

                    # Score this query
                    qm = self._score_query(judgment, result, k, latency)
                    query_metrics.append(qm)

                # Aggregate
                cm = self._aggregate_metrics(
                    config_name, config, mode, query_metrics, embed_client
                )
                all_results.append(cm)

        # Find winner
        best = max(all_results, key=lambda x: x.mean_recall_at_k)

        return EvalRun(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            k=k,
            total_queries=len(queries),
            configs_evaluated=len(all_results),
            results=all_results,
            best_config=best.config_name,
            best_recall=best.mean_recall_at_k,
        )

    def _score_query(self, judgment: RelevanceJudgment, result: SearchResult,
                     k: int, latency_ms: float) -> QueryMetrics:
        """Score a single query against ground truth."""
        hit_texts = [h.text.lower() for h in result.hits[:k]]
        relevant_found = []
        relevant_missed = []

        for expected in judgment.relevant_texts:
            expected_lower = expected.lower()
            found = any(expected_lower in ht for ht in hit_texts)
            if found:
                relevant_found.append(expected)
            else:
                relevant_missed.append(expected)

        # Recall@K
        total_relevant = len(judgment.relevant_texts)
        recall = len(relevant_found) / total_relevant if total_relevant > 0 else 0.0

        # Reciprocal Rank (rank of first relevant hit)
        rr = 0.0
        for rank, ht in enumerate(hit_texts, 1):
            if any(exp.lower() in ht for exp in judgment.relevant_texts):
                rr = 1.0 / rank
                break

        # nDCG@K (binary relevance)
        import math
        dcg = 0.0
        for rank, ht in enumerate(hit_texts, 1):
            if any(exp.lower() in ht for exp in judgment.relevant_texts):
                dcg += 1.0 / math.log2(rank + 1)
        # Ideal DCG: all relevant docs at top
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(total_relevant, k)))
        ndcg = dcg / idcg if idcg > 0 else 0.0

        return QueryMetrics(
            query_id=judgment.query_id,
            query=judgment.query,
            recall_at_k=recall,
            reciprocal_rank=rr,
            ndcg_at_k=ndcg,
            hit=len(relevant_found) > 0,
            latency_ms=latency_ms,
            relevant_found=relevant_found,
            relevant_missed=relevant_missed,
        )

    def _aggregate_metrics(self, config_name: str, config: IndexConfig,
                           mode: RetrievalMode, query_metrics: list[QueryMetrics],
                           embed_client: EmbeddingClient) -> ConfigMetrics:
        """Aggregate per-query metrics into config-level metrics."""
        if not query_metrics:
            return ConfigMetrics(
                config_name=config_name,
                index_name=config.index_name,
                embedding_model=config.embedding_config.provider.value,
                chunk_strategy=config.chunk_config.strategy.value,
                retrieval_mode=mode.value,
            )

        n = len(query_metrics)
        latencies = sorted(qm.latency_ms for qm in query_metrics)

        return ConfigMetrics(
            config_name=config_name,
            index_name=config.index_name,
            embedding_model=config.embedding_config.provider.value,
            chunk_strategy=config.chunk_config.strategy.value,
            retrieval_mode=mode.value,
            mean_recall_at_k=sum(qm.recall_at_k for qm in query_metrics) / n,
            mean_mrr=sum(qm.reciprocal_rank for qm in query_metrics) / n,
            mean_ndcg_at_k=sum(qm.ndcg_at_k for qm in query_metrics) / n,
            hit_rate=sum(1 for qm in query_metrics if qm.hit) / n,
            p50_latency_ms=latencies[n // 2] if latencies else 0,
            p95_latency_ms=latencies[int(n * 0.95)] if len(latencies) > 1 else latencies[0] if latencies else 0,
            total_cost_usd=embed_client.total_cost_usd,
            query_metrics=query_metrics,
        )

    def save_run(self, run: EvalRun, output_dir: str | Path) -> Path:
        """Save evaluation run to JSON for historical comparison."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        filename = output_path / f"eval_{run.run_id}.json"

        # Serialize
        data = {
            "run_id": run.run_id,
            "timestamp": run.timestamp,
            "k": run.k,
            "total_queries": run.total_queries,
            "configs_evaluated": run.configs_evaluated,
            "best_config": run.best_config,
            "best_recall": run.best_recall,
            "results": [
                {
                    "config_name": r.config_name,
                    "embedding_model": r.embedding_model,
                    "chunk_strategy": r.chunk_strategy,
                    "retrieval_mode": r.retrieval_mode,
                    "mean_recall_at_k": r.mean_recall_at_k,
                    "mean_mrr": r.mean_mrr,
                    "mean_ndcg_at_k": r.mean_ndcg_at_k,
                    "hit_rate": r.hit_rate,
                    "p50_latency_ms": r.p50_latency_ms,
                    "p95_latency_ms": r.p95_latency_ms,
                    "total_cost_usd": r.total_cost_usd,
                }
                for r in run.results
            ],
        }
        filename.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"Saved eval run to {filename}")
        return filename

    def load_previous_run(self, output_dir: str | Path) -> EvalRun | None:
        """Load the most recent previous eval run for comparison."""
        output_path = Path(output_dir)
        if not output_path.exists():
            return None
        files = sorted(output_path.glob("eval_*.json"), reverse=True)
        if not files:
            return None
        data = json.loads(files[0].read_text(encoding="utf-8"))
        # Reconstruct minimal EvalRun for comparison
        return EvalRun(
            run_id=data["run_id"],
            timestamp=data["timestamp"],
            k=data["k"],
            total_queries=data["total_queries"],
            configs_evaluated=data["configs_evaluated"],
            results=[],
            best_config=data["best_config"],
            best_recall=data["best_recall"],
        )

    def compare_runs(self, current: EvalRun, previous: EvalRun | None) -> str:
        """Generate comparison summary between eval runs."""
        if not previous:
            return f"First evaluation run. Best: {current.best_config} ({current.best_recall:.1%})"

        delta = current.best_recall - previous.best_recall
        direction = "↑" if delta > 0 else "↓" if delta < 0 else "="
        return (
            f"Best: {current.best_config} ({current.best_recall:.1%}) "
            f"{direction} {abs(delta):.1%} vs previous "
            f"({previous.best_config}, {previous.best_recall:.1%})"
        )
