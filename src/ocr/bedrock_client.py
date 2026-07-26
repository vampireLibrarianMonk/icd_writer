"""Bedrock vision client for page classification and disambiguation.

Uses Claude or Nova vision models to:
- Classify page content (text, table, diagram, mixed)
- Identify diagram regions vs text regions
- Resolve ambiguous OCR output
- Determine font sizes from visual analysis
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

from src.ocr.cost_tracker import CostTracker


@dataclass
class PageClassificationResult:
    """Result of Bedrock vision page classification."""

    page_number: int
    page_type: str  # "text", "table", "diagram", "mixed", "image_only"
    has_tables: bool = False
    has_diagrams: bool = False
    diagram_regions: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )  # bboxes of diagram areas
    estimated_font_sizes: dict[str, float] = field(
        default_factory=dict
    )  # region -> estimated pt size
    confidence: float = 0.0
    model: str = ""


def classify_page(
    image_bytes: bytes,
    page_number: int,
    page_width_pt: float,
    page_height_pt: float,
    cost_tracker: CostTracker,
    model_id: str = "us.amazon.nova-lite-v1:0",
    region: str = "us-east-1",
) -> PageClassificationResult:
    """Classify a page using Bedrock vision to determine content type.

    Uses a lightweight model (Nova Lite) for fast/cheap classification.
    """
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region)

    prompt = """Analyze this document page image. Respond in JSON format only.

Determine:
1. page_type: one of "text", "table", "diagram", "mixed", "image_only"
2. has_tables: true/false
3. has_diagrams: true/false  
4. diagram_regions: list of [x_percent, y_percent, width_percent, height_percent] for each diagram area (coordinates as 0-100 percentage of page)
5. estimated_body_font_size_pt: estimated main body text font size in points

Respond with ONLY valid JSON, no explanation."""

    b64_image = base64.b64encode(image_bytes).decode("ascii")

    body = json.dumps(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "png",
                                "source": {"bytes": b64_image},
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ],
            "inferenceConfig": {
                "maxTokens": 500,
                "temperature": 0.0,
            },
        }
    )

    response = client.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())

    # Extract token counts for cost tracking
    usage = response_body.get("usage", {})
    tokens_in = usage.get("inputTokens", 1000)
    tokens_out = usage.get("outputTokens", 100)

    cost_tracker.record(
        service="bedrock",
        operation="nova_lite_vision",
        page=page_number,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )

    # Parse response
    output_text = ""
    for content in response_body.get("output", {}).get("message", {}).get("content", []):
        if "text" in content:
            output_text = content["text"]
            break

    result = PageClassificationResult(
        page_number=page_number, page_type="text", model=model_id
    )

    try:
        parsed = json.loads(output_text)
        result.page_type = parsed.get("page_type", "text")
        result.has_tables = parsed.get("has_tables", False)
        result.has_diagrams = parsed.get("has_diagrams", False)
        result.confidence = 0.9  # Model gave structured response

        # Convert diagram regions from percentages to points
        for region_pct in parsed.get("diagram_regions", []):
            if len(region_pct) == 4:
                try:
                    x = float(region_pct[0]) / 100 * page_width_pt
                    y = float(region_pct[1]) / 100 * page_height_pt
                    w = float(region_pct[2]) / 100 * page_width_pt
                    h = float(region_pct[3]) / 100 * page_height_pt
                    result.diagram_regions.append((x, y, x + w, y + h))
                except (ValueError, TypeError):
                    pass

        body_size = parsed.get("estimated_body_font_size_pt", 11.0)
        result.estimated_font_sizes["body"] = body_size

    except (json.JSONDecodeError, KeyError):
        result.page_type = "text"
        result.confidence = 0.3  # Failed to parse

    return result


def disambiguate_text(
    image_bytes: bytes,
    candidate_texts: list[str],
    region_bbox: tuple[float, float, float, float],
    page_number: int,
    cost_tracker: CostTracker,
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0",
    region: str = "us-east-1",
) -> tuple[str, float]:
    """Use Claude vision to resolve ambiguous OCR results.

    When Textract and Rekognition disagree on a text region,
    send the image crop to Claude for a tiebreaker.

    Returns:
        Tuple of (best_text, confidence).
    """
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region)

    candidates_str = "\n".join(f"- '{t}'" for t in candidate_texts)
    prompt = f"""Look at this document image. Multiple OCR systems detected different text in a specific region.

The candidates are:
{candidates_str}

Which text is correct? Respond with ONLY the correct text, nothing else."""

    b64_image = base64.b64encode(image_bytes).decode("ascii")

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 100,
            "temperature": 0.0,
        }
    )

    response = client.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())

    usage = response_body.get("usage", {})
    tokens_in = usage.get("input_tokens", 1500)
    tokens_out = usage.get("output_tokens", 20)

    cost_tracker.record(
        service="bedrock",
        operation="claude_sonnet_vision",
        page=page_number,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )

    result_text = ""
    for content in response_body.get("content", []):
        if content.get("type") == "text":
            result_text = content["text"].strip()
            break

    # Match against candidates
    confidence = 0.95 if result_text in candidate_texts else 0.7
    return result_text, confidence
