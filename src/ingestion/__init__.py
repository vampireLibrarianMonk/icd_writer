"""PDF Ingestion module.

Handles reading PDF files, computing hashes, extracting metadata,
and preparing documents for the classification and extraction pipeline.
"""

from src.ingestion.pdf_reader import PdfIngestionResult, ingest_pdf

__all__ = ["PdfIngestionResult", "ingest_pdf"]
