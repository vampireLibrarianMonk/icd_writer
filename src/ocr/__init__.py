"""OCR ingestion pipeline for scanned/flattened PDFs.

Parallel path to the native extraction pipeline. Uses cloud-based OCR
models (AWS Textract, Rekognition, Bedrock vision) to recover text,
positions, and structure from image-only PDFs. Produces the same
Document IR that the native pipeline produces.

Architecture:
    Scanned PDF
        → Page images extracted
        → Textract (words + lines + tables)
        → Rekognition (diagram labels, low-confidence backup)
        → Bedrock vision (page classification, layout, disambiguation)
        → Ensemble resolution (confidence, majority vote, human flag)
        → Document IR (same schema as native extraction)
        → Rendering pipeline (unchanged)

No local GPU required — all inference is API-based.
"""

from src.ocr.pipeline import ocr_ingest
from src.ocr.cost_tracker import CostTracker

__all__ = ["ocr_ingest", "CostTracker"]
