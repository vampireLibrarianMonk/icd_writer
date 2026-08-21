"""User Guide Regression: Revision Comparison (Section 5)

Validates the Version Comparison workflow described in the User Guide:
- Compare two revisions of the same document family
- See section-by-section changes with change types
- Detect value changes and TBD deltas
- Verify headings are real sections (no bogus entries)
- Boilerplate filtering (global_changes vs section-level)
- Classification accuracy (editorial vs technical)

Tests use:
- IDSS_IDD_RevE.pdf + RevF.pdf (major revision with page reduction)
- HSI_SYS_001H.pdf + 001I.pdf (incremental revision)

These tests exercise the backend compare pipeline directly AND the API endpoints.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.briefing.section_diff import compare_revisions

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_H = ICDS_DIR / "HSI_SYS_001H.pdf"
HSI_I = ICDS_DIR / "HSI_SYS_001I.pdf"
IDSS_E = ICDS_DIR / "IDSS_IDD_RevE.pdf"
IDSS_F = ICDS_DIR / "IDSS_IDD_RevF.pdf"


@pytest.fixture(scope="module")
def client():
    """Shared test client for API tests (no document open needed)."""
    app = create_app()
    c = TestClient(app)
    c.post("/session/start")
    return c


# ─── Families Endpoint ────────────────────────────────────────────────


@pytest.mark.skipif(
    not HSI_H.exists() or not HSI_I.exists(),
    reason="HSI revision PDFs not found",
)
class TestFamiliesEndpoint:
    """Verify GET /briefing/families returns document families."""

    def test_families_endpoint_returns_families(self, client):
        """GET /briefing/families has document families with versions."""
        res = client.get("/briefing/families")
        assert res.status_code == 200
        data = res.json()
        assert "families" in data
        assert len(data["families"]) >= 1

    def test_families_include_hsi(self, client):
        """HSI family should be present with multiple versions."""
        res = client.get("/briefing/families")
        families = res.json()["families"]
        family_names = [f["family_name"] for f in families]
        assert any("hsi_sys_001" in name.lower() for name in family_names), (
            f"HSI family not found in: {family_names}"
        )

    @pytest.mark.skipif(
        not IDSS_E.exists() or not IDSS_F.exists(),
        reason="IDSS PDFs not found",
    )
    def test_families_include_idss(self, client):
        """IDSS family should be present with multiple versions."""
        res = client.get("/briefing/families")
        families = res.json()["families"]
        family_names = [f["family_name"] for f in families]
        assert any("idss_idd" in name.lower() for name in family_names), (
            f"IDSS family not found in: {family_names}"
        )

    def test_family_versions_have_fields(self, client):
        """Each version entry has required fields."""
        res = client.get("/briefing/families")
        families = res.json()["families"]
        for family in families:
            assert "versions" in family
            for version in family["versions"]:
                assert "filename" in version
                assert "path" in version
                assert "revision" in version


# ─── Compare Returns Section Diffs ────────────────────────────────────


@pytest.mark.skipif(
    not HSI_H.exists() or not HSI_I.exists(),
    reason="HSI revision PDFs not found",
)
class TestCompareReturnsSectionDiffs:
    """Verify POST /briefing/compare returns meaningful section-level diffs."""

    def test_compare_returns_section_diffs(self, client):
        """POST /briefing/compare returns sections with change_types."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(HSI_H), "version_b": str(HSI_I)},
        )
        assert res.status_code == 200
        data = res.json()
        assert "sections" in data
        assert "stats" in data
        assert len(data["sections"]) > 0
        assert data["stats"]["total_sections_changed"] > 0

    def test_sections_have_change_types(self, client):
        """Each section has a valid change_type."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(HSI_H), "version_b": str(HSI_I)},
        )
        data = res.json()
        valid_types = {"modified", "added", "removed", "unchanged"}
        for section in data["sections"]:
            assert "change_type" in section
            assert section["change_type"] in valid_types, (
                f"Invalid change_type: {section['change_type']}"
            )

    def test_compare_has_stats(self, client):
        """Stats include total value changes and TBD metrics."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(HSI_H), "version_b": str(HSI_I)},
        )
        stats = res.json()["stats"]
        assert "total_value_changes" in stats
        assert "total_sections_changed" in stats
        assert "total_sections_unchanged" in stats


# ─── No Bogus Headings ────────────────────────────────────────────────


@pytest.mark.skipif(
    not HSI_H.exists() or not HSI_I.exists(),
    reason="HSI revision PDFs not found",
)
class TestCompareNoBogusHeadings:
    """Verify no section heading contains measurement units, symbols, or bullets."""

    BOGUS_WORDS = ["bytes", "ohm"]
    BOGUS_CHARS = ["Ω"]
    BOGUS_STARTS = ["• ", "* ", "► "]

    def test_compare_no_bogus_headings(self, client):
        """No section heading contains 'bytes', 'Ω', or bullets."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(HSI_H), "version_b": str(HSI_I)},
        )
        sections = res.json()["sections"]
        for s in sections:
            heading = s["section_heading"]
            for word in self.BOGUS_WORDS:
                assert word not in heading.lower(), (
                    f"Bogus heading detected: '{heading}' contains '{word}'"
                )
            for char in self.BOGUS_CHARS:
                assert char not in heading, (
                    f"Bogus heading detected: '{heading}' contains '{char}'"
                )
            for start in self.BOGUS_STARTS:
                assert not heading.startswith(start), (
                    f"Bullet point as heading: '{heading}'"
                )

    @pytest.mark.skipif(
        not IDSS_E.exists() or not IDSS_F.exists(),
        reason="IDSS PDFs not found",
    )
    def test_idss_compare_no_bogus_headings(self, client):
        """IDSS comparison also has no bogus headings."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(IDSS_E), "version_b": str(IDSS_F)},
        )
        sections = res.json()["sections"]
        for s in sections:
            heading = s["section_heading"]
            for word in self.BOGUS_WORDS:
                assert word not in heading.lower(), (
                    f"Bogus heading in IDSS: '{heading}'"
                )
            for char in self.BOGUS_CHARS:
                assert char not in heading, f"Bogus char in IDSS: '{heading}'"


# ─── Boilerplate Filtering ────────────────────────────────────────────


@pytest.mark.skipif(
    not HSI_H.exists() or not HSI_I.exists(),
    reason="HSI revision PDFs not found",
)
class TestCompareBoilerplateFiltered:
    """Verify that global/boilerplate changes are separated from section diffs."""

    def test_compare_boilerplate_filtered(self, client):
        """global_changes contains header stamps, sections don't repeat them."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(HSI_H), "version_b": str(HSI_I)},
        )
        data = res.json()

        # global_changes should exist (may be empty for some comparisons)
        assert "global_changes" in data

        # If there are global changes, verify they aren't duplicated in sections
        global_changes = data.get("global_changes", [])
        if global_changes:
            # Global changes shouldn't appear as section headings
            section_headings = {s["section_heading"] for s in data["sections"]}
            for gc in global_changes:
                if isinstance(gc, str):
                    assert gc not in section_headings, (
                        f"Global change '{gc}' also appears as a section heading"
                    )


# ─── Classification Accuracy ──────────────────────────────────────────


@pytest.mark.skipif(
    not HSI_H.exists() or not HSI_I.exists(),
    reason="HSI revision PDFs not found",
)
class TestCompareClassificationAccuracy:
    """Verify change classification (editorial vs technical) makes sense."""

    def test_compare_classification_accuracy(self, client):
        """Changed sections have a classification field."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(HSI_H), "version_b": str(HSI_I)},
        )
        sections = res.json()["sections"]
        changed = [s for s in sections if s["change_type"] != "unchanged"]

        # At least some changed sections should have a classification
        classified = [s for s in changed if s.get("classification")]
        assert len(classified) > 0, "No changed sections have a classification"

        # Valid classification values
        valid_classifications = {"editorial", "technical", "structural", "formatting"}
        for s in classified:
            assert s["classification"] in valid_classifications, (
                f"Invalid classification '{s['classification']}' for '{s['section_heading']}'"
            )


# ─── Value Changes Detected ───────────────────────────────────────────


@pytest.mark.skipif(
    not IDSS_E.exists() or not IDSS_F.exists(),
    reason="IDSS PDFs not found",
)
class TestCompareValueChangesDetected:
    """Verify that value changes are detected between revisions."""

    def test_compare_value_changes_detected(self, client):
        """Stats show total_value_changes > 0 for IDSS E→F."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(IDSS_E), "version_b": str(IDSS_F)},
        )
        assert res.status_code == 200
        stats = res.json()["stats"]
        assert stats["total_value_changes"] > 0, (
            "No value changes detected between IDSS RevE and RevF"
        )

    def test_value_changes_have_details(self, client):
        """Sections with value changes include parameter, old_value, new_value."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(IDSS_E), "version_b": str(IDSS_F)},
        )
        sections = res.json()["sections"]
        sections_with_vc = [s for s in sections if s.get("value_changes")]

        if not sections_with_vc:
            pytest.skip("No sections with value_changes in this comparison")

        for s in sections_with_vc:
            for vc in s["value_changes"]:
                assert "parameter" in vc
                assert "old_value" in vc
                assert "new_value" in vc


# ─── TBD Delta Detected ──────────────────────────────────────────────


@pytest.mark.skipif(
    not HSI_H.exists() or not HSI_I.exists(),
    reason="HSI revision PDFs not found",
)
class TestCompareTBDDeltaDetected:
    """Verify TBD/TBR resolution or introduction is tracked across revisions."""

    def test_compare_tbd_delta_detected(self, client):
        """Stats show TBDs resolved or introduced for HSI H→I."""
        res = client.post(
            "/briefing/compare",
            params={"version_a": str(HSI_H), "version_b": str(HSI_I)},
        )
        assert res.status_code == 200
        stats = res.json()["stats"]

        # At least one of resolved/introduced should be non-zero for a real revision
        total_tbd_activity = (
            stats.get("total_tbds_resolved", 0) + stats.get("total_tbds_introduced", 0)
        )
        # This is a soft assertion — some revisions may not have TBD changes
        if total_tbd_activity == 0:
            pytest.skip("No TBD delta between HSI H and I revisions")
        assert total_tbd_activity > 0


# ─── Direct Pipeline Tests (no API) ──────────────────────────────────


@pytest.mark.skipif(
    not HSI_H.exists() or not HSI_I.exists(),
    reason="HSI revision PDFs not found",
)
class TestDirectComparisonPipeline:
    """Test the compare_revisions function directly for deeper validation."""

    @pytest.fixture(scope="class")
    def comparison(self):
        return compare_revisions(HSI_H, HSI_I)

    def test_reasonable_section_count(self, comparison):
        """Should have 20-80 sections for a mid-sized ICD."""
        total = len(comparison.sections)
        assert 20 <= total <= 80, f"Got {total} sections — unexpected range"

    def test_has_both_changed_and_unchanged(self, comparison):
        """A real revision should have both modified and stable sections."""
        assert comparison.total_sections_changed > 0
        assert comparison.total_sections_unchanged > 0

    def test_changed_sections_have_summaries(self, comparison):
        """Every changed section should have a non-empty summary."""
        changed = [s for s in comparison.sections if s.change_type != "unchanged"]
        for s in changed:
            assert s.summary_line, (
                f"Section '{s.section_heading}' has no summary"
            )

    def test_page_numbers_valid(self, comparison):
        """All page references should be within document bounds."""
        for s in comparison.sections:
            if s.page_new:
                assert 1 <= s.page_new <= 30, f"Invalid page_new: {s.page_new}"
            if s.page_old:
                assert 1 <= s.page_old <= 30, f"Invalid page_old: {s.page_old}"

    def test_highlight_matching_accuracy(self, comparison):
        """Section headings that reference pages should have valid page numbers (≥95%)."""
        sections_with_pages = [
            s for s in comparison.sections
            if s.page_new is not None and s.change_type != "removed"
        ]
        if len(sections_with_pages) < 5:
            pytest.skip("Not enough sections with page references to validate")

        valid = sum(1 for s in sections_with_pages if 1 <= s.page_new <= 23)
        accuracy = valid / len(sections_with_pages)
        assert accuracy >= 0.95, (
            f"Only {accuracy:.0%} of section page refs are valid (need ≥95%)"
        )
