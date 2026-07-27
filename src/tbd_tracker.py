"""TBD/TBR/TBC/TBS tracker.

Detects, catalogs, and tracks the status of open items in ICD documents.
Each TBD/TBR item gets:
- Unique ID
- Type (TBD, TBR, TBC, TBS)
- Status (open, in_progress, resolved)
- Location (page, block, context)
- Owner (responsible party, extracted from nearby text like 'UCB', 'SA')
- Resolution target date (if specified)
- Resolution value (what it was resolved to)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.models.document_ir import DocumentIR


TBX_PATTERN = re.compile(r"\b(TBD|TBR|TBC|TBS)\b")
OWNER_PATTERN = re.compile(r"\b(TBD|TBR|TBC|TBS)-(\w+)-(\d+)\b")


@dataclass
class TbxItem:
    """A single TBD/TBR/TBC/TBS item."""

    id: str  # e.g., "TBR-UCB-102"
    item_type: str  # TBD, TBR, TBC, TBS
    status: str = "open"  # open, in_progress, resolved
    page: int = 0
    block_id: str = ""
    context: str = ""  # surrounding text
    owner: Optional[str] = None  # responsible party
    target_date: Optional[str] = None
    resolution: Optional[str] = None
    resolved_date: Optional[str] = None


def scan_document(document_ir: DocumentIR) -> list[TbxItem]:
    """Scan a Document IR for all TBD/TBR/TBC/TBS items.

    Extracts items with their IDs (if present), context, and owner.
    """
    items: list[TbxItem] = []
    seen_ids: set[str] = set()
    counter = 0

    for page in document_ir.pages:
        for block in page.text_blocks:
            text = block.text_verbatim

            # Find items with full IDs like TBR-UCB-102
            for m in OWNER_PATTERN.finditer(text):
                item_id = m.group(0)
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Context
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 40)
                context = text[start:end].replace("\n", " ").strip()

                items.append(
                    TbxItem(
                        id=item_id,
                        item_type=m.group(1),
                        page=page.page_number,
                        block_id=block.id,
                        context=context,
                        owner=m.group(2),
                    )
                )

            # Find bare TBD/TBR without IDs
            for m in TBX_PATTERN.finditer(text):
                # Skip if this is part of a full ID we already captured
                full_match = OWNER_PATTERN.search(text[max(0, m.start()-5):m.end()+10])
                if full_match:
                    continue

                counter += 1
                item_id = f"{m.group(1)}-{counter:03d}"

                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 40)
                context = text[start:end].replace("\n", " ").strip()

                # Skip definition text ("TBD means...")
                if "means that" in context.lower() or "to be determined" in context.lower():
                    continue
                if "to be resolved" in context.lower():
                    continue

                items.append(
                    TbxItem(
                        id=item_id,
                        item_type=m.group(1),
                        page=page.page_number,
                        block_id=block.id,
                        context=context,
                    )
                )

    return items


def update_status(
    items: list[TbxItem], item_id: str, status: str, resolution: str = ""
) -> bool:
    """Update the status of a TBD/TBR item.

    Returns True if item was found and updated.
    """
    for item in items:
        if item.id == item_id:
            item.status = status
            if resolution:
                item.resolution = resolution
            return True
    return False


def summary_report(items: list[TbxItem]) -> str:
    """Generate a markdown summary of all TBD/TBR items."""
    open_items = [i for i in items if i.status == "open"]
    in_progress = [i for i in items if i.status == "in_progress"]
    resolved = [i for i in items if i.status == "resolved"]

    lines = []
    lines.append(f"# TBD/TBR Tracker ({len(items)} items)")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Open | {len(open_items)} |")
    lines.append(f"| In Progress | {len(in_progress)} |")
    lines.append(f"| Resolved | {len(resolved)} |")
    lines.append("")

    if open_items:
        lines.append("## Open Items")
        lines.append("")
        lines.append("| ID | Type | Page | Owner | Context |")
        lines.append("|----|----- |------|-------|---------|")
        for item in open_items:
            owner = item.owner or "—"
            ctx = item.context[:50].replace("|", "\\|")
            lines.append(f"| {item.id} | {item.item_type} | {item.page} | {owner} | {ctx} |")
        lines.append("")

    if resolved:
        lines.append("## Resolved Items")
        lines.append("")
        lines.append("| ID | Resolution |")
        lines.append("|----|-----------|")
        for item in resolved:
            lines.append(f"| {item.id} | {item.resolution or '—'} |")

    return "\n".join(lines)
