"""Data models for the briefing consolidation output.

These models represent the structured briefing produced by comparing
two or more ICD documents. All fields are populated by local processing
(no LLM calls required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DocumentSummary:
    """Summary metadata for a single document in the briefing."""

    stem: str  # e.g., "IDSS_IDD_RevF"
    filename: str
    path: str
    revision: str
    date: str
    page_count: int
    tbd_count: int
    tbr_count: int
    doc_type: str = "digital"  # digital | flattened


@dataclass
class TbdItem:
    """A single TBD/TBR item with location and context."""

    id: str  # e.g., "TBR-UCB-102" or "TBD-003"
    item_type: str  # TBD, TBR, TBC, TBS
    status: str  # open, resolved
    page: int
    context: str  # surrounding text (truncated)
    owner: Optional[str] = None
    document: str = ""  # which document it came from


@dataclass
class TbdDelta:
    """Change in TBD/TBR items between two revisions for a section."""

    resolved: list[TbdItem] = field(default_factory=list)
    introduced: list[TbdItem] = field(default_factory=list)
    unchanged: list[TbdItem] = field(default_factory=list)

    @property
    def net_change(self) -> int:
        """Positive = more TBDs introduced than resolved."""
        return len(self.introduced) - len(self.resolved)


@dataclass
class ValueChange:
    """A detected change in a specification value between revisions."""

    parameter: str  # e.g., "docking ring diameter"
    old_value: float
    new_value: float
    unit: str  # e.g., "mm", "W", "V"
    old_context: str  # source text snippet
    new_context: str
    page_old: Optional[int] = None
    page_new: Optional[int] = None


@dataclass
class ValueConflict:
    """A detected value mismatch between two different documents."""

    parameter: str  # shared keyword context
    value_a: float
    value_b: float
    unit: str
    context_a: str
    context_b: str
    document_a: str
    document_b: str
    page_a: Optional[int] = None
    page_b: Optional[int] = None


@dataclass
class CrossReference:
    """A detected cross-reference between two documents."""

    source_document: str  # document that contains the reference
    target_document: str  # document being referenced
    reference_text: str  # the text of the reference (e.g., doc title)
    section: str  # section where found
    page: int
    ref_type: str = "applicable_document"  # applicable_document | inline_mention


@dataclass
class MaturityScore:
    """Maturity assessment for a section or document."""

    section: str  # section heading (or "overall" for doc-level)
    total_blocks: int
    tbd_count: int
    score: float  # 0.0 to 1.0 (1.0 = fully mature, no TBDs)
    rating: str  # "high", "medium", "low"

    @staticmethod
    def compute_rating(score: float) -> str:
        if score >= 0.95:
            return "high"
        elif score >= 0.80:
            return "medium"
        else:
            return "low"


@dataclass
class SectionComparison:
    """Comparison result for a single section between two revisions."""

    section_heading: str
    change_type: str  # "modified", "added", "removed", "unchanged"
    # Summary counts
    paragraphs_modified: int = 0
    paragraphs_added: int = 0
    paragraphs_removed: int = 0
    # Detailed changes
    value_changes: list[ValueChange] = field(default_factory=list)
    tbd_delta: Optional[TbdDelta] = None
    # Specific text diffs (first few changes, truncated)
    text_snippets: list[str] = field(default_factory=list)
    # Classification
    classification: str = "editorial"  # editorial, technical, structural
    has_requirement_change: bool = False
    # Page references
    page_old: Optional[int] = None
    page_new: Optional[int] = None
    # One-line summary for collapsed view
    summary_line: str = ""


@dataclass
class ComparisonResult:
    """Full comparison result between two document revisions."""

    document_a: DocumentSummary  # older
    document_b: DocumentSummary  # newer
    sections: list[SectionComparison] = field(default_factory=list)
    # Global changes (boilerplate appearing across many sections, e.g. header/footer updates)
    global_changes: list[str] = field(default_factory=list)
    # Aggregate stats
    total_value_changes: int = 0
    total_tbds_resolved: int = 0
    total_tbds_introduced: int = 0
    total_sections_changed: int = 0
    total_sections_unchanged: int = 0
    # Cross-references
    cross_references: list[CrossReference] = field(default_factory=list)
    # Value conflicts (cross-doc, not same-doc revision diff)
    value_conflicts: list[ValueConflict] = field(default_factory=list)
    # Maturity
    maturity_a: list[MaturityScore] = field(default_factory=list)
    maturity_b: list[MaturityScore] = field(default_factory=list)
    # Metadata
    generated_at: str = ""


@dataclass
class BriefingDocument:
    """Top-level briefing output combining all analysis results.

    This is the complete output of Phase 1 consolidation for two documents.
    """

    documents: list[DocumentSummary] = field(default_factory=list)
    comparison: Optional[ComparisonResult] = None
    # Aggregated TBD list across all documents
    all_tbds: list[TbdItem] = field(default_factory=list)
    # Cross-references between all documents
    cross_references: list[CrossReference] = field(default_factory=list)
    # Maturity scores per document
    maturity_scores: list[MaturityScore] = field(default_factory=list)
    # Metadata
    generated_at: str = ""
    document_count: int = 0
