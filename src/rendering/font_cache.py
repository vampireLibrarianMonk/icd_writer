"""Font cache: extract and cache fonts from source PDFs for pixel-accurate text insertion.

When a document is opened, we extract all embedded fonts and cache them.
When inserting text (table rebuild, TOC add, header/footer edit), we use
the exact font from the source rather than a base-14 approximation.

Fallback chain:
1. Extracted font from the source PDF (exact match)
2. System font (Liberation/Windows fonts — metrically compatible)
3. Base-14 built-in (always available, slightly different metrics)
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)


class FontCache:
    """Cache of extracted fonts from a PDF document.

    Usage:
        cache = FontCache.from_pdf("document.pdf")
        font, fontname = cache.get_font("TimesNewRoman", bold=True)
        # font is a fitz.Font for width calculations
        # fontname is what to pass to page.insert_text(fontname=...)
        # OR fontfile path for page.insert_text(fontfile=...)
    """

    def __init__(self):
        self._fonts: dict[str, dict] = {}  # normalized_name -> {path, xref, buffer, ...}
        self._font_objects: dict[str, fitz.Font] = {}  # cache of fitz.Font instances

    @classmethod
    def from_pdf(cls, pdf_path: str | Path) -> "FontCache":
        """Extract all fonts from a PDF and build a cache."""
        cache = cls()
        try:
            doc = fitz.open(str(pdf_path))
            cache._extract_fonts(doc)
            doc.close()
        except Exception as e:
            logger.warning(f"Font extraction failed for {pdf_path}: {e}")
        return cache

    def _extract_fonts(self, doc: fitz.Document) -> None:
        """Extract embedded font data from all pages."""
        seen_xrefs = set()

        for page_idx in range(min(len(doc), 20)):  # Scan first 20 pages
            page = doc[page_idx]
            font_list = page.get_fonts(full=True)

            for font_info in font_list:
                xref = font_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                name = font_info[3]  # Base font name
                ext = font_info[4]   # Font type extension (ttf, cff, etc.)

                if not name:
                    continue

                try:
                    font_data = doc.extract_font(xref)
                    # extract_font returns (name, ext, subtype, content_bytes)
                    if isinstance(font_data, tuple) and len(font_data) >= 4:
                        f_name, f_ext, f_subtype, f_content = font_data[:4]
                    elif isinstance(font_data, dict):
                        f_name = font_data.get("name", name)
                        f_content = font_data.get("content", b"")
                        f_ext = font_data.get("ext", "")
                    else:
                        f_content = b""
                        f_name = name
                        f_ext = ext

                    norm_name = self._normalize_name(name)

                    if f_content:
                        # Font IS embedded — cache the actual bytes
                        self._fonts[norm_name] = {
                            "name": name,
                            "xref": xref,
                            "buffer": f_content,
                            "ext": f_ext,
                        }
                        logger.debug(f"Cached embedded font: {name} ({len(f_content)} bytes)")
                    else:
                        # Font is NOT embedded — record name for system font lookup
                        if norm_name not in self._fonts:
                            self._fonts[norm_name] = {
                                "name": name,
                                "xref": xref,
                                "buffer": None,
                                "ext": ext,
                            }
                            logger.debug(f"Recorded non-embedded font: {name}")

                except Exception as e:
                    logger.debug(f"Could not extract font xref={xref} ({name}): {e}")

    def get_font(
        self, font_name: str, bold: bool = False, italic: bool = False
    ) -> tuple[fitz.Font | None, str | None, bytes | None]:
        """Get the best available font for insertion.

        Returns:
            (font_object, fontname_or_none, fontbuffer_or_none)
            - font_object: fitz.Font for text_length calculations (may be None)
            - fontname_or_none: base-14 name to use with insert_text (fallback)
            - fontbuffer_or_none: raw font bytes to use with insert_text(fontbuffer=...)

        Usage:
            font, fontname, fontbuffer = cache.get_font("TimesNewRoman", bold=True)
            if fontbuffer:
                page.insert_text(pt, text, fontbuffer=fontbuffer, fontsize=sz)
            else:
                page.insert_text(pt, text, fontname=fontname, fontsize=sz)
        """
        # Try 1: Extracted font from PDF
        norm = self._normalize_name(font_name)
        # Try exact match, then with bold/italic variants
        candidates = [norm]
        if bold:
            candidates.insert(0, norm + ",bold")
            candidates.insert(0, norm + "-bold")
            candidates.insert(0, norm + "bold")
        if italic:
            candidates.insert(0, norm + ",italic")
            candidates.insert(0, norm + "-italic")
        if bold and italic:
            candidates.insert(0, norm + ",bolditalic")
            candidates.insert(0, norm + "-bolditalic")

        for candidate in candidates:
            if candidate in self._fonts:
                entry = self._fonts[candidate]
                if entry["buffer"]:
                    # Embedded font — use the actual bytes
                    font_obj = self._get_font_object_from_buffer(candidate, entry["buffer"])
                    return font_obj, None, entry["buffer"]
                # Non-embedded font — fall through to system font lookup

        # Also try partial match (font name contains the normalized key)
        for cached_name, entry in self._fonts.items():
            if entry["buffer"] and (norm in cached_name or cached_name in norm):
                font_obj = self._get_font_object_from_buffer(cached_name, entry["buffer"])
                return font_obj, None, entry["buffer"]

        # Try 2: System font (Liberation/Windows)
        from src.rendering.page_patch import _find_system_font
        sys_path = _find_system_font(font_name, bold, italic)
        if sys_path:
            try:
                font_obj = fitz.Font(fontfile=sys_path)
                return font_obj, None, Path(sys_path).read_bytes()
            except Exception:
                pass

        # Try 3: Base-14 fallback
        from src.rendering.page_patch import _get_pymupdf_fontname
        builtin = _get_pymupdf_fontname(font_name, bold, italic)
        try:
            font_obj = fitz.Font(fontname=builtin)
        except Exception:
            font_obj = None
        return font_obj, builtin, None

    def text_width(self, text: str, font_name: str, font_size: float,
                   bold: bool = False, italic: bool = False) -> float:
        """Calculate text width using the best available font."""
        font_obj, _, _ = self.get_font(font_name, bold, italic)
        if font_obj:
            return font_obj.text_length(text, fontsize=font_size)
        # Rough estimate
        return len(text) * font_size * 0.5

    def _get_font_object_from_buffer(self, key: str, buffer: bytes) -> fitz.Font | None:
        """Get or create a fitz.Font from cached buffer."""
        if key in self._font_objects:
            return self._font_objects[key]
        try:
            font = fitz.Font(fontbuffer=buffer)
            self._font_objects[key] = font
            return font
        except Exception:
            return None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a font name for lookup (lowercase, strip common suffixes)."""
        n = name.lower().replace(" ", "").replace("-", "").replace("_", "")
        # Remove common suffixes
        for suffix in ("mt", "ps", "regular", "roman"):
            if n.endswith(suffix):
                n = n[:-len(suffix)]
        return n

    def __repr__(self) -> str:
        return f"FontCache({len(self._fonts)} fonts cached)"
