"""Search pipeline orchestrator.

Ties together: document ingestion → chunking → embedding → indexing → search.
Also orchestrates the eval harness for continuous benchmarking.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import ALL_CONFIGS, IndexConfig, SearchConfig
from .chunking import chunk_document, ChunkResult
from .embeddings import EmbeddingClient
from .eval_harness import EvalHarness, EvalRun
from .ground_truth import get_all_ground_truth
from .indexing import IndexManager
from .model_registry import ModelRegistry
from .retrieval import HybridSearcher, RetrievalMode, SearchResult

logger = logging.getLogger(__name__)


class SearchPipeline:
    """High-level search pipeline operations.

    This is the main interface for:
    1. Indexing documents from Document IR
    2. Searching across the corpus
    3. Running evaluation benchmarks
    4. Checking for new/deprecated models
    """

    def __init__(self, config: SearchConfig | None = None,
                 region: str = "us-east-1") -> None:
        self.config = config or SearchConfig(aws_region=region)
        self.index_manager = IndexManager(self.config)
        self.registry = ModelRegistry(region=region)
        self._eval_dir = Path("tests/results/search_eval")

    # -----------------------------------------------------------------
    # Document indexing
    # -----------------------------------------------------------------

    def ingest_document(self, ir_path: str | Path,
                        configs: list[IndexConfig] | None = None) -> dict[str, int]:
        """Ingest a Document IR file into all configured search indices.

        Args:
            ir_path: Path to YAML Document IR file
            configs: Specific configs to index into (default: all)

        Returns:
            {index_name: chunks_indexed}
        """
        import yaml

        ir_path = Path(ir_path)
        with open(ir_path, encoding="utf-8") as f:
            doc_ir = yaml.safe_load(f)

        metadata = doc_ir.get("metadata", {})
        doc_hash = metadata.get("sha256", doc_ir.get("document_hash", ir_path.stem))
        doc_title = metadata.get("title", metadata.get("filename", ir_path.stem))
        pages = doc_ir.get("pages", [])

        logger.info(f"Ingesting {doc_title} ({len(pages)} pages)")

        target_configs = configs or ALL_CONFIGS
        results = {}

        for config in target_configs:
            # Ensure index exists
            index_name = self.index_manager.create_index(config)

            # Remove old data for this document (re-index support)
            self.index_manager.delete_document(index_name, doc_hash)

            # Chunk
            chunk_result = chunk_document(
                pages, doc_hash, doc_title, config.chunk_config
            )
            if not chunk_result.chunks:
                results[index_name] = 0
                continue

            # Embed
            embed_client = EmbeddingClient(
                config.embedding_config, region=self.config.aws_region
            )
            texts = [c.text for c in chunk_result.chunks]
            embeddings = embed_client.embed_texts(texts)

            # Index
            count = self.index_manager.index_chunks(
                index_name, chunk_result.chunks, embeddings
            )
            results[index_name] = count
            logger.info(
                f"  [{config.name}] {count} chunks indexed "
                f"(${embed_client.total_cost_usd:.4f})"
            )

        return results

    # -----------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------

    def search(self, query: str, k: int = 10,
               mode: RetrievalMode = RetrievalMode.HYBRID_RRF,
               config: IndexConfig | None = None,
               filters: dict[str, Any] | None = None) -> SearchResult:
        """Search across indexed ICD documents.

        Uses the best-performing config by default (from last eval run),
        or a specific config if provided.
        """
        target_config = config or self._get_best_config()
        embed_client = EmbeddingClient(
            target_config.embedding_config, region=self.config.aws_region
        )
        searcher = HybridSearcher(
            self.index_manager.client, embed_client, target_config
        )
        return searcher.search(query, k=k, mode=mode, filters=filters)

    def _get_best_config(self) -> IndexConfig:
        """Get the best-performing config from the last eval run."""
        harness = EvalHarness(self.config)
        previous = harness.load_previous_run(self._eval_dir)
        if previous and previous.best_config:
            # Find matching config
            config_name = previous.best_config.split("/")[0]
            for cfg in ALL_CONFIGS:
                if cfg.name == config_name:
                    return cfg
        # Default to first config
        return ALL_CONFIGS[0]

    # -----------------------------------------------------------------
    # Evaluation
    # -----------------------------------------------------------------

    def run_eval(self, k: int = 10,
                 configs: list[IndexConfig] | None = None) -> EvalRun:
        """Run full search evaluation benchmark.

        This is the key command for continuous improvement:
        1. Checks model availability (discovers new, flags deprecated)
        2. Runs all configs × modes × queries
        3. Compares to previous run
        4. Saves results for historical tracking
        """
        # Step 1: Check model availability
        report = self.registry.check_availability()
        if report.new_models:
            logger.info(f"New models found: {[m.model_id for m in report.new_models]}")
        if report.deprecated_models:
            logger.warning(
                f"Deprecated models: {[m.model_id for m in report.deprecated_models]}"
            )

        # Step 2: Run evaluation
        target_configs = configs or ALL_CONFIGS
        harness = EvalHarness(self.config, configs=target_configs)
        run = harness.evaluate(k=k)

        # Step 3: Compare to previous
        previous = harness.load_previous_run(self._eval_dir)
        comparison = harness.compare_runs(run, previous)
        logger.info(comparison)

        # Step 4: Save
        harness.save_run(run, self._eval_dir)

        # Step 5: Mark models as benchmarked
        for cfg in target_configs:
            self.registry.mark_benchmarked(cfg.embedding_config.provider.value)

        return run

    def check_models(self) -> str:
        """Check for new/deprecated embedding models. Returns summary."""
        report = self.registry.check_availability()
        return report.summary()

    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Get current search pipeline status."""
        indices = []
        try:
            index_names = self.index_manager.list_indices()
            for name in index_names:
                stats = self.index_manager.get_index_stats(name)
                indices.append(stats)
        except Exception as e:
            logger.warning(f"Could not get index stats: {e}")

        # Last eval run
        harness = EvalHarness(self.config)
        last_run = harness.load_previous_run(self._eval_dir)

        return {
            "indices": indices,
            "total_documents_indexed": sum(i.get("doc_count", 0) for i in indices),
            "configured_models": len(ALL_CONFIGS),
            "last_eval_run": last_run.run_id if last_run else None,
            "best_config": last_run.best_config if last_run else None,
            "best_recall": last_run.best_recall if last_run else None,
        }
