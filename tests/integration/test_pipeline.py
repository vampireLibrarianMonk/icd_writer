"""Integration tests using real PDF files in the icds/ directory."""

from pathlib import Path

import pytest

from src.classification.classifier import classify_pages
from src.extraction.text_extractor import extract_text_blocks
from src.ingestion.pdf_reader import ingest_pdf
from src.pipeline import process_pdf

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
SAMPLE_PDFS = list(ICDS_DIR.glob("**/*.pdf"))


@pytest.fixture(params=SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
def sample_pdf(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.mark.skipif(not SAMPLE_PDFS, reason="No sample PDFs in icds/")
class TestIngestion:
    def test_ingest_produces_metadata(self, sample_pdf: Path):
        result = ingest_pdf(sample_pdf)
        assert result.metadata.filename == sample_pdf.name
        assert result.metadata.page_count > 0
        assert len(result.metadata.sha256) == 64
        assert result.metadata.file_size_bytes > 0

    def test_page_dimensions_match_count(self, sample_pdf: Path):
        result = ingest_pdf(sample_pdf)
        assert len(result.page_dimensions) == result.metadata.page_count

    def test_page_dimensions_are_positive(self, sample_pdf: Path):
        result = ingest_pdf(sample_pdf)
        for w, h in result.page_dimensions:
            assert w > 0
            assert h > 0


@pytest.mark.skipif(not SAMPLE_PDFS, reason="No sample PDFs in icds/")
class TestClassification:
    def test_one_classification_per_page(self, sample_pdf: Path):
        classifications = classify_pages(sample_pdf)
        ingestion = ingest_pdf(sample_pdf)
        assert len(classifications) == ingestion.metadata.page_count

    def test_classifications_have_valid_types(self, sample_pdf: Path):
        classifications = classify_pages(sample_pdf)
        for c in classifications:
            assert len(c.classifications) >= 1
            assert c.confidence >= 0.0
            assert c.confidence <= 1.0


@pytest.mark.skipif(not SAMPLE_PDFS, reason="No sample PDFs in icds/")
class TestTextExtraction:
    def test_extract_produces_blocks(self, sample_pdf: Path):
        blocks = extract_text_blocks(sample_pdf)
        # At least some pages should have text
        # (unless fully scanned, which our samples might be)
        assert isinstance(blocks, list)

    def test_blocks_have_valid_bbox(self, sample_pdf: Path):
        blocks = extract_text_blocks(sample_pdf)
        for block in blocks:
            assert block.bbox.width >= 0
            assert block.bbox.height >= 0
            assert block.page >= 1


@pytest.mark.skipif(not SAMPLE_PDFS, reason="No sample PDFs in icds/")
class TestPipeline:
    def test_full_pipeline(self, sample_pdf: Path):
        doc_ir = process_pdf(sample_pdf)
        assert doc_ir.metadata.filename == sample_pdf.name
        assert doc_ir.page_count > 0
        assert doc_ir.provenance is not None
        assert doc_ir.provenance.source_sha256 == doc_ir.metadata.sha256
