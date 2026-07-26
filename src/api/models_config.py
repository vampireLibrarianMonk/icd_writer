"""Model configuration and cost tracking.

Central place for all model selections, pricing, and usage tracking
across the application. Models can be swapped here without touching
pipeline code.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Configuration for all AI/ML models used in the pipeline."""

    # OCR - Primary text extraction
    textract_enabled: bool = True

    # OCR - Diagram label backup
    rekognition_enabled: bool = True

    # Page classification
    classification_model: str = "us.amazon.nova-lite-v1:0"
    classification_enabled: bool = True

    # Disambiguation (conflict resolution)
    disambiguation_model: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    disambiguation_enabled: bool = True

    # Embeddings (for future search)
    embedding_model: str = "amazon.titan-embed-text-v2:0"
    embedding_dimensions: int = 1024

    # AWS region
    region: str = "us-east-1"


# Pricing per operation (USD, as of 2026-07)
PRICING_TABLE = {
    "textract": {
        "detect_document_text": {
            "cost_per_call": 0.0015,
            "unit": "page",
            "description": "Extract words and lines from a page image",
        },
        "analyze_document": {
            "cost_per_call": 0.015,
            "unit": "page",
            "description": "Extract tables and forms (10x more expensive)",
        },
    },
    "rekognition": {
        "detect_text": {
            "cost_per_call": 0.001,
            "unit": "image",
            "description": "Detect text in diagram/figure regions",
        },
    },
    "bedrock": {
        "us.amazon.nova-lite-v1:0": {
            "input_per_1k_tokens": 0.00006,
            "output_per_1k_tokens": 0.00025,
            "description": "Page classification (fast, cheap)",
        },
        "us.anthropic.claude-sonnet-4-20250514-v1:0": {
            "input_per_1k_tokens": 0.003,
            "output_per_1k_tokens": 0.015,
            "description": "Disambiguation and conflict resolution",
        },
        "amazon.titan-embed-text-v2:0": {
            "input_per_1k_tokens": 0.00002,
            "output_per_1k_tokens": 0.0,
            "description": "Text embeddings for semantic search",
        },
    },
    "weasyprint": {
        "render_page": {
            "cost_per_call": 0.0,
            "unit": "page",
            "description": "Local HTML→PDF rendering (free, compute only)",
        },
    },
}


# Available models the user can select from
AVAILABLE_MODELS = {
    "classification": {
        "us.amazon.nova-lite-v1:0": {
            "name": "Amazon Nova Lite",
            "speed": "fast",
            "cost": "very low",
            "quality": "good",
            "notes": "Default. Best cost/speed for page type detection.",
        },
        "us.amazon.nova-pro-v1:0": {
            "name": "Amazon Nova Pro",
            "speed": "medium",
            "cost": "moderate",
            "quality": "better",
            "notes": "More accurate on complex layouts.",
        },
    },
    "disambiguation": {
        "us.anthropic.claude-sonnet-4-20250514-v1:0": {
            "name": "Claude Sonnet 4",
            "speed": "medium",
            "cost": "moderate",
            "quality": "excellent",
            "notes": "Default. Best accuracy for OCR conflict resolution.",
        },
        "us.anthropic.claude-haiku-3-20250414-v1:0": {
            "name": "Claude Haiku 3",
            "speed": "fast",
            "cost": "low",
            "quality": "good",
            "notes": "Faster/cheaper, slightly less accurate.",
        },
        "us.amazon.nova-lite-v1:0": {
            "name": "Amazon Nova Lite",
            "speed": "fast",
            "cost": "very low",
            "quality": "adequate",
            "notes": "Budget option. May struggle with ambiguous text.",
        },
    },
    "embedding": {
        "amazon.titan-embed-text-v2:0": {
            "name": "Amazon Titan Embeddings V2",
            "dimensions": 1024,
            "cost": "very low",
            "notes": "Default. Data stays in AWS.",
        },
        "cohere.embed-english-v3": {
            "name": "Cohere Embed V3",
            "dimensions": 1024,
            "cost": "low",
            "notes": "Higher quality for technical text.",
        },
    },
}


def estimate_document_cost(
    page_count: int,
    has_tables: int = 0,
    has_diagrams: int = 0,
    config: ModelConfig | None = None,
) -> dict[str, float]:
    """Estimate the cost to process a document before running.

    Args:
        page_count: Total pages in the document.
        has_tables: Number of pages expected to have tables.
        has_diagrams: Number of pages expected to have diagrams.
        config: Model configuration (uses defaults if None).

    Returns:
        Dict with per-service costs and total.
    """
    if config is None:
        config = ModelConfig()

    costs = {}

    # Textract: every page gets text detection
    if config.textract_enabled:
        costs["textract_text"] = page_count * 0.0015
        costs["textract_tables"] = has_tables * 0.015

    # Rekognition: only diagram pages
    if config.rekognition_enabled:
        costs["rekognition"] = has_diagrams * 0.001

    # Bedrock classification: every page
    if config.classification_enabled:
        # ~1000 input tokens (image) + ~100 output per page
        per_page = 1000 * 0.00006 / 1000 + 100 * 0.00025 / 1000
        costs["bedrock_classify"] = page_count * per_page

    # Bedrock disambiguation: assume 5% of pages have conflicts
    if config.disambiguation_enabled:
        conflict_pages = max(1, int(page_count * 0.05))
        per_call = 1500 * 0.003 / 1000 + 50 * 0.015 / 1000
        costs["bedrock_disambiguate"] = conflict_pages * per_call

    costs["total"] = sum(costs.values())
    return costs
