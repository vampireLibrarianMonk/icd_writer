"""Text accuracy tests — verify regenerated PDFs preserve original text content."""

from pathlib import Path

import fitz
import pytest

from src.rendering import render_page_to_pdf

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
SAMPLE_PDFS = list(ICDS_DIR.glob("*.pdf"))


@pytest.fixture(params=SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
def sample_pdf(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.mark.skipif(not SAMPLE_PDFS, reason="No sample PDFs in icds/")
class TestTextAccuracy:
    def test_text_preserved_on_page_1(self, sample_pdf: Path, tmp_path: Path):
        """Verify page 1 text content is preserved through the pipeline."""
        output_path = tmp_path / "page1.pdf"
        render_page_to_pdf(sample_pdf, page_number=1, output_path=output_path)

        orig = fitz.open(str(sample_pdf))
        regen = fitz.open(str(output_path))

        orig_text = " ".join(orig[0].get_text("text").split())
        regen_text = " ".join(regen[0].get_text("text").split())

        orig.close()
        regen.close()

        # All non-whitespace text should be present
        assert orig_text == regen_text, (
            f"Text mismatch on page 1. "
            f"Original: {len(orig_text)} chars, Regen: {len(regen_text)} chars"
        )

    def test_no_text_lost_across_pages(self, sample_pdf: Path, tmp_path: Path):
        """Verify no text content is lost (ignoring extra whitespace).

        Checks that at least 95% of unique words from the original appear
        in the regenerated version. Some words may be lost if they are
        rendered as part of images or hidden by z-order in the original.
        """
        orig = fitz.open(str(sample_pdf))

        # Test first 5 pages (to keep test fast)
        pages_to_test = min(5, len(orig))

        total_words = 0
        found_words = 0

        for page_idx in range(pages_to_test):
            page_num = page_idx + 1
            output_path = tmp_path / f"page{page_num}.pdf"
            render_page_to_pdf(sample_pdf, page_number=page_num, output_path=output_path)

            regen = fitz.open(str(output_path))

            orig_text = " ".join(orig[page_idx].get_text("text").split())
            regen_text = " ".join(regen[0].get_text("text").split())

            regen.close()

            orig_words = set(orig_text.split())
            regen_words = set(regen_text.split())
            total_words += len(orig_words)
            found_words += len(orig_words & regen_words)

        orig.close()

        word_retention = found_words / total_words * 100 if total_words > 0 else 100
        assert word_retention >= 95.0, (
            f"Word retention too low: {word_retention:.1f}% "
            f"({found_words}/{total_words} unique words preserved)"
        )
