"""AWS Rekognition client for diagram/label text detection.

Used as a secondary model for text detection in diagram regions
where Textract may miss small labels or rotated text.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.ocr.cost_tracker import CostTracker
from src.ocr.textract_client import OcrWord


def run_rekognition_text(
    image_bytes: bytes,
    page_number: int,
    page_width_pt: float,
    page_height_pt: float,
    cost_tracker: CostTracker,
    region: str = "us-east-1",
) -> list[OcrWord]:
    """Run Rekognition DetectText on a page image.

    Returns detected text with bounding boxes. Useful for:
    - Diagram labels that Textract misses
    - Rotated or curved text
    - Small text in figures
    """
    import boto3

    client = boto3.client("rekognition", region_name=region)

    response = client.detect_text(Image={"Bytes": image_bytes})

    cost_tracker.record(
        service="rekognition",
        operation="detect_text",
        page=page_number,
    )

    words: list[OcrWord] = []

    for detection in response.get("TextDetections", []):
        if detection.get("Type") != "WORD":
            continue

        text = detection.get("DetectedText", "")
        confidence = detection.get("Confidence", 0.0)
        bbox = detection.get("Geometry", {}).get("BoundingBox", {})

        x0 = bbox.get("Left", 0) * page_width_pt
        y0 = bbox.get("Top", 0) * page_height_pt
        w = bbox.get("Width", 0) * page_width_pt
        h = bbox.get("Height", 0) * page_height_pt

        words.append(
            OcrWord(
                text=text,
                x0=x0,
                y0=y0,
                x1=x0 + w,
                y1=y0 + h,
                confidence=confidence,
                source="rekognition",
            )
        )

    return words
