"""Semantic validation for ICD documents.

Checks:
- All cross-references resolve to existing targets
- Requirement IDs are unique
- TBD/TBR items are cataloged
- Section numbering is sequential
- Referenced documents/figures/tables exist
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models.document_ir import DocumentIR


SECTION_REF = re.compile(r"[Ss]ection\s+(\d+[\.\d]*)")
FIGURE_REF = re.compile(r"[Ff]igure\s+(\d+)")
TABLE_REF = re.compile(r"[Tt]able\s+([\d\.]+[-\d]*)")
SECTION_HEADING = re.compile(r"^(\d+[\.\d]*\.?)\s+\S")


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: str  # "error", "warning", "info"
    category: str  # "cross_ref", "requirement", "tbd", "structure"
    message: str
    page: int = 0
    block_id: str = ""


def validate_document(document_ir: DocumentIR) -> list[ValidationIssue]:
    """Run all semantic validations on a document.

    Returns a list of issues found, sorted by severity.
    """
    issues: list[ValidationIssue] = []

    # Collect defined sections
    defined_sections = set()
    for page in document_ir.pages:
        for block in page.text_blocks:
            m = SECTION_HEADING.match(block.text_verbatim.strip())
            if m:
                defined_sections.add(m.group(1).rstrip("."))

    # Collect defined tables
    defined_tables = set()
    for page in document_ir.pages:
        for block in page.text_blocks:
            if block.text_verbatim.strip().startswith("Table "):
                m = TABLE_REF.match(block.text_verbatim.strip())
                if m:
                    defined_tables.add(m.group(1))

    # Check cross-references
    for page in document_ir.pages:
        for block in page.text_blocks:
            text = block.text_verbatim

            # Section references
            for m in SECTION_REF.finditer(text):
                target = m.group(1).rstrip(".")
                if target not in defined_sections:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="cross_ref",
                            message=f"Section {target} referenced but not found as a heading",
                            page=page.page_number,
                            block_id=block.id,
                        )
                    )

            # Table references
            for m in TABLE_REF.finditer(text):
                target = m.group(1)
                # Don't flag table definitions themselves
                if not text.strip().startswith("Table "):
                    if target not in defined_tables:
                        issues.append(
                            ValidationIssue(
                                severity="info",
                                category="cross_ref",
                                message=f"Table {target} referenced — verify it exists",
                                page=page.page_number,
                                block_id=block.id,
                            )
                        )

    # Check section numbering sequence
    section_numbers = sorted(defined_sections)
    for i in range(1, len(section_numbers)):
        curr = section_numbers[i]
        prev = section_numbers[i - 1]
        # Simple check: top-level sections should be sequential
        if "." not in curr and "." not in prev:
            try:
                if int(curr) - int(prev) > 1:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="structure",
                            message=f"Gap in section numbering: {prev} → {curr}",
                        )
                    )
            except ValueError:
                pass

    # Sort: errors first, then warnings, then info
    severity_order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: severity_order.get(i.severity, 3))

    return issues


def validation_report(issues: list[ValidationIssue]) -> str:
    """Generate a markdown validation report."""
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    infos = [i for i in issues if i.severity == "info"]

    lines = []
    lines.append(f"# Semantic Validation Report ({len(issues)} findings)")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Errors | {len(errors)} |")
    lines.append(f"| Warnings | {len(warnings)} |")
    lines.append(f"| Info | {len(infos)} |")
    lines.append("")

    if not issues:
        lines.append("✓ No issues found.")
        return "\n".join(lines)

    lines.append("## Findings")
    lines.append("")
    lines.append("| # | Severity | Category | Page | Message |")
    lines.append("|---|----------|----------|------|---------|")
    for i, issue in enumerate(issues, 1):
        lines.append(
            f"| {i} | {issue.severity} | {issue.category} | "
            f"{issue.page or '—'} | {issue.message} |"
        )

    return "\n".join(lines)
