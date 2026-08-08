"""Section-level comparison between document revisions.

Builds on version_diff infrastructure but adds:
- Value change extraction per section
- TBD delta tracking (resolved vs introduced)
- Paragraph-level change counting
- One-line summary generation for the collapsed accordion view

All local processing — zero AWS cost.
"""

from __future__ import annotations

import difflib
import logging
import re
from pathlib import Path

from src.briefing.models import (
    ComparisonResult,
    DocumentSummary,
    SectionComparison,
    TbdDelta,
    TbdItem,
    ValueChange,
)
from src.briefing.value_extraction import (
    SpecValue,
    VALUE_PATTERN,
    TOLERANCE_PATTERN,
    _extract_keywords,
)
from src.tbd_tracker import TBX_PATTERN, OWNER_PATTERN
from src.version_diff import (
    _extract_sections,
    _extract_revision,
    _has_requirement_change,
    _classify_change,
)

logger = logging.getLogger(__name__)


def compare_revisions(
    path_a: str | Path,
    path_b: str | Path,
    summary_a: DocumentSummary | None = None,
    summary_b: DocumentSummary | None = None,
) -> ComparisonResult:
    """Compare two document revisions section by section.

    Produces a ComparisonResult with detailed per-section analysis including
    value changes, TBD deltas, and paragraph counts.

    Args:
        path_a: Path to the older revision PDF.
        path_b: Path to the newer revision PDF.
        summary_a: Pre-built DocumentSummary for doc A (optional).
        summary_b: Pre-built DocumentSummary for doc B (optional).

    Returns:
        ComparisonResult with all section comparisons.
    """
    from datetime import datetime, timezone

    path_a = Path(path_a)
    path_b = Path(path_b)

    # Extract sections from both documents
    sections_a = _extract_sections(path_a)
    sections_b = _extract_sections(path_b)

    # Build section comparisons
    section_results = _compare_sections(sections_a, sections_b)

    # Post-process: detect and filter boilerplate (repeated header/footer stamps)
    global_changes = _detect_and_filter_boilerplate(section_results)

    # Compute aggregate stats (after boilerplate filtering)
    total_value_changes = sum(len(s.value_changes) for s in section_results)
    total_tbds_resolved = sum(
        len(s.tbd_delta.resolved) for s in section_results if s.tbd_delta
    )
    total_tbds_introduced = sum(
        len(s.tbd_delta.introduced) for s in section_results if s.tbd_delta
    )
    total_changed = sum(
        1 for s in section_results if s.change_type != "unchanged"
    )
    total_unchanged = sum(
        1 for s in section_results if s.change_type == "unchanged"
    )

    result = ComparisonResult(
        document_a=summary_a or _quick_summary(path_a),
        document_b=summary_b or _quick_summary(path_b),
        sections=section_results,
        global_changes=global_changes,
        total_value_changes=total_value_changes,
        total_tbds_resolved=total_tbds_resolved,
        total_tbds_introduced=total_tbds_introduced,
        total_sections_changed=total_changed,
        total_sections_unchanged=total_unchanged,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    return result


def _quick_summary(path: Path) -> DocumentSummary:
    """Build a minimal DocumentSummary from a PDF path."""
    import fitz
    doc = fitz.open(str(path))
    first_text = doc[0].get_text()[:500]
    revision = _extract_revision(first_text)
    page_count = doc.page_count
    doc.close()

    return DocumentSummary(
        stem=path.stem,
        filename=path.name,
        path=str(path),
        revision=revision,
        date="",
        page_count=page_count,
        tbd_count=0,
        tbr_count=0,
    )


def _detect_and_filter_boilerplate(
    sections: list[SectionComparison],
    min_occurrences: int = 3,
) -> list[str]:
    """Detect repeated substitution patterns across sections and filter them out.

    Boilerplate = a word-level substitution snippet (contains '→') that appears
    in 3+ sections. This indicates a header/footer/stamp change, not real content.

    Added lines (starting with '+') are NOT treated as boilerplate even if repeated,
    because they represent real requirements being added to multiple sections.

    Returns:
        List of global change descriptions extracted from boilerplate.

    Side effects:
        - Removes boilerplate snippets from each section's text_snippets
        - Reclassifies sections that only had boilerplate as "unchanged"
        - Recalculates paragraph counts for affected sections
    """
    from collections import Counter

    # Collect all substitution-type snippets (contain → or are word changes)
    substitution_snippets: list[str] = []
    for s in sections:
        if s.change_type != "modified" or not s.text_snippets:
            continue
        for snippet in s.text_snippets:
            # Only count substitution patterns as potential boilerplate
            # Not additions (+) or removals (-) — those are real content changes
            if "→" in snippet and not snippet.startswith("+") and not snippet.startswith("-"):
                substitution_snippets.append(snippet)

    # Find patterns that repeat across many sections
    counts = Counter(substitution_snippets)
    boilerplate = {snippet for snippet, count in counts.items() if count >= min_occurrences}

    if not boilerplate:
        return []

    # Build global changes list from the boilerplate patterns
    global_changes = sorted(boilerplate)

    # Filter boilerplate from each section
    for s in sections:
        if s.change_type != "modified" or not s.text_snippets:
            continue

        # Remove boilerplate snippets
        filtered = [sn for sn in s.text_snippets if sn not in boilerplate]
        s.text_snippets = filtered

        # If section now has no real changes (no snippets, no value changes, no TBD changes)
        has_value_changes = len(s.value_changes) > 0
        has_tbd_changes = (
            s.tbd_delta is not None
            and (len(s.tbd_delta.resolved) > 0 or len(s.tbd_delta.introduced) > 0)
        )
        has_text_changes = len(filtered) > 0

        if not has_value_changes and not has_tbd_changes and not has_text_changes:
            # This section only had boilerplate — mark as unchanged
            s.change_type = "unchanged"
            s.paragraphs_modified = 0
            s.paragraphs_added = 0
            s.paragraphs_removed = 0
            s.classification = "editorial"
            s.has_requirement_change = False
            s.summary_line = "no changes"

    return global_changes


def _compare_sections(
    sections_a: list[dict],
    sections_b: list[dict],
) -> list[SectionComparison]:
    """Compare aligned sections and produce SectionComparison objects."""
    results: list[SectionComparison] = []

    # Build lookups
    lookup_a = {s["heading"].lower().strip(): s for s in sections_a}
    lookup_b = {s["heading"].lower().strip(): s for s in sections_b}

    headings_a = set(lookup_a.keys())
    headings_b = set(lookup_b.keys())

    # Sections in both
    for heading_key in sorted(headings_a & headings_b):
        sec_a = lookup_a[heading_key]
        sec_b = lookup_b[heading_key]

        text_a = sec_a["text"].strip()
        text_b = sec_b["text"].strip()

        if text_a == text_b:
            results.append(SectionComparison(
                section_heading=sec_b["heading"],
                change_type="unchanged",
                page_old=sec_a["page"],
                page_new=sec_b["page"],
                summary_line="no changes",
            ))
            continue

        # Compute paragraph-level changes
        paras_a = [p.strip() for p in text_a.split("\n") if p.strip()]
        paras_b = [p.strip() for p in text_b.split("\n") if p.strip()]
        para_diff = _count_paragraph_changes(paras_a, paras_b)

        # Extract value changes within this section
        values_a = _extract_values_from_text(text_a, sec_a["page"])
        values_b = _extract_values_from_text(text_b, sec_b["page"])
        value_changes = _find_value_changes_in_section(values_a, values_b)

        # TBD delta
        tbd_delta = _compute_tbd_delta(text_a, text_b, sec_a["page"], sec_b["page"])

        # Classification — use structured results to override text-based heuristic
        classification = _classify_change(text_a, text_b)
        has_req_change = _has_requirement_change(text_a, text_b)

        # Override: if we found value changes with units, it's technical
        if value_changes:
            classification = "technical"
        # Override: if TBDs were resolved or introduced, it's technical
        if tbd_delta.resolved or tbd_delta.introduced:
            classification = "technical"
            has_req_change = True

        # Build summary line
        summary_line = _build_summary_line(
            value_changes, tbd_delta, para_diff, classification
        )

        results.append(SectionComparison(
            section_heading=sec_b["heading"],
            change_type="modified",
            paragraphs_modified=para_diff["modified"],
            paragraphs_added=para_diff["added"],
            paragraphs_removed=para_diff["removed"],
            value_changes=value_changes,
            tbd_delta=tbd_delta,
            text_snippets=_extract_diff_snippets(paras_a, paras_b),
            classification=classification,
            has_requirement_change=has_req_change,
            page_old=sec_a["page"],
            page_new=sec_b["page"],
            summary_line=summary_line,
        ))

    # Sections only in B (added)
    for heading_key in sorted(headings_b - headings_a):
        sec_b = lookup_b[heading_key]
        text_b = sec_b["text"].strip()
        paras = len([p for p in text_b.split("\n") if p.strip()])

        results.append(SectionComparison(
            section_heading=sec_b["heading"],
            change_type="added",
            paragraphs_added=paras,
            classification="structural",
            page_new=sec_b["page"],
            summary_line="new section",
        ))

    # Sections only in A (removed)
    for heading_key in sorted(headings_a - headings_b):
        sec_a = lookup_a[heading_key]
        text_a = sec_a["text"].strip()
        paras = len([p for p in text_a.split("\n") if p.strip()])

        results.append(SectionComparison(
            section_heading=sec_a["heading"],
            change_type="removed",
            paragraphs_removed=paras,
            classification="structural",
            page_old=sec_a["page"],
            summary_line="section removed",
        ))

    return results


def _count_paragraph_changes(paras_a: list[str], paras_b: list[str]) -> dict[str, int]:
    """Count paragraph-level additions, removals, and modifications."""
    matcher = difflib.SequenceMatcher(None, paras_a, paras_b)
    added = 0
    removed = 0
    modified = 0

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        elif op == "insert":
            added += j2 - j1
        elif op == "delete":
            removed += i2 - i1
        elif op == "replace":
            # Count the minimum as modified, extras as added/removed
            count_a = i2 - i1
            count_b = j2 - j1
            modified += min(count_a, count_b)
            if count_b > count_a:
                added += count_b - count_a
            elif count_a > count_b:
                removed += count_a - count_b

    return {"added": added, "removed": removed, "modified": modified}


def _extract_values_from_text(text: str, page: int) -> list[SpecValue]:
    """Extract spec values from a section's text."""
    specs: list[SpecValue] = []

    for match in VALUE_PATTERN.finditer(text):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        unit = match.group(2)
        start = max(0, match.start() - 60)
        end = min(len(text), match.end() + 60)
        context = text[start:end].replace("\n", " ").strip()
        keywords = _extract_keywords(context)
        specs.append(SpecValue(
            value=value, unit=unit, context=context,
            page=page, keywords=keywords,
        ))

    for match in TOLERANCE_PATTERN.finditer(text):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        unit = f"±{match.group(2)}"
        start = max(0, match.start() - 60)
        end = min(len(text), match.end() + 60)
        context = text[start:end].replace("\n", " ").strip()
        keywords = _extract_keywords(context)
        specs.append(SpecValue(
            value=value, unit=unit, context=context,
            page=page, keywords=keywords,
        ))

    return specs


def _find_value_changes_in_section(
    values_a: list[SpecValue],
    values_b: list[SpecValue],
) -> list[ValueChange]:
    """Find value changes within a single section between two revisions."""
    changes: list[ValueChange] = []
    matched_b: set[int] = set()

    for spec_a in values_a:
        target_unit = spec_a.unit.lstrip("±")
        best_idx = None
        best_score = 0

        for i, spec_b in enumerate(values_b):
            if i in matched_b:
                continue
            candidate_unit = spec_b.unit.lstrip("±")
            if target_unit != candidate_unit:
                continue
            shared = set(spec_a.keywords) & set(spec_b.keywords)
            score = len(shared)
            if score >= 2 and score > best_score:
                best_score = score
                best_idx = i

        if best_idx is not None:
            spec_b = values_b[best_idx]
            if spec_a.value != spec_b.value:
                shared = set(spec_a.keywords) & set(spec_b.keywords)
                parameter = " ".join(sorted(shared)[:4]) if shared else spec_a.context[:30]
                changes.append(ValueChange(
                    parameter=parameter,
                    old_value=spec_a.value,
                    new_value=spec_b.value,
                    unit=spec_a.unit,
                    old_context=spec_a.context,
                    new_context=spec_b.context,
                    page_old=spec_a.page,
                    page_new=spec_b.page,
                ))
                matched_b.add(best_idx)

    return changes


def _compute_tbd_delta(
    text_a: str, text_b: str, page_a: int, page_b: int
) -> TbdDelta:
    """Compute TBD/TBR changes between old and new section text."""
    delta = TbdDelta()

    # Find all TBD/TBR items in old text
    tbds_a = _find_tbds_in_text(text_a, page_a)
    tbds_b = _find_tbds_in_text(text_b, page_b)

    # Compare by ID or context
    ids_a = {t.id for t in tbds_a}
    ids_b = {t.id for t in tbds_b}

    # Resolved: in A but not in B
    for tbd in tbds_a:
        if tbd.id not in ids_b:
            tbd.status = "resolved"
            delta.resolved.append(tbd)

    # Introduced: in B but not in A
    for tbd in tbds_b:
        if tbd.id not in ids_a:
            tbd.status = "open"
            delta.introduced.append(tbd)

    # Unchanged: in both
    for tbd in tbds_b:
        if tbd.id in ids_a:
            delta.unchanged.append(tbd)

    return delta


def _find_tbds_in_text(text: str, page: int) -> list[TbdItem]:
    """Find TBD/TBR items in a section's text."""
    items: list[TbdItem] = []
    seen_ids: set[str] = set()

    # Full IDs like TBR-UCB-102
    for m in OWNER_PATTERN.finditer(text):
        item_id = m.group(0)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        context = text[start:end].replace("\n", " ").strip()
        items.append(TbdItem(
            id=item_id,
            item_type=m.group(1),
            status="open",
            page=page,
            context=context,
            owner=m.group(2),
        ))

    # Bare TBD/TBR
    counter = 0
    for m in TBX_PATTERN.finditer(text):
        # Skip if part of a full ID
        check_start = max(0, m.start() - 5)
        check_end = min(len(text), m.end() + 10)
        if OWNER_PATTERN.search(text[check_start:check_end]):
            continue
        counter += 1
        item_id = f"{m.group(1)}-{page:03d}-{counter:02d}"
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        context = text[start:end].replace("\n", " ").strip()
        # Skip definitions
        if "means that" in context.lower() or "to be determined" in context.lower():
            continue
        if "to be resolved" in context.lower():
            continue
        items.append(TbdItem(
            id=item_id,
            item_type=m.group(1),
            status="open",
            page=page,
            context=context,
        ))

    return items


def _extract_diff_snippets(
    paras_a: list[str], paras_b: list[str], max_snippets: int = 5
) -> list[str]:
    """Extract human-readable diff snippets showing what actually changed.

    Returns up to max_snippets short descriptions like:
    - "HSI_SYS_001H.doc → HSI_SYS_001I.doc"
    - "+ Added: 'New requirement for thermal margin'"
    - "- Removed: 'Old connector pinout reference'"
    """
    snippets: list[str] = []
    matcher = difflib.SequenceMatcher(None, paras_a, paras_b)

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if len(snippets) >= max_snippets:
            break

        if op == "equal":
            continue
        elif op == "replace":
            # Show what changed (old → new)
            for k in range(min(i2 - i1, max_snippets - len(snippets))):
                old_line = paras_a[i1 + k][:80].strip()
                if k < (j2 - j1):
                    new_line = paras_b[j1 + k][:80].strip()
                    # Find the specific difference
                    diff_desc = _describe_line_change(old_line, new_line)
                    if diff_desc:
                        snippets.append(diff_desc)
                    else:
                        snippets.append(f"Changed: \"{old_line[:50]}...\"")
                else:
                    snippets.append(f"- \"{old_line[:60]}\"")
        elif op == "insert":
            for k in range(min(j2 - j1, max_snippets - len(snippets))):
                new_line = paras_b[j1 + k][:70].strip()
                if new_line:
                    snippets.append(f"+ \"{new_line[:60]}\"")
        elif op == "delete":
            for k in range(min(i2 - i1, max_snippets - len(snippets))):
                old_line = paras_a[i1 + k][:70].strip()
                if old_line:
                    snippets.append(f"- \"{old_line[:60]}\"")

    return snippets


def _describe_line_change(old: str, new: str) -> str | None:
    """Try to produce a concise description of what changed between two lines."""
    # If lines are very similar, find the specific word that changed
    old_words = old.split()
    new_words = new.split()

    if len(old_words) == len(new_words) and len(old_words) > 0:
        diffs = [(o, n) for o, n in zip(old_words, new_words) if o != n]
        if 1 <= len(diffs) <= 3:
            changes = [f"{o} → {n}" for o, n in diffs]
            return ", ".join(changes)

    # If one line is a subset of the other (something added/removed)
    if old in new:
        added = new.replace(old, "").strip()
        if added and len(added) < 60:
            return f"+ \"{added}\""
    if new in old:
        removed = old.replace(new, "").strip()
        if removed and len(removed) < 60:
            return f"- \"{removed}\""

    return None


def _build_summary_line(
    value_changes: list[ValueChange],
    tbd_delta: TbdDelta,
    para_diff: dict[str, int],
    classification: str,
) -> str:
    """Build a one-line summary for the collapsed accordion view."""
    parts: list[str] = []

    if value_changes:
        n = len(value_changes)
        parts.append(f"{n} value{'s' if n != 1 else ''} changed")

    if tbd_delta.resolved:
        n = len(tbd_delta.resolved)
        parts.append(f"{n} TBD{'s' if n != 1 else ''} resolved")

    if tbd_delta.introduced:
        n = len(tbd_delta.introduced)
        parts.append(f"{n} TBD{'s' if n != 1 else ''} introduced")

    if not parts:
        # Fall back to paragraph-level description
        total_changes = para_diff["modified"] + para_diff["added"] + para_diff["removed"]
        if total_changes > 0:
            parts.append(f"{total_changes} paragraph{'s' if total_changes != 1 else ''} modified")
        else:
            parts.append(f"{classification} changes")

    return ", ".join(parts)
