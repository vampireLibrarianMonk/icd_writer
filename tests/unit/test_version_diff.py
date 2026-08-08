"""Tests for document version detection and differential analysis (Phase 6).

Tests version family detection, quick comparison, full structured diff,
and report generation using real ICD revision pairs.
"""

from pathlib import Path

import pytest

from src.version_diff import (
    DiffReport,
    DocumentFamily,
    SectionDiff,
    detect_families,
    full_diff,
    generate_report,
    normalize_stem,
    quick_compare,
)

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
IDSS_E = ICDS_DIR / "digital" / "IDSS_IDD_RevE.pdf"
IDSS_F = ICDS_DIR / "digital" / "IDSS_IDD_RevF.pdf"
HSI_DIGITAL = ICDS_DIR / "digital" / "HSI_SYS_015G.pdf"
HSI_FLAT = ICDS_DIR / "flat" / "HSI_SYS_015G_flattened.pdf"

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"


# -----------------------------------------------------------------
# Filename normalization
# -----------------------------------------------------------------

class TestNormalizeStem:
    """Filename stem normalization for family detection."""

    def test_strip_flat_suffix(self):
        assert normalize_stem("HSI_SYS_015G_flattened.pdf") == "hsi_sys_015"

    def test_strip_rev_suffix(self):
        assert normalize_stem("IDSS_IDD_RevF.pdf") == "idss_idd"
        assert normalize_stem("IDSS_IDD_RevE.pdf") == "idss_idd"

    def test_strip_version_suffix(self):
        assert normalize_stem("document_v2.pdf") == "document"

    def test_plain_name_unchanged(self):
        assert normalize_stem("20150010976.pdf") == "20150010976"

    def test_case_insensitive(self):
        assert normalize_stem("Doc_REVA.pdf") == "doc"

    def test_strip_date_suffix(self):
        assert normalize_stem("report_20240315.pdf") == "report"


# -----------------------------------------------------------------
# Family detection
# -----------------------------------------------------------------

class TestFamilyDetection:
    """Detecting related document versions."""

    def test_detects_families(self):
        """Finds document families from the test corpus."""
        families = detect_families(scan_dirs=[ICDS_DIR / "digital", ICDS_DIR / "flat"])
        assert len(families) >= 2  # At least IDSS pair + digital/flat pairs

    def test_idss_family_detected(self):
        """IDSS Rev E and Rev F grouped together."""
        families = detect_families(scan_dirs=[ICDS_DIR / "digital", ICDS_DIR / "flat"])
        idss_family = next((f for f in families if "idss" in f.base_name), None)
        assert idss_family is not None
        assert len(idss_family.versions) >= 2
        revisions = {v.revision for v in idss_family.versions if v.revision}
        assert "E" in revisions
        assert "F" in revisions

    def test_family_status_page_count_differs(self):
        """IDSS family correctly flagged as page_count_differs."""
        families = detect_families(scan_dirs=[ICDS_DIR / "digital", ICDS_DIR / "flat"])
        idss_family = next((f for f in families if "idss" in f.base_name), None)
        assert idss_family is not None
        assert idss_family.status == "page_count_differs"

    def test_digital_flat_pair_detected(self):
        """Digital and flattened versions of same doc grouped."""
        families = detect_families(scan_dirs=[ICDS_DIR / "digital", ICDS_DIR / "flat"])
        hsi_015_family = next((f for f in families if "hsi_sys_015" in f.base_name), None)
        assert hsi_015_family is not None
        types = {v.doc_type for v in hsi_015_family.versions}
        assert "digital" in types
        assert "flattened" in types

    def test_versions_have_metadata(self):
        """Each detected version has page count and type."""
        families = detect_families()
        for family in families:
            for version in family.versions:
                assert version.page_count > 0
                assert version.doc_type in ("digital", "flattened")
                assert version.path


# -----------------------------------------------------------------
# Quick comparison
# -----------------------------------------------------------------

@pytest.mark.skipif(not IDSS_E.exists() or not IDSS_F.exists(), reason="IDSS PDFs not found")
class TestQuickCompare:
    """Fast metadata comparison between versions."""

    def test_quick_compare_returns_structure(self):
        result = quick_compare(IDSS_E, IDSS_F)
        assert "pages_a" in result
        assert "pages_b" in result
        assert "first_page_overlap" in result
        assert "likely_related" in result

    def test_page_counts_correct(self):
        result = quick_compare(IDSS_E, IDSS_F)
        assert result["pages_a"] == 142
        assert result["pages_b"] == 70
        assert result["page_count_match"] is False

    def test_identifies_as_related(self):
        result = quick_compare(IDSS_E, IDSS_F)
        assert result["likely_related"] is True

    def test_extracts_revisions(self):
        result = quick_compare(IDSS_E, IDSS_F)
        assert result["revision_a"] == "E"
        assert result["revision_b"] == "F"

    def test_overlap_is_meaningful(self):
        """Related docs should have >30% first-page overlap."""
        result = quick_compare(IDSS_E, IDSS_F)
        assert result["first_page_overlap"] > 0.3


# -----------------------------------------------------------------
# Full structured diff
# -----------------------------------------------------------------

@pytest.mark.skipif(not IDSS_E.exists() or not IDSS_F.exists(), reason="IDSS PDFs not found")
class TestFullDiff:
    """Full section-by-section differential analysis."""

    @pytest.fixture
    def report(self):
        return full_diff(IDSS_E, IDSS_F)

    def test_returns_diff_report(self, report):
        assert isinstance(report, DiffReport)
        assert report.version_a.filename == "IDSS_IDD_RevE.pdf"
        assert report.version_b.filename == "IDSS_IDD_RevF.pdf"

    def test_detects_modifications(self, report):
        assert report.sections_modified > 0

    def test_detects_additions(self, report):
        """Rev F has new content not in Rev E."""
        assert report.sections_added > 0

    def test_detects_removals(self, report):
        """Rev F removed significant content from Rev E (142→70 pages)."""
        assert report.sections_removed > 0

    def test_detects_requirement_changes(self, report):
        """Finds sections where shall/must language changed."""
        assert report.requirement_changes > 0
        req_diffs = [d for d in report.diffs if d.has_requirement_change]
        assert len(req_diffs) > 0

    def test_text_overlap_reasonable(self, report):
        """Same document → should have >30% overlap even with major revision."""
        assert report.text_overlap > 0.3

    def test_diff_tokens_computed(self, report):
        """Token count available for LLM budget estimation."""
        assert report.total_diff_tokens > 0

    def test_diffs_have_classification(self, report):
        """Each diff has a classification."""
        for diff in report.diffs:
            assert diff.classification in ("editorial", "technical", "structural")
            assert diff.change_type in ("modified", "added", "removed")

    def test_diffs_have_text_content(self, report):
        """Modified diffs have old and new text."""
        modified = [d for d in report.diffs if d.change_type == "modified"]
        assert len(modified) > 0
        for diff in modified[:5]:
            assert diff.old_text or diff.new_text


# -----------------------------------------------------------------
# Report generation
# -----------------------------------------------------------------

@pytest.mark.skipif(not IDSS_E.exists() or not IDSS_F.exists(), reason="IDSS PDFs not found")
class TestReportGeneration:
    """Report export in multiple formats."""

    @pytest.fixture
    def report(self):
        return full_diff(IDSS_E, IDSS_F)

    def test_markdown_format(self, report):
        md = generate_report(report, format="markdown")
        assert "# Document Version Differential Report" in md
        assert "## Summary" in md
        assert "## Changes" in md
        assert report.version_a.filename in md
        assert report.version_b.filename in md

    def test_text_format(self, report):
        txt = generate_report(report, format="text")
        assert "DOCUMENT VERSION DIFFERENTIAL REPORT" in txt
        assert "SUMMARY" in txt
        assert "CHANGES" in txt

    def test_html_format(self, report):
        html = generate_report(report, format="html")
        assert "<html>" in html
        assert "Differential Report" in html
        assert "</html>" in html

    def test_report_includes_stats(self, report):
        md = generate_report(report, format="markdown")
        assert f"Sections modified: {report.sections_modified}" in md
        assert f"Sections added: {report.sections_added}" in md

    def test_report_flags_requirements(self, report):
        md = generate_report(report, format="markdown")
        assert "⚠️" in md  # Requirement changes flagged


# -----------------------------------------------------------------
# Same-content comparison (digital vs flat)
# -----------------------------------------------------------------

@pytest.mark.skipif(not HSI_DIGITAL.exists() or not HSI_FLAT.exists(),
                    reason="HSI digital/flat pair not found")
class TestSameContentComparison:
    """Comparing digital vs flattened version of same document."""

    def test_quick_compare_same_pages(self):
        result = quick_compare(HSI_DIGITAL, HSI_FLAT)
        assert result["pages_a"] == result["pages_b"] == 8
        assert result["page_count_match"] is True

    def test_detected_as_related(self):
        result = quick_compare(HSI_DIGITAL, HSI_FLAT)
        assert result["likely_related"] is True
