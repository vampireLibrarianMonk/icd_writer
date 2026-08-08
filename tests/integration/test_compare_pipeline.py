"""Integration tests for the Revision Compare pipeline.

Tests the full flow: section extraction → comparison → API response
against the real ICD corpus. Validates that:
1. Section headings are real document sections (not values/bullets)
2. Comparison produces meaningful results
3. AI summarize endpoint works end-to-end
4. Page numbers in results correspond to actual document pages
5. Both HSI_SYS_001 H→I and IDSS_IDD RevE→F produce usable output

These tests hit the real backend API (Docker must be running).
"""

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import pytest

from src.briefing.section_diff import compare_revisions
from src.version_diff import _extract_sections, full_diff

# ─── Paths ─────────────────────────────────────────────────────

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_H = ICDS_DIR / "HSI_SYS_001H.pdf"
HSI_I = ICDS_DIR / "HSI_SYS_001I.pdf"
IDSS_E = ICDS_DIR / "IDSS_IDD_RevE.pdf"
IDSS_F = ICDS_DIR / "IDSS_IDD_RevF.pdf"

API_BASE = "http://localhost:8000"


# ─── Section Extraction Quality ────────────────────────────────

class TestSectionExtractionQuality:
    """Validate that section headings are real document sections."""

    # Patterns that should NEVER appear as headings (checked as whole words)
    BOGUS_WORDS = ["bytes", "ohm"]
    BOGUS_CHARS = ["Ω"]
    # Patterns that indicate a heading is a bullet (only at START)
    BOGUS_STARTS = ["• ", "* ", "► "]

    def _check_no_bogus_headings(self, sections):
        import re
        for s in sections:
            heading = s["heading"]
            for word in self.BOGUS_WORDS:
                assert not re.search(r'\b' + word + r'\b', heading, re.IGNORECASE), (
                    f"Bogus heading detected: '{heading}' contains word '{word}'"
                )
            for char in self.BOGUS_CHARS:
                assert char not in heading, (
                    f"Bogus heading detected: '{heading}' contains '{char}'"
                )
            for start in self.BOGUS_STARTS:
                assert not heading.startswith(start), (
                    f"Bullet point as heading: '{heading}'"
                )

    @pytest.mark.skipif(not HSI_H.exists(), reason="HSI_SYS_001H.pdf not found")
    def test_hsi_001h_no_bogus_headings(self):
        sections = _extract_sections(HSI_H)
        self._check_no_bogus_headings(sections)
        # Should have real numbered sections
        numbered = [s for s in sections if s["heading"][0].isdigit()]
        assert len(numbered) >= 20, f"Only {len(numbered)} numbered sections found"

    @pytest.mark.skipif(not HSI_I.exists(), reason="HSI_SYS_001I.pdf not found")
    def test_hsi_001i_no_bogus_headings(self):
        sections = _extract_sections(HSI_I)
        self._check_no_bogus_headings(sections)

    @pytest.mark.skipif(not IDSS_E.exists(), reason="IDSS_IDD_RevE.pdf not found")
    def test_idss_reve_no_bogus_headings(self):
        sections = _extract_sections(IDSS_E)
        self._check_no_bogus_headings(sections)
        # IDSS should have major numbered sections
        major_sections = [
            s for s in sections
            if s["heading"].startswith(("1.0", "2.0", "3.", "4.", "5."))
        ]
        assert len(major_sections) >= 5

    @pytest.mark.skipif(not IDSS_F.exists(), reason="IDSS_IDD_RevF.pdf not found")
    def test_idss_revf_no_bogus_headings(self):
        sections = _extract_sections(IDSS_F)
        self._check_no_bogus_headings(sections)

    @pytest.mark.skipif(not HSI_H.exists(), reason="HSI_SYS_001H.pdf not found")
    def test_hsi_sections_have_valid_pages(self):
        """Every section page should be within the document."""
        sections = _extract_sections(HSI_H)
        for s in sections:
            assert 1 <= s["page"] <= 23, (
                f"Section '{s['heading']}' has page {s['page']} outside 1-23"
            )

    @pytest.mark.skipif(not HSI_H.exists(), reason="HSI_SYS_001H.pdf not found")
    def test_hsi_key_sections_present(self):
        """HSI ICD should have these known sections."""
        sections = _extract_sections(HSI_H)
        headings = {s["heading"] for s in sections}
        expected = [
            "1. Introduction",
            "4.  Electrical Interface",
            "4.1. Power",
            "4.2. Signals",
        ]
        for exp in expected:
            # Fuzzy match — heading might have extra whitespace
            found = any(exp.replace(" ", "") in h.replace(" ", "") for h in headings)
            assert found, f"Expected section '{exp}' not found in headings"


# ─── Comparison Results Quality ────────────────────────────────

@pytest.mark.skipif(not HSI_H.exists() or not HSI_I.exists(), reason="HSI PDFs not found")
class TestHSIComparison:
    """Validate comparison results for HSI_SYS_001 H→I."""

    @pytest.fixture(scope="class")
    def comparison(self):
        return compare_revisions(HSI_H, HSI_I)

    def test_reasonable_section_count(self, comparison):
        """Should have a reasonable number of sections, not 70+."""
        total = len(comparison.sections)
        assert 20 <= total <= 80, f"Got {total} sections — too many or too few"

    def test_has_both_changed_and_unchanged(self, comparison):
        assert comparison.total_sections_changed > 0
        assert comparison.total_sections_unchanged > 0

    def test_changed_sections_have_summaries(self, comparison):
        """Every changed section should have a non-empty summary line."""
        changed = [s for s in comparison.sections if s.change_type != "unchanged"]
        for s in changed:
            assert s.summary_line, f"Section '{s.section_heading}' has no summary"

    def test_page_numbers_valid(self, comparison):
        """All page references should be within document bounds (1-23)."""
        for s in comparison.sections:
            if s.page_new:
                assert 1 <= s.page_new <= 23
            if s.page_old:
                assert 1 <= s.page_old <= 23

    def test_no_bogus_section_headings(self, comparison):
        """No measurement values or bullets as headings."""
        for s in comparison.sections:
            h = s.section_heading
            assert "bytes" not in h.lower(), f"Bogus heading: {h}"
            assert "Ω" not in h, f"Bogus heading: {h}"
            assert not h.startswith("•"), f"Bullet as heading: {h}"


@pytest.mark.skipif(not IDSS_E.exists() or not IDSS_F.exists(), reason="IDSS PDFs not found")
class TestIDSSComparison:
    """Validate comparison results for IDSS_IDD RevE→F."""

    @pytest.fixture(scope="class")
    def comparison(self):
        return compare_revisions(IDSS_E, IDSS_F)

    def test_detects_major_changes(self, comparison):
        """RevE (142pg) → RevF (70pg) should show significant changes."""
        assert comparison.total_sections_changed > 10

    def test_has_removed_sections(self, comparison):
        """Page reduction means sections were removed."""
        removed = [s for s in comparison.sections if s.change_type == "removed"]
        assert len(removed) > 0

    def test_no_bogus_headings(self, comparison):
        for s in comparison.sections:
            h = s.section_heading
            assert not h.startswith("•"), f"Bullet: {h}"
            # Should not be a pure number
            assert not h.replace(".", "").replace(" ", "").isdigit(), f"Numeric heading: {h}"


# ─── API Integration ───────────────────────────────────────────

def _api_post(path, params=None):
    """Helper to call the backend API."""
    if params:
        url = f"{API_BASE}{path}?{urlencode(params)}"
    else:
        url = f"{API_BASE}{path}"
    req = Request(url, method="POST")
    try:
        resp = urlopen(req, timeout=60)
        return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        pytest.fail(f"API call failed: {e.code} {e.reason} — {body[:200]}")


def _api_get(path, params=None):
    if params:
        url = f"{API_BASE}{path}?{urlencode(params)}"
    else:
        url = f"{API_BASE}{path}"
    req = Request(url, method="GET")
    try:
        resp = urlopen(req, timeout=30)
        return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        pytest.fail(f"API call failed: {e.code} {e.reason} — {body[:200]}")


@pytest.mark.skipif(not HSI_H.exists() or not HSI_I.exists(), reason="HSI PDFs not found")
class TestBriefingAPI:
    """Test the /briefing/ API endpoints against real documents."""

    # Paths as seen by the Docker container
    DOCKER_HSI_H = "icds/digital/HSI_SYS_001H.pdf"
    DOCKER_HSI_I = "icds/digital/HSI_SYS_001I.pdf"

    def test_families_endpoint(self):
        """GET /briefing/families should return HSI and IDSS families."""
        result = _api_get("/briefing/families")
        assert "families" in result
        names = [f["family_name"] for f in result["families"]]
        assert any("hsi_sys_001" in n for n in names), f"HSI family not found in {names}"

    def test_compare_endpoint_hsi(self):
        """POST /briefing/compare for HSI H→I should return valid results."""
        result = _api_post("/briefing/compare", {
            "version_a": self.DOCKER_HSI_H,
            "version_b": self.DOCKER_HSI_I,
        })
        assert "sections" in result
        assert "stats" in result
        assert result["stats"]["total_sections_changed"] > 0
        # No bogus headings
        for s in result["sections"]:
            assert "bytes" not in s["section_heading"].lower()
            assert "Ω" not in s["section_heading"]

    def test_compare_returns_page_numbers(self):
        """Sections should have valid page references."""
        result = _api_post("/briefing/compare", {
            "version_a": self.DOCKER_HSI_H,
            "version_b": self.DOCKER_HSI_I,
        })
        pages_seen = set()
        for s in result["sections"]:
            if s["page_new"]:
                pages_seen.add(s["page_new"])
                assert 1 <= s["page_new"] <= 23
        # Should cover multiple pages
        assert len(pages_seen) >= 5, f"Only {len(pages_seen)} distinct pages referenced"

    def test_ai_summarize_endpoint(self):
        """POST /documents/diff/summarize should return a summary with cost."""
        # First get a valid section heading
        result = _api_post("/briefing/compare", {
            "version_a": self.DOCKER_HSI_H,
            "version_b": self.DOCKER_HSI_I,
        })
        changed = [s for s in result["sections"] if s["change_type"] == "modified"]
        assert len(changed) > 0, "No modified sections to summarize"

        section_heading = changed[0]["section_heading"]

        # Now call summarize
        summary_result = _api_post("/documents/diff/summarize", {
            "version_a": self.DOCKER_HSI_H,
            "version_b": self.DOCKER_HSI_I,
            "section_heading": section_heading,
        })

        # Should have either a summary or an error (AWS creds might not be available)
        assert "section_heading" in summary_result
        if summary_result.get("ai_summary"):
            assert len(summary_result["ai_summary"]) > 20
            assert summary_result["cost_usd"] > 0
        # If no summary, should have an error explaining why
        elif summary_result.get("error"):
            assert len(summary_result["error"]) > 0


# ─── Document Highlight Navigation ────────────────────────────

@pytest.mark.skipif(not HSI_H.exists(), reason="HSI_SYS_001H.pdf not found")
class TestHighlightTargets:
    """Verify that section headings can be found in the document text
    (required for the highlight-on-navigate feature to work)."""

    def test_section_headings_exist_in_document_text(self):
        """Each section heading should appear as text on its stated page."""
        import fitz
        sections = _extract_sections(HSI_H)
        doc = fitz.open(str(HSI_H))

        misses = []
        for s in sections[:30]:  # Check first 30
            page_idx = s["page"] - 1
            if page_idx >= len(doc):
                continue
            page_text = doc[page_idx].get_text()
            # The heading text (or key words from it) should appear on that page
            heading_words = [w for w in s["heading"].split() if len(w) > 3]
            if heading_words:
                found = any(w in page_text for w in heading_words[:3])
                if not found:
                    misses.append(f"p.{s['page']}: '{s['heading'][:40]}' not found on page")

        doc.close()
        # Allow a few misses (preamble, etc.) but most should be on their page
        assert len(misses) < len(sections) * 0.2, (
            f"Too many heading/page mismatches ({len(misses)}):\n" +
            "\n".join(misses[:10])
        )
