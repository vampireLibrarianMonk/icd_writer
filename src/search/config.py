"""Search pipeline configuration.

Defines embedding models, chunking strategies, and index configurations
as swappable components. New models are added here — the evaluation harness
picks them up automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""

    TITAN_V2 = "amazon.titan-embed-text-v2:0"
    TITAN_V1 = "amazon.titan-embed-text-v1"
    COHERE_ENGLISH = "cohere.embed-english-v3"
    COHERE_MULTILINGUAL = "cohere.embed-multilingual-v3"
    # Add new models here as they become available on Bedrock
    # The eval harness will automatically benchmark them


class ChunkStrategy(str, Enum):
    """Document chunking strategies."""

    FIXED_WORDS = "fixed_words"  # Fixed word-count windows
    PARAGRAPH = "paragraph"  # Natural paragraph boundaries from IR
    SECTION = "section"  # Full ICD sections (heading → next heading)
    SLIDING_WINDOW = "sliding_window"  # Overlapping word windows
    SEMANTIC = "semantic"  # Bedrock-assisted boundary detection


class SimilarityMetric(str, Enum):
    """Vector similarity metrics for kNN."""

    COSINE = "cosinesimil"
    L2 = "l2"
    INNER_PRODUCT = "innerproduct"


@dataclass
class ChunkConfig:
    """Configuration for a chunking strategy."""

    strategy: ChunkStrategy
    max_tokens: int = 512
    overlap_tokens: int = 64
    # For section-based: include heading in each chunk
    include_heading: bool = True
    # For semantic: model used to detect boundaries
    boundary_model: str | None = None


@dataclass
class EmbeddingConfig:
    """Configuration for an embedding model."""

    provider: EmbeddingProvider
    dimensions: int = 1024  # Titan V2 default
    normalize: bool = True
    # Cost per 1K tokens (for tracking)
    cost_per_1k_tokens: float = 0.0001


@dataclass
class IndexConfig:
    """OpenSearch index configuration."""

    name: str
    embedding_config: EmbeddingConfig
    chunk_config: ChunkConfig
    similarity_metric: SimilarityMetric = SimilarityMetric.COSINE
    # kNN engine settings
    ef_construction: int = 512
    m: int = 16
    # BM25 settings for hybrid
    bm25_boost: float = 1.0
    knn_boost: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def index_name(self) -> str:
        """Generate deterministic index name from config."""
        model_short = self.embedding_config.provider.value.split(".")[-1].split(":")[0]
        chunk_short = self.chunk_config.strategy.value
        return f"icd-{model_short}-{chunk_short}-{self.embedding_config.dimensions}d"


@dataclass
class SearchConfig:
    """Top-level search pipeline configuration."""

    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_scheme: str = "https"
    # AWS OpenSearch Service (None = local Docker)
    opensearch_domain: str | None = None
    aws_region: str = "us-east-1"
    # Active configurations to maintain
    active_indices: list[IndexConfig] = field(default_factory=list)
    # Default retrieval settings
    default_k: int = 10
    rerank: bool = False


# -----------------------------------------------------------------
# Predefined configurations for benchmarking
# -----------------------------------------------------------------

TITAN_V2_PARAGRAPH = IndexConfig(
    name="titan-v2-paragraph",
    embedding_config=EmbeddingConfig(
        provider=EmbeddingProvider.TITAN_V2,
        dimensions=1024,
        cost_per_1k_tokens=0.0001,
    ),
    chunk_config=ChunkConfig(
        strategy=ChunkStrategy.PARAGRAPH,
        max_tokens=512,
    ),
)

TITAN_V2_SECTION = IndexConfig(
    name="titan-v2-section",
    embedding_config=EmbeddingConfig(
        provider=EmbeddingProvider.TITAN_V2,
        dimensions=1024,
        cost_per_1k_tokens=0.0001,
    ),
    chunk_config=ChunkConfig(
        strategy=ChunkStrategy.SECTION,
        max_tokens=1024,
        include_heading=True,
    ),
)

TITAN_V2_SLIDING = IndexConfig(
    name="titan-v2-sliding",
    embedding_config=EmbeddingConfig(
        provider=EmbeddingProvider.TITAN_V2,
        dimensions=1024,
        cost_per_1k_tokens=0.0001,
    ),
    chunk_config=ChunkConfig(
        strategy=ChunkStrategy.SLIDING_WINDOW,
        max_tokens=256,
        overlap_tokens=64,
    ),
)

COHERE_ENGLISH_PARAGRAPH = IndexConfig(
    name="cohere-en-paragraph",
    embedding_config=EmbeddingConfig(
        provider=EmbeddingProvider.COHERE_ENGLISH,
        dimensions=1024,
        cost_per_1k_tokens=0.0001,
    ),
    chunk_config=ChunkConfig(
        strategy=ChunkStrategy.PARAGRAPH,
        max_tokens=512,
    ),
)

# Registry of all known configurations — eval harness iterates this
ALL_CONFIGS: list[IndexConfig] = [
    TITAN_V2_PARAGRAPH,
    TITAN_V2_SECTION,
    TITAN_V2_SLIDING,
    COHERE_ENGLISH_PARAGRAPH,
]
