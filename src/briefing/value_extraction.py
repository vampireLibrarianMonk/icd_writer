"""Specification value extraction and conflict detection.

Extracts numerical values with units from document text blocks,
then compares across documents or revisions to find changes and
conflicts. Uses regex only — no LLM calls.

All local processing — zero AWS cost.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from src.briefing.models import ValueChange, ValueConflict
from src.models.document_ir import DocumentIR

logger = logging.getLogger(__name__)

# Pattern for numerical values with engineering units
# Captures: optional sign, number (with optional decimal), optional space, unit
VALUE_PATTERN = re.compile(
    r'([+-]?\d+\.?\d*)\s*'
    r'(V|kV|mV|'           # Voltage
    r'W|kW|mW|'            # Power
    r'A|mA|µA|'            # Current
    r'MHz|GHz|kHz|Hz|'     # Frequency
    r'Mbps|kbps|bps|Gbps|' # Data rate
    r'mm|cm|m|km|µm|'      # Length
    r'kg|g|mg|lb|lbs|'     # Mass
    r'°C|°F|K|'            # Temperature
    r'psi|Pa|kPa|MPa|atm|' # Pressure
    r'ft-lb|Nm|N|kN|'      # Force/Torque
    r'dB|dBm|dBW|'         # Signal
    r'ms|µs|ns|s|min|hr|'  # Time
    r'deg|rad|'            # Angle
    r'Ohm|kOhm|MOhm|'     # Resistance
    r'bits?|bytes?|KB|MB|GB|TB)' # Data size
    r'\b'
)

# Tolerance pattern: ±value unit
TOLERANCE_PATTERN = re.compile(
    r'[±]\s*(\d+\.?\d*)\s*'
    r'(mm|cm|m|µm|°C|°F|K|V|mV|A|mA|deg|%)'
)

# Context window (characters before/after the value match) for keyword extraction
CONTEXT_WINDOW = 60


@dataclass
class SpecValue:
    """A single extracted specification value with context."""

    value: float
    unit: str
    context: str  # surrounding text for matching
    page: int
    block_id: str = ""
    keywords: list[str] = field(default_factory=list)  # significant words nearby


def extract_specifications(ir: DocumentIR) -> list[SpecValue]:
    """Extract all specification values (number + unit) from a document.

    Args:
        ir: Document IR to extract values from.

    Returns:
        List of SpecValue objects with their context and page.
    """
    specs: list[SpecValue] = []

    for page in ir.pages:
        for block in page.text_blocks:
            text = block.text_verbatim
            if not text or len(text) < 3:
                continue

            # Find all value+unit matches
            for match in VALUE_PATTERN.finditer(text):
                value_str = match.group(1)
                unit = match.group(2)

                try:
                    value = float(value_str)
                except ValueError:
                    continue

                # Extract context around the match
                start = max(0, match.start() - CONTEXT_WINDOW)
                end = min(len(text), match.end() + CONTEXT_WINDOW)
                context = text[start:end].replace("\n", " ").strip()

                # Extract keywords from context
                keywords = _extract_keywords(context)

                specs.append(SpecValue(
                    value=value,
                    unit=unit,
                    context=context,
                    page=page.page_number,
                    block_id=block.id,
                    keywords=keywords,
                ))

            # Also find tolerance patterns
            for match in TOLERANCE_PATTERN.finditer(text):
                value_str = match.group(1)
                unit = match.group(2)

                try:
                    value = float(value_str)
                except ValueError:
                    continue

                start = max(0, match.start() - CONTEXT_WINDOW)
                end = min(len(text), match.end() + CONTEXT_WINDOW)
                context = text[start:end].replace("\n", " ").strip()
                keywords = _extract_keywords(context)

                specs.append(SpecValue(
                    value=value,
                    unit=f"±{unit}",
                    context=context,
                    page=page.page_number,
                    block_id=block.id,
                    keywords=keywords,
                ))

    return specs


def detect_value_changes(
    specs_old: list[SpecValue],
    specs_new: list[SpecValue],
) -> list[ValueChange]:
    """Detect specification values that changed between two revisions.

    Matches values by shared keywords + same unit, then checks if the
    numeric value differs.

    Args:
        specs_old: Spec values from the older revision.
        specs_new: Spec values from the newer revision.

    Returns:
        List of ValueChange objects for values that differ.
    """
    changes: list[ValueChange] = []
    matched_new: set[int] = set()

    for spec_old in specs_old:
        best_match_idx = _find_best_match(spec_old, specs_new, matched_new)
        if best_match_idx is None:
            continue

        spec_new = specs_new[best_match_idx]

        # Same unit, different value = change
        if spec_old.value != spec_new.value:
            # Build a parameter name from shared keywords
            shared = set(spec_old.keywords) & set(spec_new.keywords)
            parameter = " ".join(sorted(shared)[:4]) if shared else spec_old.context[:30]

            changes.append(ValueChange(
                parameter=parameter,
                old_value=spec_old.value,
                new_value=spec_new.value,
                unit=spec_old.unit,
                old_context=spec_old.context,
                new_context=spec_new.context,
                page_old=spec_old.page,
                page_new=spec_new.page,
            ))
            matched_new.add(best_match_idx)

    return changes


def detect_value_conflicts(
    specs_a: list[SpecValue],
    specs_b: list[SpecValue],
    doc_a_stem: str = "",
    doc_b_stem: str = "",
) -> list[ValueConflict]:
    """Detect value conflicts between two different documents.

    Same logic as detect_value_changes but for cross-document comparison.
    Only flags conflicts where the same parameter (by keyword match) has
    different values.

    Args:
        specs_a: Spec values from document A.
        specs_b: Spec values from document B.
        doc_a_stem: Document A identifier.
        doc_b_stem: Document B identifier.

    Returns:
        List of ValueConflict objects.
    """
    conflicts: list[ValueConflict] = []
    matched_b: set[int] = set()

    for spec_a in specs_a:
        best_match_idx = _find_best_match(spec_a, specs_b, matched_b)
        if best_match_idx is None:
            continue

        spec_b = specs_b[best_match_idx]

        # Same unit, different value = conflict
        if spec_a.value != spec_b.value:
            shared = set(spec_a.keywords) & set(spec_b.keywords)
            parameter = " ".join(sorted(shared)[:4]) if shared else spec_a.context[:30]

            conflicts.append(ValueConflict(
                parameter=parameter,
                value_a=spec_a.value,
                value_b=spec_b.value,
                unit=spec_a.unit,
                context_a=spec_a.context,
                context_b=spec_b.context,
                document_a=doc_a_stem,
                document_b=doc_b_stem,
                page_a=spec_a.page,
                page_b=spec_b.page,
            ))
            matched_b.add(best_match_idx)

    return conflicts


def _find_best_match(
    target: SpecValue,
    candidates: list[SpecValue],
    excluded: set[int],
) -> int | None:
    """Find the best matching spec value in candidates by keywords + unit.

    Returns the index of the best match, or None if no good match found.
    """
    best_idx = None
    best_score = 0

    # Normalize unit for comparison (strip ± prefix for tolerance matching)
    target_unit = target.unit.lstrip("±")

    for i, candidate in enumerate(candidates):
        if i in excluded:
            continue

        candidate_unit = candidate.unit.lstrip("±")
        if target_unit != candidate_unit:
            continue

        # Score by keyword overlap
        shared = set(target.keywords) & set(candidate.keywords)
        score = len(shared)

        # Require at least 2 shared keywords for a match
        if score >= 2 and score > best_score:
            best_score = score
            best_idx = i

    return best_idx


def _extract_keywords(text: str) -> list[str]:
    """Extract significant keywords from context text.

    Filters out common words, numbers, and units to get meaningful
    parameter names and descriptors.
    """
    # Common stop words + engineering fluff
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can",
        "had", "her", "was", "one", "our", "this", "that", "with", "from",
        "have", "been", "will", "shall", "must", "may", "should", "per",
        "each", "than", "its", "also", "between", "into", "any", "only",
        "over", "such", "after", "before", "other", "which", "their",
        "there", "when", "what", "where", "more", "less", "most",
        "tbd", "tbr", "tbc", "tbs", "ref", "see", "note",
    }

    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [w for w in words if w not in stop_words]
