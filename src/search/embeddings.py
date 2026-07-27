"""Embedding client — abstracts over Bedrock embedding models.

Supports multiple providers. Each model is called through the same interface
so the eval harness can swap them freely.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3

from .config import EmbeddingConfig, EmbeddingProvider

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Generate embeddings via AWS Bedrock."""

    def __init__(self, config: EmbeddingConfig, region: str = "us-east-1") -> None:
        self.config = config
        self.region = region
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._total_tokens = 0
        self._total_calls = 0

    @property
    def total_cost_usd(self) -> float:
        """Estimated cost so far."""
        return (self._total_tokens / 1000) * self.config.cost_per_1k_tokens

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "model": self.config.provider.value,
            "total_calls": self._total_calls,
            "total_tokens": self._total_tokens,
            "estimated_cost_usd": round(self.total_cost_usd, 6),
        }

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of vectors.

        Note: Bedrock embedding models have per-call limits.
        Titan V2 supports up to 8192 tokens per text, batch of 1.
        Cohere supports batches of up to 96 texts.
        """
        if self.config.provider in (
            EmbeddingProvider.COHERE_ENGLISH,
            EmbeddingProvider.COHERE_MULTILINGUAL,
        ):
            return self._embed_cohere(texts)
        else:
            return self._embed_titan(texts)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text. Returns one vector."""
        results = self.embed_texts([text])
        return results[0]

    def _embed_titan(self, texts: list[str]) -> list[list[float]]:
        """Embed using Amazon Titan Text Embeddings V2."""
        vectors: list[list[float]] = []
        for text in texts:
            body = {
                "inputText": text,
                "dimensions": self.config.dimensions,
                "normalize": self.config.normalize,
            }
            response = self._client.invoke_model(
                modelId=self.config.provider.value,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            vectors.append(result["embedding"])
            self._total_tokens += result.get("inputTextTokenCount", len(text.split()))
            self._total_calls += 1
        return vectors

    def _embed_cohere(self, texts: list[str]) -> list[list[float]]:
        """Embed using Cohere Embed models (supports batching)."""
        vectors: list[list[float]] = []
        # Cohere supports batches of 96, with max 2048 chars per text
        batch_size = 96
        max_chars = 2048
        for i in range(0, len(texts), batch_size):
            batch = [t[:max_chars] for t in texts[i:i + batch_size]]
            body = {
                "texts": batch,
                "input_type": "search_document",
                "truncate": "END",
            }
            response = self._client.invoke_model(
                modelId=self.config.provider.value,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            vectors.extend(result["embeddings"])
            # Cohere doesn't return token counts directly
            token_est = sum(len(t.split()) for t in batch)
            self._total_tokens += token_est
            self._total_calls += 1
        return vectors

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query.

        Cohere distinguishes between document and query embeddings.
        Titan uses the same model for both.
        """
        if self.config.provider in (
            EmbeddingProvider.COHERE_ENGLISH,
            EmbeddingProvider.COHERE_MULTILINGUAL,
        ):
            body = {
                "texts": [query],
                "input_type": "search_query",
                "truncate": "END",
            }
            response = self._client.invoke_model(
                modelId=self.config.provider.value,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            self._total_tokens += len(query.split())
            self._total_calls += 1
            return result["embeddings"][0]
        else:
            return self.embed_text(query)
