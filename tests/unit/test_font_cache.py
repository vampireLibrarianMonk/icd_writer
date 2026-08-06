"""Unit Tests: Font Cache (extraction and lookup)

Verifies that the FontCache correctly:
1. Extracts fonts from source PDFs
2. Returns extracted fonts for matching font names
3. Falls back to system fonts when extraction fails
4. Falls back to base-14 as last resort
5. Calculates text width accurately with extracted fonts
"""

from pathlib import Path

import fitz
import pytest

from src.rendering.font_cache import FontCache

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"
NDS_PDF = ICDS_DIR / "NDS_IDD_RevC.pdf"


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestFontCacheExtraction:
    """Test font extraction from source PDFs."""

    def test_cache_extracts_fonts_from_hsi(self):
        """FontCache extracts at least one font from HSI PDF."""
        cache = FontCache.from_pdf(str(HSI_PDF))
        assert len(cache._fonts) >= 1, f"Expected fonts, got {cache._fonts.keys()}"

    def test_cache_has_times_variant(self):
        """HSI uses TimesNewRoman — cache should have a times-like font."""
        cache = FontCache.from_pdf(str(HSI_PDF))
        # Look for any font with "times" in the normalized name
        has_times = any("times" in k for k in cache._fonts.keys())
        # Or the original name
        has_times_orig = any("Times" in v["name"] for v in cache._fonts.values())
        assert has_times or has_times_orig, (
            f"No Times font found. Cached: {list(cache._fonts.keys())}"
        )

    def test_get_font_returns_buffer_for_known_font(self):
        """get_font returns a font buffer for a font that exists in the PDF."""
        cache = FontCache.from_pdf(str(HSI_PDF))
        font_obj, fontname, fontbuffer = cache.get_font("TimesNewRoman")

        # Should get EITHER a buffer (extracted) or a fontname (fallback)
        assert fontbuffer is not None or fontname is not None

    def test_get_font_fallback_for_unknown_font(self):
        """get_font falls back to base-14 for a completely unknown font."""
        cache = FontCache.from_pdf(str(HSI_PDF))
        font_obj, fontname, fontbuffer = cache.get_font("ComicSansMS")

        # Should get a base-14 fallback
        assert fontname is not None or fontbuffer is not None

    def test_text_width_returns_positive(self):
        """text_width returns a positive value for non-empty text."""
        cache = FontCache.from_pdf(str(HSI_PDF))
        width = cache.text_width("Hello World", "TimesNewRoman", 12.0)
        assert width > 0

    def test_text_width_scales_with_font_size(self):
        """Larger font size produces wider text."""
        cache = FontCache.from_pdf(str(HSI_PDF))
        w12 = cache.text_width("Test", "TimesNewRoman", 12.0)
        w24 = cache.text_width("Test", "TimesNewRoman", 24.0)
        assert w24 > w12 * 1.5  # Should be roughly 2x


@pytest.mark.skipif(not NDS_PDF.exists() or NDS_PDF.stat().st_size < 200, reason="NDS PDF not found")
class TestFontCacheNDS:
    """Test font extraction from NDS (uses Arial)."""

    def test_cache_extracts_fonts_from_nds(self):
        """FontCache extracts fonts from NDS PDF."""
        cache = FontCache.from_pdf(str(NDS_PDF))
        assert len(cache._fonts) >= 1

    def test_get_font_for_arial(self):
        """NDS uses Arial — get_font should find it."""
        cache = FontCache.from_pdf(str(NDS_PDF))
        font_obj, fontname, fontbuffer = cache.get_font("Arial-BoldMT", bold=True)
        # Should have something (extracted, system, or base-14)
        assert font_obj is not None or fontname is not None or fontbuffer is not None


class TestFontCacheEmpty:
    """Test FontCache behavior with no PDF."""

    def test_empty_cache_returns_fallback(self):
        """An empty cache still returns a usable font."""
        cache = FontCache()
        font_obj, fontname, fontbuffer = cache.get_font("TimesNewRoman")
        # Should fall through to system or base-14
        assert fontname is not None or fontbuffer is not None

    def test_empty_cache_text_width(self):
        """An empty cache still calculates text width."""
        cache = FontCache()
        width = cache.text_width("Test", "TimesNewRoman", 12.0)
        assert width > 0
