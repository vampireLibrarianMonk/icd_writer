"""Document version detection and differential analysis.

Phase 6: Detects related document versions, computes structured diffs,
and produces exportable reports with optional LLM summarization.

Workflow:
1. detect_families() — find related documents by filename/content
2. quick_compare() — fast metadata + page count comparison
3. full_diff() — structured section-by-section text diff
4. generate_report() — formatted output (text, markdown, HTML)
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Data models
# -----------------------------------------------------------------

@dataclass
class DocumentVersion:
    """A single document version with metadata."""

    path: str
    filename: str
    stem: str
    page_count: int
    sha256: str
    title: str = ""
    revision: str = ""
    date: str = ""
    doc_type: str = "digital"  # digital, flattened
    file_size_bytes: int = 0


@dataclass
class DocumentFamily:
    """A group of related document versions."""

    base_name: str
    versions: list[DocumentVersion]
    status: str = "unknown"  # identical, content_differs, page_count_differs
    text_overlap: float = 0.0  # 0.0 to 1.0


@dataclass
class SectionDiff:
    """A diff for one section between two versions."""

    section_heading: str
    section_number: str | None = None
    page_old: int | None = None
    page_new: int | None = None
    change_type: str = "modified"  # modified, added, removed
    old_text: str = ""
    new_text: str = ""
    # Classification
    classification: str = "editorial"  # editorial, technical, structural
    has_requirement_change: bool = False  # shall/will/must modified
    has_tbd_change: bool = False  # TBD added or removed
    # LLM summary (populated on demand)
    ai_summary: str | None = None


@dataclass
class DiffReport:
    """Complete differential analysis between two versions."""

    version_a: DocumentVersion  # Older
    version_b: DocumentVersion  # Newer
    # Summary stats
    sections_modified: int = 0
    sections_added: int = 0
    sections_removed: int = 0
    requirement_changes: int = 0
    tbd_changes: int = 0
    editorial_changes: int = 0
    text_overlap: float = 0.0
    # Detailed diffs
    diffs: list[SectionDiff] = field(default_factory=list)
    # Metadata
    generated_at: str = ""
    total_diff_tokens: int = 0


# -----------------------------------------------------------------
# Version Detection
# -----------------------------------------------------------------

# Suffixes to strip when normalizing filenames
STRIP_SUFFIXES = [
    "_flat", "_flattened", "_scanned",
    "_v1", "_v2", "_v3", "_v4", "_v5",
    "_reva", "_revb", "_revc", "_revd", "_reve", "_revf", "_revg", "_revh",
    "_draft", "_final", "_baseline",
    "_digital", "_ocr",
]


def normalize_stem(filename: str) -> str:
    """Normalize a filename to its base document identity."""
    stem = Path(filename).stem.lower()
    for suffix in STRIP_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
    # Strip trailing dates like _20240315
    stem = re.sub(r'_\d{8}$', '', stem)
    # Strip trailing revision markers like _RevF
    stem = re.sub(r'_rev[a-z]$', '', stem, flags=re.IGNORECASE)
    # Strip ICD-style revision suffix: number + single letter (e.g., 001H → 001)
    # Pattern: document number ends with digits followed by a single revision letter
    stem = re.sub(r'(\d{2,})[a-z]$', r'\1', stem)
    return stem


def detect_families(scan_dirs: list[Path | str] | None = None) -> list[DocumentFamily]:
    """Scan directories and group documents into version families.

    Only considers documents that have been indexed (have a _document_ir.yaml
    in output/). This ensures the diff tab only shows versions the user has
    explicitly uploaded and processed.

    Returns families where multiple versions of the same document exist.
    """
    if scan_dirs is None:
        scan_dirs = [Path("icds/digital"), Path("uploads")]

    output_dir = Path("output")

    # Collect all PDFs with metadata — only indexed ones
    all_versions: dict[str, list[DocumentVersion]] = {}

    for scan_dir in scan_dirs:
        scan_dir = Path(scan_dir)
        if not scan_dir.exists():
            continue

        for pdf_path in sorted(scan_dir.glob("*.pdf")):
            # Only include documents that have been indexed
            ir_path = output_dir / f"{pdf_path.stem}_document_ir.yaml"
            if not ir_path.exists():
                continue

            doc = fitz.open(str(pdf_path))
            sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

            # Extract revision from first page text
            first_page_text = doc[0].get_text()[:500]
            revision = _extract_revision(first_page_text)
            title = doc.metadata.get("title", "") or ""
            date = _extract_date(first_page_text)

            # Fallback: extract revision from filename if text-based failed
            if not revision:
                revision = _extract_revision_from_filename(pdf_path.name)

            # Determine type
            doc_type = "flattened" if "flat" in scan_dir.name else "digital"

            version = DocumentVersion(
                path=str(pdf_path),
                filename=pdf_path.name,
                stem=pdf_path.stem,
                page_count=doc.page_count,
                sha256=sha,
                title=title,
                revision=revision,
                date=date,
                doc_type=doc_type,
                file_size_bytes=pdf_path.stat().st_size,
            )
            doc.close()

            # Group by normalized stem
            base = normalize_stem(pdf_path.name)
            all_versions.setdefault(base, []).append(version)

    # Build families (only groups with 2+ versions)
    families = []
    for base_name, versions in all_versions.items():
        if len(versions) < 2:
            continue

        # Quick status check
        if len(set(v.sha256 for v in versions)) == 1:
            status = "identical"
        elif len(set(v.page_count for v in versions)) > 1:
            status = "page_count_differs"
        else:
            status = "content_differs"

        families.append(DocumentFamily(
            base_name=base_name,
            versions=sorted(versions, key=lambda v: (v.date or "", v.revision or "")),
            status=status,
        ))

    return families


# -----------------------------------------------------------------
# Quick Comparison
# -----------------------------------------------------------------

def quick_compare(path_a: str | Path, path_b: str | Path) -> dict[str, Any]:
    """Fast comparison between two documents (no full text diff).

    Returns metadata comparison and text overlap estimate.
    """
    doc_a = fitz.open(str(path_a))
    doc_b = fitz.open(str(path_b))

    # Page counts
    pages_a = doc_a.page_count
    pages_b = doc_b.page_count

    # First page text comparison (fast overlap estimate)
    text_a = set(doc_a[0].get_text().split())
    text_b = set(doc_b[0].get_text().split())
    overlap = len(text_a & text_b) / max(len(text_a | text_b), 1)

    # Revision extraction
    rev_a = _extract_revision(doc_a[0].get_text()[:500])
    rev_b = _extract_revision(doc_b[0].get_text()[:500])

    doc_a.close()
    doc_b.close()

    return {
        "pages_a": pages_a,
        "pages_b": pages_b,
        "page_count_match": pages_a == pages_b,
        "first_page_overlap": round(overlap, 3),
        "revision_a": rev_a,
        "revision_b": rev_b,
        "likely_related": overlap > 0.3 or (
            normalize_stem(Path(path_a).name) == normalize_stem(Path(path_b).name)
        ),
    }


# -----------------------------------------------------------------
# Full Structured Diff
# -----------------------------------------------------------------

def full_diff(path_a: str | Path, path_b: str | Path) -> DiffReport:
    """Compute a full structured diff between two document versions.

    Extracts sections from both, aligns them, and produces per-section diffs.
    Version A is treated as older, Version B as newer.
    """
    path_a, path_b = Path(path_a), Path(path_b)

    # Extract sections from both
    sections_a = _extract_sections(path_a)
    sections_b = _extract_sections(path_b)

    # Build version metadata
    doc_a = fitz.open(str(path_a))
    doc_b = fitz.open(str(path_b))
    version_a = DocumentVersion(
        path=str(path_a), filename=path_a.name, stem=path_a.stem,
        page_count=doc_a.page_count,
        sha256=hashlib.sha256(path_a.read_bytes()).hexdigest(),
        revision=_extract_revision(doc_a[0].get_text()[:500]),
    )
    version_b = DocumentVersion(
        path=str(path_b), filename=path_b.name, stem=path_b.stem,
        page_count=doc_b.page_count,
        sha256=hashlib.sha256(path_b.read_bytes()).hexdigest(),
        revision=_extract_revision(doc_b[0].get_text()[:500]),
    )
    doc_a.close()
    doc_b.close()

    # Align and diff sections
    diffs = _diff_sections(sections_a, sections_b)

    # Compute stats
    text_a_all = " ".join(s["text"] for s in sections_a)
    text_b_all = " ".join(s["text"] for s in sections_b)
    words_a = set(text_a_all.split())
    words_b = set(text_b_all.split())
    text_overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)

    # Count diff tokens for budget estimation
    total_tokens = sum(
        len(d.old_text.split()) + len(d.new_text.split()) for d in diffs
    )

    from datetime import datetime, timezone
    report = DiffReport(
        version_a=version_a,
        version_b=version_b,
        sections_modified=sum(1 for d in diffs if d.change_type == "modified"),
        sections_added=sum(1 for d in diffs if d.change_type == "added"),
        sections_removed=sum(1 for d in diffs if d.change_type == "removed"),
        requirement_changes=sum(1 for d in diffs if d.has_requirement_change),
        tbd_changes=sum(1 for d in diffs if d.has_tbd_change),
        editorial_changes=sum(1 for d in diffs if d.classification == "editorial"),
        text_overlap=round(text_overlap, 3),
        diffs=diffs,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_diff_tokens=total_tokens,
    )

    return report


# -----------------------------------------------------------------
# Section Extraction
# -----------------------------------------------------------------

def _extract_sections(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract text organized by sections (headings).

    Heading detection rules:
    1. Numbered section headings: "1.", "1.1", "4.1.2.3 Title Text"
       - Must start with a section number pattern
       - Must be followed by alphabetic title text (not units/values)
    2. All-caps titles: "INTRODUCTION", "DOCUMENT REVISION RECORD"
       - Must be >= 6 chars, all uppercase letters/spaces
       - Must NOT start with bullet points or special chars
    3. Large font (>14pt) short text that looks like a title
       - Must contain at least one letter
       - Must NOT be a measurement value or data entry
    """
    doc = fitz.open(str(pdf_path))
    sections: list[dict[str, Any]] = []
    current_heading = "Preamble"
    current_text_parts: list[str] = []
    current_page = 1

    # Numbered section: "1. Introduction" or "4.1.2.3 Title"
    # Requires the text after the number to start with a letter (not a digit/unit)
    numbered_heading = re.compile(
        r'^(\d+(?:\.\d+)*\.?)\s+([A-Za-z][A-Za-z\s&/,\-()]{2,})$'
    )
    # All-caps title (at least 8 chars, only letters and spaces, at least 2 words)
    allcaps_heading = re.compile(
        r'^[A-Z]{2,}(?:\s+[A-Z]{2,})+$'
    )
    # Single all-caps words that are known structural headings
    known_allcaps_headings = {
        "PREFACE", "INTRODUCTION", "CONCURRENCE", "REFERENCES",
        "REQUIREMENTS", "APPENDIX", "GLOSSARY", "ACRONYMS",
        "SUMMARY", "CONTENTS", "ABSTRACT",
    }
    # Common TOC/table column labels that should NOT be headings
    excluded_allcaps = {
        "PARAGRAPH", "DESCRIPTION", "FIGURE", "TABLE", "PAGE",
        "NUMBER", "TITLE", "SECTION", "APPENDIX",
    }
    # Things that should NEVER be headings
    not_heading_patterns = [
        re.compile(r'^[•\-\*►▪]'),          # Bullet points
        re.compile(r'^\d+\.?\d*\s*(V|W|A|mA|MHz|GHz|Mbps|mm|cm|kg|°C|K|psi|ft-lb|N|Nm|Ω|ohm|ns|ms|µs|bytes?|BTU|dB)', re.IGNORECASE),  # Measurement values
        re.compile(r'^\d+\s+bytes?$', re.IGNORECASE),  # "1024 bytes"
        re.compile(r'^\d+\s*(x|×)\s*\d+'),  # Dimensions like "8 x 10"
        re.compile(r'^(Figure|Table|Note)\s+\d', re.IGNORECASE),  # Figure/Table captions
        re.compile(r'^\d{4}-\w{3}-\d{2}'),   # Dates like "1999-Mar-11"
        re.compile(r'^(NUMBER|CROSS SECTIONAL|RETRO REFLECTOR|HEMISPHERICAL)', re.IGNORECASE),  # TOC figure descriptions
    ]

    for page_idx in range(doc.page_count):
        page = doc[page_idx]
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = ""
                max_size = 0
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                    max_size = max(max_size, span.get("size", 0))

                line_text = line_text.strip()
                if not line_text:
                    continue

                # Check exclusion patterns first
                is_excluded = any(p.match(line_text) for p in not_heading_patterns)
                if is_excluded:
                    current_text_parts.append(line_text)
                    continue

                # Detect headings
                is_heading = False

                # Rule 1: Numbered section heading
                if numbered_heading.match(line_text) and len(line_text) < 80:
                    is_heading = True
                # Rule 2: All-caps title
                elif allcaps_heading.match(line_text) and len(line_text) < 60:
                    # Must not be a TOC column label
                    if line_text.strip() not in excluded_allcaps:
                        is_heading = True
                elif line_text.strip() in known_allcaps_headings:
                    is_heading = True
                # Rule 3: Large font title (>14pt, has letters, short)
                elif max_size > 14 and len(line_text) < 80 and re.search(r'[A-Za-z]{3,}', line_text):
                    # Extra check: not a TOC entry or figure description
                    if not any(line_text.startswith(x) for x in ("NUMBER", "CROSS", "RETRO", "HEMI")):
                        is_heading = True

                if is_heading:
                    # Flush previous section
                    if current_text_parts:
                        sections.append({
                            "heading": current_heading,
                            "text": "\n".join(current_text_parts),
                            "page": current_page,
                        })
                    current_heading = line_text
                    current_text_parts = []
                    current_page = page_idx + 1
                else:
                    current_text_parts.append(line_text)

    # Flush last section
    if current_text_parts:
        sections.append({
            "heading": current_heading,
            "text": "\n".join(current_text_parts),
            "page": current_page,
        })

    doc.close()
    return sections


# -----------------------------------------------------------------
# Section Alignment & Diff
# -----------------------------------------------------------------

def _diff_sections(sections_a: list[dict], sections_b: list[dict]) -> list[SectionDiff]:
    """Align sections between two versions and compute diffs."""
    diffs: list[SectionDiff] = []

    # Build lookup by heading
    lookup_a = {s["heading"].lower().strip(): s for s in sections_a}
    lookup_b = {s["heading"].lower().strip(): s for s in sections_b}

    headings_a = set(lookup_a.keys())
    headings_b = set(lookup_b.keys())

    # Sections in both (modified or unchanged)
    for heading in headings_a & headings_b:
        sec_a = lookup_a[heading]
        sec_b = lookup_b[heading]

        text_a = sec_a["text"].strip()
        text_b = sec_b["text"].strip()

        if text_a == text_b:
            continue  # Unchanged — skip

        # Compute what changed
        diff = SectionDiff(
            section_heading=sec_b["heading"],
            page_old=sec_a["page"],
            page_new=sec_b["page"],
            change_type="modified",
            old_text=text_a[:500],  # Truncate for report
            new_text=text_b[:500],
        )

        # Classify
        diff.classification = _classify_change(text_a, text_b)
        diff.has_requirement_change = _has_requirement_change(text_a, text_b)
        diff.has_tbd_change = _has_tbd_change(text_a, text_b)

        diffs.append(diff)

    # Sections only in B (added)
    for heading in headings_b - headings_a:
        sec_b = lookup_b[heading]
        diffs.append(SectionDiff(
            section_heading=sec_b["heading"],
            page_new=sec_b["page"],
            change_type="added",
            new_text=sec_b["text"][:500],
            classification="structural",
            has_tbd_change="tbd" in sec_b["text"].lower(),
        ))

    # Sections only in A (removed)
    for heading in headings_a - headings_b:
        sec_a = lookup_a[heading]
        diffs.append(SectionDiff(
            section_heading=sec_a["heading"],
            page_old=sec_a["page"],
            change_type="removed",
            old_text=sec_a["text"][:500],
            classification="structural",
        ))

    # Sort by section heading (approximates document order)
    diffs.sort(key=lambda d: d.section_heading.lower())
    return diffs


# -----------------------------------------------------------------
# Classification Helpers
# -----------------------------------------------------------------

def _classify_change(old_text: str, new_text: str) -> str:
    """Classify a change as editorial, technical, or structural.

    - technical: specification values changed, requirements modified
    - structural: significant reorganization (>20% word difference)
    - editorial: document references, formatting, minor wording
    """
    # Check for requirement language changes (shall/must/will added or removed)
    if _has_requirement_change(old_text, new_text):
        return "technical"

    # Check for specification value changes (numbers with engineering units)
    # Require: standalone number not glued to letters, followed by unit with boundary
    spec_pattern = re.compile(
        r'(?<!\w)(\d+\.?\d*)\s*'
        r'(V|kV|mV|W|kW|mW|mA|µA|MHz|GHz|kHz|Mbps|kbps|'
        r'mm|cm|µm|kg|mg|°C|°F|psi|kPa|MPa|atm|'
        r'ft-lb|Nm|kN|ohm|Ω|ns|ms|µs|sec|msec|dB|dBm|Hz)\b',
    )
    old_specs = set(spec_pattern.findall(old_text))
    new_specs = set(spec_pattern.findall(new_text))
    if old_specs != new_specs and (old_specs or new_specs):
        return "technical"

    # Check for significant word changes (>30% different = structural)
    old_words = set(old_text.lower().split())
    new_words = set(new_text.lower().split())
    if old_words and new_words:
        similarity = len(old_words & new_words) / max(len(old_words | new_words), 1)
        if similarity < 0.7:
            return "structural"

    return "editorial"


def _has_requirement_change(old_text: str, new_text: str) -> bool:
    """Check if shall/will/must statements were added or removed.

    Only flags when the number of requirement statements changes,
    not when existing statements move to different positions.
    """
    req_pattern = re.compile(r'\b(shall|must)\b', re.IGNORECASE)
    old_count = len(req_pattern.findall(old_text))
    new_count = len(req_pattern.findall(new_text))

    # Only flag if the count of requirement keywords changed
    return old_count != new_count


def _has_tbd_change(old_text: str, new_text: str) -> bool:
    """Check if TBD/TBR items were added or removed."""
    tbd_pattern = re.compile(r'\bTB[DR]\b', re.IGNORECASE)
    old_tbds = len(tbd_pattern.findall(old_text))
    new_tbds = len(tbd_pattern.findall(new_text))
    return old_tbds != new_tbds


# -----------------------------------------------------------------
# Metadata Extraction Helpers
# -----------------------------------------------------------------

def _extract_revision(text: str) -> str:
    """Extract revision identifier from document text."""
    patterns = [
        r'[Rr]ev(?:ision)?[\s.:]*([A-Z])\b',
        r'[Rr]ev(?:ision)?[\s.:]*(\d+)',
        r'[Vv]ersion[\s.:]*(\d+(?:\.\d+)*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _extract_revision_from_filename(filename: str) -> str:
    """Extract revision from filename patterns.

    Handles:
    - IDSS_IDD_RevF.pdf → F
    - HSI_SYS_001H.pdf → H (trailing letter after digits)
    """
    stem = Path(filename).stem
    # Pattern 1: _RevX suffix
    m = re.search(r'_[Rr]ev([A-Z])', stem)
    if m:
        return m.group(1)
    # Pattern 2: trailing single letter after digits (ICD convention)
    m = re.search(r'\d([A-Z])$', stem)
    if m:
        return m.group(1)
    return ""


def _extract_date(text: str) -> str:
    """Extract date from document text."""
    patterns = [
        r'(\w+ \d{4})',  # "October 2016", "July 2022"
        r'(\d{4}-\d{2}-\d{2})',  # ISO date
        r'(\d{2}/\d{2}/\d{4})',  # US date
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


# -----------------------------------------------------------------
# Report Generation
# -----------------------------------------------------------------

def generate_report(report: DiffReport, format: str = "markdown") -> str:
    """Generate a formatted report from a DiffReport.

    Args:
        report: The diff report data
        format: 'markdown', 'text', or 'html'
    """
    if format == "markdown":
        return _report_markdown(report)
    elif format == "html":
        return _report_html(report)
    else:
        return _report_text(report)


def _report_markdown(report: DiffReport) -> str:
    """Generate markdown report."""
    lines = [
        "# Document Version Differential Report",
        "",
        f"**Document Family:** {normalize_stem(report.version_a.filename)}",
        f"**Version A (older):** {report.version_a.filename}",
        f"  - Pages: {report.version_a.page_count} | Revision: {report.version_a.revision or 'unknown'}",
        f"**Version B (newer):** {report.version_b.filename}",
        f"  - Pages: {report.version_b.page_count} | Revision: {report.version_b.revision or 'unknown'}",
        "",
        "## Summary",
        "",
        f"- Sections modified: {report.sections_modified}",
        f"- Sections added: {report.sections_added}",
        f"- Sections removed: {report.sections_removed}",
        f"- Requirement changes: {report.requirement_changes}"
        + (" ⚠️" if report.requirement_changes > 0 else ""),
        f"- TBD/TBR changes: {report.tbd_changes}",
        f"- Editorial changes: {report.editorial_changes}",
        f"- Text overlap: {report.text_overlap:.1%}",
        "",
        "## Changes (by section)",
        "",
    ]

    for diff in report.diffs:
        icon = {"technical": "⚠️", "structural": "🔧", "editorial": "📝"}.get(
            diff.classification, ""
        )
        type_label = diff.change_type.upper()

        lines.append(f"### {diff.section_heading}")
        lines.append(f"**[{type_label}]** {icon} Classification: {diff.classification}")
        if diff.page_old and diff.page_new:
            lines.append(f"Pages: {diff.page_old} → {diff.page_new}")

        if diff.has_requirement_change:
            lines.append("⚠️ **Requirement language changed**")
        if diff.has_tbd_change:
            lines.append("📋 **TBD/TBR items changed**")

        if diff.old_text and diff.change_type != "added":
            old_preview = diff.old_text[:200].replace("\n", " ")
            lines.append(f"\n> Old: {old_preview}...")
        if diff.new_text and diff.change_type != "removed":
            new_preview = diff.new_text[:200].replace("\n", " ")
            lines.append(f"\n> New: {new_preview}...")

        if diff.ai_summary:
            lines.append(f"\n**AI Summary:** {diff.ai_summary}")

        lines.append("")

    lines.extend([
        "---",
        f"Generated: {report.generated_at}",
        f"Diff tokens: {report.total_diff_tokens} (estimated LLM cost: ${report.total_diff_tokens * 0.00006 / 1000:.4f})",
    ])

    return "\n".join(lines)


def _report_text(report: DiffReport) -> str:
    """Generate plain text report."""
    lines = [
        "DOCUMENT VERSION DIFFERENTIAL REPORT",
        "=" * 50,
        f"Version A: {report.version_a.filename} ({report.version_a.page_count} pages, Rev {report.version_a.revision})",
        f"Version B: {report.version_b.filename} ({report.version_b.page_count} pages, Rev {report.version_b.revision})",
        "",
        "SUMMARY",
        f"  Sections modified: {report.sections_modified}",
        f"  Sections added: {report.sections_added}",
        f"  Sections removed: {report.sections_removed}",
        f"  Requirement changes: {report.requirement_changes}",
        f"  TBD/TBR changes: {report.tbd_changes}",
        f"  Text overlap: {report.text_overlap:.1%}",
        "",
        "CHANGES",
        "-" * 50,
    ]

    for diff in report.diffs:
        lines.append(f"\n[{diff.change_type.upper()}] {diff.section_heading}")
        lines.append(f"  Classification: {diff.classification}")
        if diff.has_requirement_change:
            lines.append("  ⚠️  REQUIREMENT CHANGE")
        if diff.old_text:
            lines.append(f"  Old: {diff.old_text[:100].replace(chr(10), ' ')}...")
        if diff.new_text:
            lines.append(f"  New: {diff.new_text[:100].replace(chr(10), ' ')}...")

    lines.extend(["", "=" * 50, f"Generated: {report.generated_at}"])
    return "\n".join(lines)


def _report_html(report: DiffReport) -> str:
    """Generate HTML report."""
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>Document Version Differential Report</title>",
        "<style>body{font-family:sans-serif;max-width:900px;margin:0 auto;padding:20px;}",
        ".diff{margin:10px 0;padding:10px;border-radius:4px;}",
        ".modified{border-left:3px solid #ff9800;background:#fff8e1;}",
        ".added{border-left:3px solid #4caf50;background:#e8f5e9;}",
        ".removed{border-left:3px solid #f44336;background:#ffebee;}",
        ".warn{color:#e65100;font-weight:bold;}",
        "blockquote{margin:5px 0;padding:5px 10px;background:#f5f5f5;border-radius:3px;font-size:0.9em;}",
        "</style></head><body>",
        "<h1>Document Version Differential Report</h1>",
        f"<p><b>Version A:</b> {report.version_a.filename} ({report.version_a.page_count}pg, Rev {report.version_a.revision})</p>",
        f"<p><b>Version B:</b> {report.version_b.filename} ({report.version_b.page_count}pg, Rev {report.version_b.revision})</p>",
        f"<p>Modified: {report.sections_modified} | Added: {report.sections_added} | Removed: {report.sections_removed}</p>",
    ]

    for diff in report.diffs:
        cls = diff.change_type
        html.append(f"<div class='diff {cls}'>")
        html.append(f"<h3>{diff.section_heading} [{diff.change_type.upper()}]</h3>")
        if diff.has_requirement_change:
            html.append("<p class='warn'>⚠️ Requirement language changed</p>")
        if diff.old_text:
            html.append(f"<blockquote>Old: {diff.old_text[:200]}</blockquote>")
        if diff.new_text:
            html.append(f"<blockquote>New: {diff.new_text[:200]}</blockquote>")
        html.append("</div>")

    html.append(f"<hr><p>Generated: {report.generated_at}</p></body></html>")
    return "\n".join(html)
