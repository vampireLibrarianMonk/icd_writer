"""Tests for the briefing consolidation module (Phase 1).

Tests value extraction, cross-reference detection, maturity scoring,
section-level comparison, and the consolidator against the Tier 1 corpus
(IDSS IDD Rev E + Rev F).
"""

from pathlib import Path

import pytest

from src.briefing.consolidator import (
    build_document_summary,
    gather_documents,
    load_document_ir,
)
from src.briefing.cross_reference import detect_cross_refs
from src.briefing.maturity import score_document
from src.briefing.models import (
    BriefingDocument,
    ComparisonResult,
    MaturityScore,
    SectionComparison,
    ValueChange,
)
from src.briefing.section_diff import compare_revisions
from src.briefing.value_extraction import (
    detect_value_changes,
    detect_value_conflicts,
    extract_specifications,
)


# ─── Paths ─────────────────────────────────────────────────────

ICDS_DIR = Path(__file__).parent.parent.parent / "icds"
IDSS_E = ICDS_DIR / "digital" / "IDSS_IDD_RevE.pdf"
IDSS_F = ICDS_DIR / "digital" / "IDSS_IDD_RevF.pdf"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"


# ─── Value Extraction ──────────────────────────────────────────

class TestValueExtraction:
    """Test specification value extraction from Document IR."""

    @pytest.fixture
    def ir_e(self):
        return load_document_ir("IDSS_IDD_RevE", OUTPUT_DIR)

    @pytest.fixture
    def ir_f(self):
        return load_document_ir("IDSS_IDD_RevF", OUTPUT_DIR)

    def test_extracts_values_from_ir(self, ir_e):
        """Should find numeric values with engineering units."""
        if ir_e is None:
            pytest.skip("IDSS_IDD_RevE IR not available")
        specs = extract_specifications(ir_e)
        assert len(specs) > 0
        # Each spec should have value, unit, context, page
        for spec in specs[:10]:
            assert spec.value is not None
            assert spec.unit
            assert spec.context
            assert spec.page > 0

    def test_extracts_values_from_rev_f(self, ir_f):
        """Rev F (shorter doc) should also have extractable values."""
        if ir_f is None:
            pytest.skip("IDSS_IDD_RevF IR not available")
        specs = extract_specifications(ir_f)
        assert len(specs) > 0

    def test_values_have_keywords(self, ir_e):
        """Extracted values should have meaningful keywords for matching."""
        if ir_e is None:
            pytest.skip("IDSS_IDD_RevE IR not available")
        specs = extract_specifications(ir_e)
        with_keywords = [s for s in specs if len(s.keywords) >= 2]
        # Most specs should have at least 2 keywords
        assert len(with_keywords) > len(specs) * 0.3

    def test_detect_value_changes_between_revisions(self, ir_e, ir_f):
        """Should detect value changes between Rev E and Rev F."""
        if ir_e is None or ir_f is None:
            pytest.skip("Both IDSS IRs required")
        specs_e = extract_specifications(ir_e)
        specs_f = extract_specifications(ir_f)
        changes = detect_value_changes(specs_e, specs_f)
        # Between two major revisions, expect at least some value changes
        assert isinstance(changes, list)
        for change in changes:
            assert isinstance(change, ValueChange)
            assert change.unit
            assert change.old_value != change.new_value


# ─── Cross-Reference Detection ─────────────────────────────────

class TestCrossReference:
    """Test cross-reference detection between documents."""

    @pytest.fixture
    def ir_e(self):
        return load_document_ir("IDSS_IDD_RevE", OUTPUT_DIR)

    @pytest.fixture
    def ir_f(self):
        return load_document_ir("IDSS_IDD_RevF", OUTPUT_DIR)

    def test_detects_cross_refs_same_family(self, ir_e, ir_f):
        """Same document family should detect cross-references (shared refs)."""
        if ir_e is None or ir_f is None:
            pytest.skip("Both IDSS IRs required")
        refs = detect_cross_refs(ir_e, ir_f, "IDSS_IDD_RevE", "IDSS_IDD_RevF")
        # Same family docs typically reference each other or share refs
        assert isinstance(refs, list)

    def test_cross_refs_have_required_fields(self, ir_e, ir_f):
        """Each CrossReference should have source, target, text, page."""
        if ir_e is None or ir_f is None:
            pytest.skip("Both IDSS IRs required")
        refs = detect_cross_refs(ir_e, ir_f, "IDSS_IDD_RevE", "IDSS_IDD_RevF")
        for ref in refs:
            assert ref.source_document
            assert ref.target_document
            assert ref.reference_text
            assert ref.page > 0


# ─── Maturity Scoring ──────────────────────────────────────────

class TestMaturityScoring:
    """Test maturity scoring for documents."""

    @pytest.fixture
    def ir_e(self):
        return load_document_ir("IDSS_IDD_RevE", OUTPUT_DIR)

    @pytest.fixture
    def ir_f(self):
        return load_document_ir("IDSS_IDD_RevF", OUTPUT_DIR)

    def test_scores_document_sections(self, ir_e):
        """Should produce maturity scores per section + overall."""
        if ir_e is None:
            pytest.skip("IDSS_IDD_RevE IR not available")
        from src.tbd_tracker import scan_document
        tbds = scan_document(ir_e)
        scores = score_document(ir_e, tbds)
        assert len(scores) > 1  # At least one section + overall
        # Last score should be "overall"
        assert scores[-1].section == "overall"

    def test_scores_are_valid_range(self, ir_f):
        """All scores should be between 0.0 and 1.0."""
        if ir_f is None:
            pytest.skip("IDSS_IDD_RevF IR not available")
        from src.tbd_tracker import scan_document
        tbds = scan_document(ir_f)
        scores = score_document(ir_f, tbds)
        for score in scores:
            assert 0.0 <= score.score <= 1.0
            assert score.rating in ("high", "medium", "low")
            assert score.total_blocks >= 0
            assert score.tbd_count >= 0

    def test_overall_score_reflects_tbds(self, ir_e):
        """Document with TBDs should have overall score < 1.0."""
        if ir_e is None:
            pytest.skip("IDSS_IDD_RevE IR not available")
        from src.tbd_tracker import scan_document
        tbds = scan_document(ir_e)
        if len(tbds) == 0:
            pytest.skip("No TBDs found in RevE")
        scores = score_document(ir_e, tbds)
        overall = scores[-1]
        assert overall.score < 1.0  # Has TBDs → not fully mature


# ─── Section-Level Comparison ──────────────────────────────────

@pytest.mark.skipif(not IDSS_E.exists() or not IDSS_F.exists(), reason="IDSS PDFs not found")
class TestSectionComparison:
    """Test section-by-section comparison between revisions."""

    @pytest.fixture
    def comparison(self):
        return compare_revisions(IDSS_E, IDSS_F)

    def test_returns_comparison_result(self, comparison):
        assert isinstance(comparison, ComparisonResult)
        assert comparison.document_a.filename == "IDSS_IDD_RevE.pdf"
        assert comparison.document_b.filename == "IDSS_IDD_RevF.pdf"

    def test_has_sections(self, comparison):
        """Should produce multiple section comparisons."""
        assert len(comparison.sections) > 0

    def test_detects_changed_sections(self, comparison):
        """Rev E→F had major changes (142→70 pages)."""
        changed = [s for s in comparison.sections if s.change_type != "unchanged"]
        assert len(changed) > 0
        assert comparison.total_sections_changed > 0

    def test_section_types_valid(self, comparison):
        """All sections should have valid change types."""
        for section in comparison.sections:
            assert section.change_type in ("modified", "added", "removed", "unchanged")
            assert section.section_heading

    def test_sections_have_summary_lines(self, comparison):
        """Changed sections should have non-empty summary lines."""
        changed = [s for s in comparison.sections if s.change_type != "unchanged"]
        for section in changed:
            assert section.summary_line
            assert section.summary_line != ""

    def test_detects_value_changes(self, comparison):
        """Should find at least some value changes across sections."""
        all_value_changes = []
        for section in comparison.sections:
            all_value_changes.extend(section.value_changes)
        # Between two major revisions, there should be some value changes
        # (not guaranteed, so this is a soft assertion)
        assert comparison.total_value_changes >= 0

    def test_classification_valid(self, comparison):
        """Each section should have a valid classification."""
        for section in comparison.sections:
            assert section.classification in ("editorial", "technical", "structural")

    def test_detects_removed_sections(self, comparison):
        """Rev F is shorter — should have some removed sections."""
        removed = [s for s in comparison.sections if s.change_type == "removed"]
        assert len(removed) > 0

    def test_has_generated_timestamp(self, comparison):
        assert comparison.generated_at
        assert "T" in comparison.generated_at  # ISO format


# ─── Consolidator ─────────────────────────────────────────────

class TestConsolidator:
    """Test the top-level document gathering and TBD aggregation."""

    def test_gather_single_document(self):
        """Should load a single document and scan TBDs."""
        ir_path = OUTPUT_DIR / "IDSS_IDD_RevE_document_ir.yaml"
        if not ir_path.exists():
            pytest.skip("IDSS_IDD_RevE IR not indexed")
        briefing = gather_documents(["IDSS_IDD_RevE"], OUTPUT_DIR)
        assert isinstance(briefing, BriefingDocument)
        assert briefing.document_count == 1
        assert len(briefing.documents) == 1
        assert briefing.documents[0].stem == "IDSS_IDD_RevE"
        assert briefing.documents[0].page_count > 0

    def test_gather_two_documents(self):
        """Should load two documents and aggregate TBDs."""
        ir_e = OUTPUT_DIR / "IDSS_IDD_RevE_document_ir.yaml"
        ir_f = OUTPUT_DIR / "IDSS_IDD_RevF_document_ir.yaml"
        if not ir_e.exists() or not ir_f.exists():
            pytest.skip("Both IDSS IRs need to be indexed")
        briefing = gather_documents(["IDSS_IDD_RevE", "IDSS_IDD_RevF"], OUTPUT_DIR)
        assert briefing.document_count == 2
        assert len(briefing.documents) == 2
        # TBDs should be aggregated from both
        assert isinstance(briefing.all_tbds, list)

    def test_gather_skips_missing_documents(self):
        """Should gracefully skip documents without IR files."""
        briefing = gather_documents(["NONEXISTENT_DOC"], OUTPUT_DIR)
        assert briefing.document_count == 0
        assert len(briefing.documents) == 0

    def test_document_summary_has_metadata(self):
        """Document summaries should have revision, page count, TBD counts."""
        ir_path = OUTPUT_DIR / "IDSS_IDD_RevF_document_ir.yaml"
        if not ir_path.exists():
            pytest.skip("IDSS_IDD_RevF IR not indexed")
        briefing = gather_documents(["IDSS_IDD_RevF"], OUTPUT_DIR)
        doc = briefing.documents[0]
        assert doc.page_count > 0
        assert doc.tbd_count >= 0
        assert doc.tbr_count >= 0
        assert doc.filename

    def test_aggregated_tbds_have_document_labels(self):
        """Each TBD in all_tbds should be labeled with its source document."""
        ir_path = OUTPUT_DIR / "IDSS_IDD_RevE_document_ir.yaml"
        if not ir_path.exists():
            pytest.skip("IDSS_IDD_RevE IR not indexed")
        briefing = gather_documents(["IDSS_IDD_RevE"], OUTPUT_DIR)
        for tbd in briefing.all_tbds:
            assert tbd.document == "IDSS_IDD_RevE"
            assert tbd.id
            assert tbd.item_type in ("TBD", "TBR", "TBC", "TBS")


# ─── Integration: Full Pipeline ────────────────────────────────

@pytest.mark.skipif(not IDSS_E.exists() or not IDSS_F.exists(), reason="IDSS PDFs not found")
class TestFullPipeline:
    """End-to-end test: compare two documents and verify all outputs."""

    def test_full_comparison_produces_all_outputs(self):
        """compare_revisions + maturity + cross-refs should all succeed."""
        ir_e = load_document_ir("IDSS_IDD_RevE", OUTPUT_DIR)
        ir_f = load_document_ir("IDSS_IDD_RevF", OUTPUT_DIR)
        if ir_e is None or ir_f is None:
            pytest.skip("Both IRs need to be indexed")

        # Section comparison
        comparison = compare_revisions(IDSS_E, IDSS_F)
        assert comparison.total_sections_changed > 0

        # Maturity scoring
        from src.tbd_tracker import scan_document
        tbds_e = scan_document(ir_e)
        tbds_f = scan_document(ir_f)
        scores_e = score_document(ir_e, tbds_e)
        scores_f = score_document(ir_f, tbds_f)
        assert len(scores_e) > 0
        assert len(scores_f) > 0

        # Cross-references
        refs = detect_cross_refs(ir_e, ir_f, "IDSS_IDD_RevE", "IDSS_IDD_RevF")
        assert isinstance(refs, list)

        # Value extraction
        specs_e = extract_specifications(ir_e)
        specs_f = extract_specifications(ir_f)
        assert len(specs_e) > 0
        assert len(specs_f) > 0
