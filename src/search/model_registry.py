"""Model registry and availability checker.

This is the apparatus for continuously tracking which models are available,
which are deprecated, and which new ones should be benchmarked.

Key behaviors:
1. Probes Bedrock for available embedding models on each eval run
2. Compares against known registry — flags new models for benchmarking
3. Detects deprecated/unavailable models — flags for removal from active config
4. Generates a report of model availability changes since last check
5. Auto-generates IndexConfig entries for newly discovered models

Usage:
    registry = ModelRegistry(region="us-east-1")
    report = registry.check_availability()
    if report.new_models:
        print(f"New models to benchmark: {report.new_models}")
    if report.deprecated_models:
        print(f"Deprecated — switch away from: {report.deprecated_models}")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .config import (
    ALL_CONFIGS,
    ChunkConfig,
    ChunkStrategy,
    EmbeddingConfig,
    EmbeddingProvider,
    IndexConfig,
    SimilarityMetric,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a Bedrock embedding model."""

    model_id: str
    model_name: str
    provider: str
    available: bool = True
    dimensions: int | None = None
    max_tokens: int | None = None
    cost_per_1k_tokens: float | None = None
    # When we first saw this model
    first_seen: str = ""
    # When it was last confirmed available
    last_checked: str = ""
    # Whether we've already benchmarked it
    benchmarked: bool = False
    # If deprecated, when
    deprecated_date: str | None = None


@dataclass
class AvailabilityReport:
    """Result of checking model availability."""

    timestamp: str
    region: str
    # Models we know about
    known_models: list[ModelInfo]
    # Changes since last check
    new_models: list[ModelInfo] = field(default_factory=list)
    deprecated_models: list[ModelInfo] = field(default_factory=list)
    # Models available but not yet benchmarked
    unbenchmarked: list[ModelInfo] = field(default_factory=list)
    # Current recommendation
    recommended_model: str | None = None

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Model Availability Report ({self.timestamp})",
            f"Region: {self.region}",
            f"Known embedding models: {len(self.known_models)}",
            f"  Available: {sum(1 for m in self.known_models if m.available)}",
            f"  Deprecated: {sum(1 for m in self.known_models if not m.available)}",
        ]
        if self.new_models:
            lines.append(f"\n🆕 New models ({len(self.new_models)}):")
            for m in self.new_models:
                lines.append(f"  - {m.model_id} ({m.provider})")
        if self.deprecated_models:
            lines.append(f"\n⚠️  Deprecated ({len(self.deprecated_models)}):")
            for m in self.deprecated_models:
                lines.append(f"  - {m.model_id}")
        if self.unbenchmarked:
            lines.append(f"\n📊 Needs benchmarking ({len(self.unbenchmarked)}):")
            for m in self.unbenchmarked:
                lines.append(f"  - {m.model_id}")
        if self.recommended_model:
            lines.append(f"\n🏆 Recommended: {self.recommended_model}")
        return "\n".join(lines)


# Known embedding models on Bedrock (updated as we discover them)
KNOWN_EMBEDDING_MODELS: dict[str, dict[str, Any]] = {
    "amazon.titan-embed-text-v2:0": {
        "provider": "Amazon",
        "dimensions": 1024,
        "max_tokens": 8192,
        "cost_per_1k_tokens": 0.0001,
    },
    "amazon.titan-embed-text-v1": {
        "provider": "Amazon",
        "dimensions": 1536,
        "max_tokens": 8192,
        "cost_per_1k_tokens": 0.0001,
    },
    "cohere.embed-english-v3": {
        "provider": "Cohere",
        "dimensions": 1024,
        "max_tokens": 512,
        "cost_per_1k_tokens": 0.0001,
    },
    "cohere.embed-multilingual-v3": {
        "provider": "Cohere",
        "dimensions": 1024,
        "max_tokens": 512,
        "cost_per_1k_tokens": 0.0001,
    },
}


class ModelRegistry:
    """Tracks embedding model availability and generates benchmark configs."""

    def __init__(self, region: str = "us-east-1",
                 registry_path: str | Path | None = None) -> None:
        self.region = region
        self.registry_path = Path(registry_path) if registry_path else Path(
            "tests/results/search_eval/model_registry.json"
        )
        self._bedrock_client = boto3.client("bedrock", region_name=region)
        self._known_models: dict[str, ModelInfo] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load previously saved registry state."""
        if self.registry_path.exists():
            data = json.loads(self.registry_path.read_text())
            for model_data in data.get("models", []):
                info = ModelInfo(**model_data)
                self._known_models[info.model_id] = info
        else:
            # Initialize from static knowledge
            now = datetime.now(timezone.utc).isoformat()
            for model_id, meta in KNOWN_EMBEDDING_MODELS.items():
                self._known_models[model_id] = ModelInfo(
                    model_id=model_id,
                    model_name=model_id.split(".")[-1],
                    provider=meta["provider"],
                    dimensions=meta.get("dimensions"),
                    max_tokens=meta.get("max_tokens"),
                    cost_per_1k_tokens=meta.get("cost_per_1k_tokens"),
                    first_seen=now,
                    last_checked=now,
                )

    def save_registry(self) -> None:
        """Persist registry state."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "region": self.region,
            "models": [
                {
                    "model_id": m.model_id,
                    "model_name": m.model_name,
                    "provider": m.provider,
                    "available": m.available,
                    "dimensions": m.dimensions,
                    "max_tokens": m.max_tokens,
                    "cost_per_1k_tokens": m.cost_per_1k_tokens,
                    "first_seen": m.first_seen,
                    "last_checked": m.last_checked,
                    "benchmarked": m.benchmarked,
                    "deprecated_date": m.deprecated_date,
                }
                for m in self._known_models.values()
            ],
        }
        self.registry_path.write_text(json.dumps(data, indent=2))

    def check_availability(self) -> AvailabilityReport:
        """Probe Bedrock for current embedding model availability.

        This is the key function — call it before each eval run to detect
        new and deprecated models.
        """
        now = datetime.now(timezone.utc).isoformat()
        new_models: list[ModelInfo] = []
        deprecated_models: list[ModelInfo] = []

        # List all foundation models with embedding output modality
        try:
            response = self._bedrock_client.list_foundation_models(
                byOutputModality="EMBEDDING"
            )
            available_ids = set()
            for model_summary in response.get("modelSummaries", []):
                model_id = model_summary.get("modelId", "")
                if not model_id:
                    continue
                available_ids.add(model_id)

                if model_id not in self._known_models:
                    # New model discovered!
                    info = ModelInfo(
                        model_id=model_id,
                        model_name=model_summary.get("modelName", model_id),
                        provider=model_summary.get("providerName", "Unknown"),
                        available=True,
                        first_seen=now,
                        last_checked=now,
                        benchmarked=False,
                    )
                    # Try to get dimensions from model details
                    self._enrich_model_info(info)
                    self._known_models[model_id] = info
                    new_models.append(info)
                    logger.info(f"🆕 New embedding model: {model_id}")
                else:
                    # Update last_checked
                    self._known_models[model_id].last_checked = now
                    self._known_models[model_id].available = True

            # Check for deprecated models
            for model_id, info in self._known_models.items():
                if model_id not in available_ids and info.available:
                    info.available = False
                    info.deprecated_date = now
                    deprecated_models.append(info)
                    logger.warning(f"⚠️  Model deprecated: {model_id}")

        except ClientError as e:
            logger.error(f"Failed to list Bedrock models: {e}")
            # Return current state without changes
            pass

        # Find unbenchmarked models
        unbenchmarked = [
            m for m in self._known_models.values()
            if m.available and not m.benchmarked
        ]

        # Save updated registry
        self.save_registry()

        return AvailabilityReport(
            timestamp=now,
            region=self.region,
            known_models=list(self._known_models.values()),
            new_models=new_models,
            deprecated_models=deprecated_models,
            unbenchmarked=unbenchmarked,
        )

    def _enrich_model_info(self, info: ModelInfo) -> None:
        """Try to get additional model details from Bedrock."""
        try:
            response = self._bedrock_client.get_foundation_model(
                modelIdentifier=info.model_id
            )
            details = response.get("modelDetails", {})
            # Extract what we can
            input_modalities = details.get("inputModalities", [])
            output_modalities = details.get("outputModalities", [])
            logger.debug(
                f"Model {info.model_id}: in={input_modalities}, out={output_modalities}"
            )
        except ClientError:
            pass

    def generate_configs_for_model(self, model_id: str) -> list[IndexConfig]:
        """Generate benchmark IndexConfigs for a newly discovered model.

        Creates one config per chunking strategy so the eval harness
        can determine optimal chunking for this model.
        """
        info = self._known_models.get(model_id)
        if not info:
            raise ValueError(f"Unknown model: {model_id}")

        # Determine dimensions (default to 1024 if unknown)
        dims = info.dimensions or 1024

        # Map to EmbeddingProvider enum or create dynamic config
        provider = None
        for ep in EmbeddingProvider:
            if ep.value == model_id:
                provider = ep
                break

        if provider is None:
            # Model not in our enum yet — log for manual addition
            logger.warning(
                f"Model {model_id} not in EmbeddingProvider enum. "
                f"Add it to config.py to enable benchmarking."
            )
            return []

        configs = []
        strategies = [
            ChunkStrategy.PARAGRAPH,
            ChunkStrategy.SECTION,
            ChunkStrategy.SLIDING_WINDOW,
        ]

        for strategy in strategies:
            model_short = model_id.split(".")[-1].split(":")[0]
            config = IndexConfig(
                name=f"{model_short}-{strategy.value}",
                embedding_config=EmbeddingConfig(
                    provider=provider,
                    dimensions=dims,
                    cost_per_1k_tokens=info.cost_per_1k_tokens or 0.0001,
                ),
                chunk_config=ChunkConfig(
                    strategy=strategy,
                    max_tokens=min(info.max_tokens or 512, 1024),
                ),
            )
            configs.append(config)

        return configs

    def mark_benchmarked(self, model_id: str) -> None:
        """Mark a model as benchmarked after eval run."""
        if model_id in self._known_models:
            self._known_models[model_id].benchmarked = True
            self.save_registry()

    def get_active_models(self) -> list[ModelInfo]:
        """Get all currently available models."""
        return [m for m in self._known_models.values() if m.available]

    def get_deprecated_models(self) -> list[ModelInfo]:
        """Get all deprecated models (may still be in active configs)."""
        return [m for m in self._known_models.values() if not m.available]
