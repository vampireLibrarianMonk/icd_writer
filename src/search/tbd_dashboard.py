"""TBD Dashboard — Cross-document TBD/TBR tracking and correlation.

Surfaces all TBD/TBR items across the indexed ICD corpus with:
- Cross-document correlation (same TBD in provider and user ICDs)
- Status lifecycle tracking (open → assigned → resolved → verified)
- Ownership and target date management
- Filtering and export capabilities

Builds on the existing src/tbd_tracker.py for per-document extraction.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import SearchConfig, TITAN_V2_PARAGRAPH
from .embeddings import EmbeddingClient
from .indexing import IndexManager

logger = logging.getLogger(__name__)


@dataclass
class TBDItem:
    """A TBD/TBR item with full dashboard metadata."""

    # Identity
    item_id: str  # e.g., "TBD-001" or "TBR-UCB-102"
    item_type: str  # TBD, TBR, TBC, TBS
    # Source
    document_hash: str
    document_title: str
    page_number: int
    section_heading: str | None = None
    section_number: str | None = None
    context: str = ""  # Surrounding text
    # Status lifecycle
    status: str = "open"  # open, assigned, resolved, verified
    owner: str | None = None
    target_date: str | None = None
    resolution_value: str | None = None
    resolution_rationale: str | None = None
    resolved_date: str | None = None
    resolved_by: str | None = None
    # Classification
    in_shall_statement: bool = False
    content_type: str = "paragraph"  # paragraph, table, figure
    # Cross-document correlation
    correlated_items: list[str] = field(default_factory=list)  # IDs of related TBDs
    correlation_confidence: str | None = None  # high, medium, low
    # Audit
    created_date: str = ""
    last_modified: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TBDCorrelation:
    """A correlation between TBD items across documents."""

    item_a_id: str
    item_b_id: str
    confidence: str  # high, medium, low
    reason: str  # Why these are linked
    conflict: bool = False  # True if resolved differently
    conflict_detail: str | None = None


@dataclass
class DashboardStats:
    """Aggregate statistics for the TBD dashboard."""

    total_items: int = 0
    open_count: int = 0
    assigned_count: int = 0
    resolved_count: int = 0
    verified_count: int = 0
    # By type
    tbd_count: int = 0
    tbr_count: int = 0
    # By severity
    in_shall_statements: int = 0
    # Cross-document
    correlated_pairs: int = 0
    conflicts: int = 0
    # Age
    oldest_days: int = 0
    avg_age_days: int = 0
    # Documents
    documents_count: int = 0


class TBDDashboard:
    """Cross-document TBD/TBR tracking dashboard.

    Aggregates TBD items from all indexed documents, correlates them
    across document boundaries, and provides filtering/export.
    """

    def __init__(self, search_config: SearchConfig | None = None,
                 state_path: str | Path | None = None,
                 region: str = "us-east-1") -> None:
        self.config = search_config or SearchConfig(aws_region=region)
        self.region = region
        self.state_path = Path(state_path) if state_path else Path(
            "output/tbd_dashboard_state.json"
        )
        self._items: dict[str, TBDItem] = {}
        self._correlations: list[TBDCorrelation] = []
        self._embed_client: EmbeddingClient | None = None
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted dashboard state."""
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            for item_data in data.get("items", []):
                item = TBDItem(**{k: v for k, v in item_data.items()
                                  if k in TBDItem.__dataclass_fields__})
                self._items[item.item_id] = item
            for corr_data in data.get("correlations", []):
                self._correlations.append(TBDCorrelation(**corr_data))

    def save_state(self) -> None:
        """Persist dashboard state."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "item_id": item.item_id,
                    "item_type": item.item_type,
                    "document_hash": item.document_hash,
                    "document_title": item.document_title,
                    "page_number": item.page_number,
                    "section_heading": item.section_heading,
                    "section_number": item.section_number,
                    "context": item.context,
                    "status": item.status,
                    "owner": item.owner,
                    "target_date": item.target_date,
                    "resolution_value": item.resolution_value,
                    "resolution_rationale": item.resolution_rationale,
                    "resolved_date": item.resolved_date,
                    "resolved_by": item.resolved_by,
                    "in_shall_statement": item.in_shall_statement,
                    "content_type": item.content_type,
                    "correlated_items": item.correlated_items,
                    "correlation_confidence": item.correlation_confidence,
                    "created_date": item.created_date,
                    "last_modified": item.last_modified,
                }
                for item in self._items.values()
            ],
            "correlations": [
                {
                    "item_a_id": c.item_a_id,
                    "item_b_id": c.item_b_id,
                    "confidence": c.confidence,
                    "reason": c.reason,
                    "conflict": c.conflict,
                    "conflict_detail": c.conflict_detail,
                }
                for c in self._correlations
            ],
        }
        self.state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def ingest_document(self, ir_path: str | Path) -> int:
        """Extract TBD items from a Document IR and add to dashboard.

        Returns number of new items added.
        """
        import yaml
        from src.tbd_tracker import scan_document
        from src.models.document_ir import DocumentIR

        ir_path = Path(ir_path)
        with open(ir_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        # Load as DocumentIR
        doc_ir = DocumentIR.model_validate(raw)
        metadata = raw.get("metadata", {})
        doc_hash = metadata.get("sha256", ir_path.stem)
        # Use filename (stem of IR path) as the document title for display
        # PDF metadata titles are often garbage (section headings, "Microsoft Word - ...")
        doc_title = metadata.get("filename", ir_path.stem.replace("_document_ir", ""))
        if not doc_title or doc_title.startswith("Microsoft Word"):
            doc_title = ir_path.stem.replace("_document_ir", "")

        # Extract using existing tracker
        tbx_items = scan_document(doc_ir)

        now = datetime.now(timezone.utc).isoformat()
        new_count = 0

        for tbx in tbx_items:
            # Create unique ID scoped to document
            dashboard_id = f"{doc_hash[:8]}_{tbx.id}"

            if dashboard_id in self._items:
                continue  # Already tracked

            # Determine if in a "shall" statement
            in_shall = "shall" in tbx.context.lower()

            self._items[dashboard_id] = TBDItem(
                item_id=dashboard_id,
                item_type=tbx.item_type,
                document_hash=doc_hash,
                document_title=doc_title,
                page_number=tbx.page,
                context=tbx.context,
                status=tbx.status if tbx.status != "open" else "open",
                owner=tbx.owner,
                target_date=tbx.target_date,
                resolution_value=tbx.resolution,
                in_shall_statement=in_shall,
                created_date=now,
                last_modified=now,
            )
            new_count += 1

        logger.info(f"Ingested {new_count} new TBD items from {doc_title}")
        return new_count

    def correlate(self) -> list[TBDCorrelation]:
        """Find correlated TBD items across documents using semantic similarity.

        Two TBDs are correlated if:
        1. They are in different documents
        2. Their context text has high semantic similarity
        3. They share section heading patterns
        """
        if not self._embed_client:
            self._embed_client = EmbeddingClient(
                TITAN_V2_PARAGRAPH.embedding_config, region=self.region
            )

        # Group items by document
        by_doc: dict[str, list[TBDItem]] = {}
        for item in self._items.values():
            by_doc.setdefault(item.document_hash, []).append(item)

        if len(by_doc) < 2:
            logger.info("Need items from at least 2 documents to correlate")
            return []

        # Embed all item contexts
        all_items = list(self._items.values())
        contexts = [item.context for item in all_items]
        embeddings = self._embed_client.embed_texts(contexts)

        # Find cross-document pairs with high similarity
        import numpy as np
        vectors = np.array(embeddings)
        # Normalize
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vectors = vectors / norms

        new_correlations = []
        for i in range(len(all_items)):
            for j in range(i + 1, len(all_items)):
                # Must be different documents
                if all_items[i].document_hash == all_items[j].document_hash:
                    continue

                # Compute cosine similarity
                sim = float(np.dot(vectors[i], vectors[j]))

                if sim > 0.75:
                    confidence = "high" if sim > 0.85 else "medium"
                    reason = (
                        f"Semantic similarity {sim:.2f} between contexts in "
                        f"{all_items[i].document_title} and {all_items[j].document_title}"
                    )

                    # Check for conflict (both resolved but different values)
                    conflict = False
                    conflict_detail = None
                    if (all_items[i].resolution_value and all_items[j].resolution_value
                            and all_items[i].resolution_value != all_items[j].resolution_value):
                        conflict = True
                        conflict_detail = (
                            f"Resolved as '{all_items[i].resolution_value}' in "
                            f"{all_items[i].document_title} but "
                            f"'{all_items[j].resolution_value}' in "
                            f"{all_items[j].document_title}"
                        )

                    corr = TBDCorrelation(
                        item_a_id=all_items[i].item_id,
                        item_b_id=all_items[j].item_id,
                        confidence=confidence,
                        reason=reason,
                        conflict=conflict,
                        conflict_detail=conflict_detail,
                    )
                    new_correlations.append(corr)

                    # Link items
                    all_items[i].correlated_items.append(all_items[j].item_id)
                    all_items[j].correlated_items.append(all_items[i].item_id)
                    all_items[i].correlation_confidence = confidence
                    all_items[j].correlation_confidence = confidence

        self._correlations = new_correlations
        logger.info(f"Found {len(new_correlations)} cross-document correlations")
        return new_correlations

    def update_status(self, item_id: str, status: str,
                      owner: str | None = None,
                      resolution_value: str | None = None,
                      rationale: str | None = None,
                      resolved_by: str | None = None) -> bool:
        """Update a TBD item's status."""
        if item_id not in self._items:
            return False

        item = self._items[item_id]
        now = datetime.now(timezone.utc).isoformat()

        # Record history
        item.history.append({
            "timestamp": now,
            "field": "status",
            "old_value": item.status,
            "new_value": status,
            "by": resolved_by,
        })

        item.status = status
        item.last_modified = now

        if owner:
            item.owner = owner
        if resolution_value:
            item.resolution_value = resolution_value
        if rationale:
            item.resolution_rationale = rationale
        if status == "resolved":
            item.resolved_date = now
            item.resolved_by = resolved_by

        self.save_state()
        return True

    def get_stats(self) -> DashboardStats:
        """Get aggregate statistics."""
        items = list(self._items.values())
        if not items:
            return DashboardStats()

        docs = set(i.document_hash for i in items)

        return DashboardStats(
            total_items=len(items),
            open_count=sum(1 for i in items if i.status == "open"),
            assigned_count=sum(1 for i in items if i.status == "assigned"),
            resolved_count=sum(1 for i in items if i.status == "resolved"),
            verified_count=sum(1 for i in items if i.status == "verified"),
            tbd_count=sum(1 for i in items if i.item_type == "TBD"),
            tbr_count=sum(1 for i in items if i.item_type == "TBR"),
            in_shall_statements=sum(1 for i in items if i.in_shall_statement),
            correlated_pairs=len(self._correlations),
            conflicts=sum(1 for c in self._correlations if c.conflict),
            documents_count=len(docs),
        )

    def filter_items(self, status: str | None = None,
                     item_type: str | None = None,
                     document: str | None = None,
                     owner: str | None = None,
                     in_shall: bool | None = None) -> list[TBDItem]:
        """Filter TBD items by criteria."""
        results = list(self._items.values())

        if status:
            results = [i for i in results if i.status == status]
        if item_type:
            results = [i for i in results if i.item_type == item_type.upper()]
        if document:
            doc_lower = document.lower()
            results = [i for i in results
                       if doc_lower in i.document_title.lower()]
        if owner:
            results = [i for i in results if i.owner and owner.lower() in i.owner.lower()]
        if in_shall is not None:
            results = [i for i in results if i.in_shall_statement == in_shall]

        return results

    def export_csv(self) -> str:
        """Export all items as CSV."""
        lines = [
            "ID,Type,Status,Document,Page,Section,Owner,Target Date,"
            "In Shall,Context,Resolution,Correlated With"
        ]
        for item in sorted(self._items.values(), key=lambda x: (x.document_title, x.page_number)):
            context_clean = item.context.replace('"', '""').replace('\n', ' ')[:100]
            corr = "; ".join(item.correlated_items[:3])
            lines.append(
                f'"{item.item_id}","{item.item_type}","{item.status}",'
                f'"{item.document_title}",{item.page_number},'
                f'"{item.section_heading or ""}","{item.owner or ""}",'
                f'"{item.target_date or ""}",{item.in_shall_statement},'
                f'"{context_clean}","{item.resolution_value or ""}","{corr}"'
            )
        return "\n".join(lines)

    def export_markdown(self) -> str:
        """Export as markdown table for review packages."""
        stats = self.get_stats()
        lines = [
            "# TBD/TBR Dashboard Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Documents:** {stats.documents_count}",
            f"**Total Items:** {stats.total_items}",
            f"**Open:** {stats.open_count} | **Assigned:** {stats.assigned_count} "
            f"| **Resolved:** {stats.resolved_count} | **Verified:** {stats.verified_count}",
            f"**In 'shall' statements:** {stats.in_shall_statements} (contractually blocking)",
            f"**Cross-document correlations:** {stats.correlated_pairs}",
            f"**Conflicts:** {stats.conflicts}",
            "",
            "## Open Items",
            "",
            "| ID | Type | Document | Page | Owner | In Shall | Context |",
            "|---|---|---|---|---|---|---|",
        ]

        for item in sorted(self.filter_items(status="open"),
                           key=lambda x: (not x.in_shall_statement, x.document_title)):
            context_short = item.context[:60].replace("|", "\\|")
            shall_mark = "⚠️" if item.in_shall_statement else ""
            lines.append(
                f"| {item.item_id} | {item.item_type} | "
                f"{item.document_title[:25]} | {item.page_number} | "
                f"{item.owner or '—'} | {shall_mark} | {context_short} |"
            )

        if self._correlations:
            lines.extend([
                "",
                "## Cross-Document Correlations",
                "",
                "| Item A | Item B | Confidence | Conflict |",
                "|---|---|---|---|",
            ])
            for corr in self._correlations:
                conflict_mark = "⚠️ YES" if corr.conflict else "No"
                lines.append(
                    f"| {corr.item_a_id} | {corr.item_b_id} | "
                    f"{corr.confidence} | {conflict_mark} |"
                )

        return "\n".join(lines)

    def summary(self) -> str:
        """Human-readable summary for CLI."""
        stats = self.get_stats()
        lines = [
            "TBD Dashboard Summary",
            "=" * 40,
            f"Documents scanned: {stats.documents_count}",
            f"Total TBD/TBR items: {stats.total_items}",
            "",
            "Status breakdown:",
            f"  Open:     {stats.open_count}",
            f"  Assigned: {stats.assigned_count}",
            f"  Resolved: {stats.resolved_count}",
            f"  Verified: {stats.verified_count}",
            "",
            f"Type breakdown:",
            f"  TBD: {stats.tbd_count}",
            f"  TBR: {stats.tbr_count}",
            "",
            f"⚠️  In 'shall' statements (contractually blocking): "
            f"{stats.in_shall_statements}",
            f"Cross-document correlations: {stats.correlated_pairs}",
            f"Conflicts: {stats.conflicts}",
        ]

        # Show top open items
        open_items = self.filter_items(status="open")
        if open_items:
            # Prioritize: shall-statement items first
            open_items.sort(key=lambda x: (not x.in_shall_statement, x.document_title))
            lines.extend(["", "Top open items:"])
            for item in open_items[:10]:
                shall = " [SHALL]" if item.in_shall_statement else ""
                lines.append(
                    f"  • {item.item_id} ({item.item_type}){shall} — "
                    f"{item.document_title}, p{item.page_number}"
                )
                if item.context:
                    ctx = item.context[:70].replace("\n", " ")
                    lines.append(f"    \"{ctx}\"")

        return "\n".join(lines)
