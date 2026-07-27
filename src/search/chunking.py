"""Document chunking strategies.

Converts Document IR into indexable chunks. Each strategy produces
the same ChunkResult format so they're interchangeable for benchmarking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..search.config import ChunkConfig, ChunkStrategy


@dataclass
class Chunk:
    """A single indexable text chunk with provenance metadata."""

    chunk_id: str  # {doc_hash}_{page}_{chunk_idx}
    text: str
    # Provenance
    document_hash: str
    document_title: str
    page_number: int
    section_heading: str | None = None
    section_number: str | None = None
    # Position in source
    y_start: float | None = None
    y_end: float | None = None
    # Type hints for retrieval filtering
    content_type: str = "paragraph"  # paragraph, table, heading, requirement, tbd
    # Extracted metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        """Rough token count (words × 1.3)."""
        return int(len(self.text.split()) * 1.3)


@dataclass
class ChunkResult:
    """Output of a chunking operation on a single document."""

    document_hash: str
    document_title: str
    chunks: list[Chunk]
    config: ChunkConfig
    total_tokens_estimate: int = 0

    def __post_init__(self) -> None:
        self.total_tokens_estimate = sum(c.token_estimate for c in self.chunks)


def chunk_document(pages: list[dict[str, Any]], doc_hash: str, doc_title: str,
                   config: ChunkConfig) -> ChunkResult:
    """Chunk a document's page data according to config.

    Args:
        pages: List of page dicts from Document IR. Supports two formats:
               - Structured: separate 'headings', 'text_blocks', 'tables' keys
               - Flat (actual IR): 'text_blocks' with 'block_type' field and 'text_verbatim'
        doc_hash: SHA-256 hash of source PDF
        doc_title: Document title for metadata
        config: Chunking configuration

    Returns:
        ChunkResult with all chunks and metadata
    """
    # Normalize pages to the structured format expected by strategies
    normalized = _normalize_pages(pages)

    strategy_fn = _STRATEGIES.get(config.strategy)
    if not strategy_fn:
        raise ValueError(f"Unknown chunking strategy: {config.strategy}")
    return strategy_fn(normalized, doc_hash, doc_title, config)


def _normalize_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Document IR pages into the format strategies expect.

    Handles both:
    - Test format: separate 'headings' and 'text_blocks' with 'text' and 'y'
    - Real IR: unified 'text_blocks' with 'block_type', 'text_verbatim', 'bbox'
    """
    normalized = []
    for page in pages:
        # If already has separate headings/text_blocks with 'text' key, pass through
        if page.get("headings") or (
            page.get("text_blocks")
            and page["text_blocks"]
            and "text" in page["text_blocks"][0]
            and "text_verbatim" not in page["text_blocks"][0]
        ):
            normalized.append(page)
            continue

        # Real IR format: split by block_type
        headings = []
        text_blocks = []
        tables = page.get("tables", [])

        for tb in page.get("text_blocks", []):
            text = tb.get("text_verbatim", tb.get("text", ""))
            if not text or not text.strip():
                continue
            bbox = tb.get("bbox", {})
            y = bbox.get("y0", 0) if isinstance(bbox, dict) else 0
            block_type = tb.get("block_type", "paragraph")

            entry = {
                "text": text.strip(),
                "y": y,
            }

            if block_type == "heading":
                # Try to extract section number from heading text
                section_num = _extract_section_number(text.strip())
                if section_num:
                    entry["section_number"] = section_num
                headings.append(entry)
            else:
                text_blocks.append(entry)

        # Normalize tables
        norm_tables = []
        for tbl in tables:
            t_bbox = tbl.get("bbox", {})
            t_y = t_bbox.get("y0", 0) if isinstance(t_bbox, dict) else 0
            norm_tables.append({
                "y": t_y,
                "rows": tbl.get("rows", []),
                "cells": tbl.get("cells", []),
            })

        normalized.append({
            "page_number": page.get("page_number", 0),
            "headings": headings,
            "text_blocks": text_blocks,
            "tables": norm_tables,
        })

    return normalized


def _extract_section_number(text: str) -> str | None:
    """Extract section number like '1.0', '3.2.1' from heading text."""
    import re
    match = re.match(r'^(\d+(?:\.\d+)*)\s', text)
    if match:
        return match.group(1)
    return None


def _chunk_paragraph(pages: list[dict[str, Any]], doc_hash: str,
                     doc_title: str, config: ChunkConfig) -> ChunkResult:
    """Chunk by natural paragraph boundaries from the Document IR."""
    chunks: list[Chunk] = []
    chunk_idx = 0

    for page in pages:
        page_num = page.get("page_number", 0)
        current_heading = None
        current_section = None

        # Process headings and text blocks in document order (by y position)
        elements = []
        for h in page.get("headings", []):
            elements.append(("heading", h))
        for tb in page.get("text_blocks", []):
            elements.append(("text", tb))
        for tbl in page.get("tables", []):
            elements.append(("table", tbl))

        # Sort by y position
        elements.sort(key=lambda e: e[1].get("y", e[1].get("y0", 0)))

        for elem_type, elem in elements:
            if elem_type == "heading":
                current_heading = elem.get("text", "")
                current_section = elem.get("section_number")
                # Headings themselves are chunks (short, but valuable for search)
                chunks.append(Chunk(
                    chunk_id=f"{doc_hash}_{page_num}_{chunk_idx}",
                    text=current_heading,
                    document_hash=doc_hash,
                    document_title=doc_title,
                    page_number=page_num,
                    section_heading=current_heading,
                    section_number=current_section,
                    y_start=elem.get("y", elem.get("y0")),
                    content_type="heading",
                ))
                chunk_idx += 1

            elif elem_type == "text":
                text = elem.get("text", "")
                if not text.strip():
                    continue
                # If text exceeds max_tokens, split at sentence boundaries
                if _estimate_tokens(text) > config.max_tokens:
                    for sub_text in _split_at_sentences(text, config.max_tokens):
                        chunks.append(Chunk(
                            chunk_id=f"{doc_hash}_{page_num}_{chunk_idx}",
                            text=sub_text,
                            document_hash=doc_hash,
                            document_title=doc_title,
                            page_number=page_num,
                            section_heading=current_heading,
                            section_number=current_section,
                            y_start=elem.get("y", elem.get("y0")),
                            content_type="paragraph",
                        ))
                        chunk_idx += 1
                else:
                    chunks.append(Chunk(
                        chunk_id=f"{doc_hash}_{page_num}_{chunk_idx}",
                        text=text,
                        document_hash=doc_hash,
                        document_title=doc_title,
                        page_number=page_num,
                        section_heading=current_heading,
                        section_number=current_section,
                        y_start=elem.get("y", elem.get("y0")),
                        content_type="paragraph",
                    ))
                    chunk_idx += 1

            elif elem_type == "table":
                # Serialize table content as text for indexing
                table_text = _serialize_table(elem)
                if table_text.strip():
                    chunks.append(Chunk(
                        chunk_id=f"{doc_hash}_{page_num}_{chunk_idx}",
                        text=table_text,
                        document_hash=doc_hash,
                        document_title=doc_title,
                        page_number=page_num,
                        section_heading=current_heading,
                        section_number=current_section,
                        y_start=elem.get("y", elem.get("y0")),
                        content_type="table",
                    ))
                    chunk_idx += 1

    return ChunkResult(
        document_hash=doc_hash,
        document_title=doc_title,
        chunks=chunks,
        config=config,
    )


def _chunk_section(pages: list[dict[str, Any]], doc_hash: str,
                   doc_title: str, config: ChunkConfig) -> ChunkResult:
    """Chunk by section — accumulate text between headings."""
    chunks: list[Chunk] = []
    chunk_idx = 0

    current_heading = None
    current_section = None
    current_text_parts: list[str] = []
    current_page = 0
    current_y = 0.0

    def flush_section() -> None:
        nonlocal chunk_idx
        if not current_text_parts:
            return
        full_text = "\n".join(current_text_parts)
        prefix = ""
        if config.include_heading and current_heading:
            prefix = f"{current_section + ' ' if current_section else ''}{current_heading}\n\n"
        text = prefix + full_text

        # Split if over max tokens
        if _estimate_tokens(text) > config.max_tokens:
            for sub_text in _split_at_sentences(text, config.max_tokens):
                chunks.append(Chunk(
                    chunk_id=f"{doc_hash}_{current_page}_{chunk_idx}",
                    text=sub_text,
                    document_hash=doc_hash,
                    document_title=doc_title,
                    page_number=current_page,
                    section_heading=current_heading,
                    section_number=current_section,
                    y_start=current_y,
                    content_type="section",
                ))
                chunk_idx += 1
        else:
            chunks.append(Chunk(
                chunk_id=f"{doc_hash}_{current_page}_{chunk_idx}",
                text=text,
                document_hash=doc_hash,
                document_title=doc_title,
                page_number=current_page,
                section_heading=current_heading,
                section_number=current_section,
                y_start=current_y,
                content_type="section",
            ))
            chunk_idx += 1

    for page in pages:
        page_num = page.get("page_number", 0)
        elements = []
        for h in page.get("headings", []):
            elements.append(("heading", h))
        for tb in page.get("text_blocks", []):
            elements.append(("text", tb))
        for tbl in page.get("tables", []):
            elements.append(("table", tbl))
        elements.sort(key=lambda e: e[1].get("y", e[1].get("y0", 0)))

        for elem_type, elem in elements:
            if elem_type == "heading":
                # Flush previous section
                flush_section()
                current_text_parts = []
                current_heading = elem.get("text", "")
                current_section = elem.get("section_number")
                current_page = page_num
                current_y = elem.get("y", elem.get("y0", 0))
            elif elem_type == "text":
                text = elem.get("text", "")
                if text.strip():
                    current_text_parts.append(text)
                    if not current_heading:
                        current_page = page_num
            elif elem_type == "table":
                table_text = _serialize_table(elem)
                if table_text.strip():
                    current_text_parts.append(table_text)

    # Flush last section
    flush_section()

    return ChunkResult(
        document_hash=doc_hash,
        document_title=doc_title,
        chunks=chunks,
        config=config,
    )


def _chunk_sliding_window(pages: list[dict[str, Any]], doc_hash: str,
                          doc_title: str, config: ChunkConfig) -> ChunkResult:
    """Chunk with sliding window over concatenated page text."""
    chunks: list[Chunk] = []
    chunk_idx = 0

    # Build (word, page_num) pairs
    word_pages: list[tuple[str, int]] = []
    for page in pages:
        page_num = page.get("page_number", 0)
        elements = []
        for tb in page.get("text_blocks", []):
            elements.append(tb)
        for h in page.get("headings", []):
            elements.append(h)
        elements.sort(key=lambda e: e.get("y", e.get("y0", 0)))
        for elem in elements:
            text = elem.get("text", "")
            for word in text.split():
                word_pages.append((word, page_num))

    if not word_pages:
        return ChunkResult(document_hash=doc_hash, document_title=doc_title,
                           chunks=chunks, config=config)

    # Convert max_tokens to approximate word count
    max_words = int(config.max_tokens / 1.3)
    overlap_words = int(config.overlap_tokens / 1.3)
    step = max(1, max_words - overlap_words)

    i = 0
    while i < len(word_pages):
        window = word_pages[i:i + max_words]
        text = " ".join(w for w, _ in window)
        page_num = window[0][1]  # Page of first word

        chunks.append(Chunk(
            chunk_id=f"{doc_hash}_{page_num}_{chunk_idx}",
            text=text,
            document_hash=doc_hash,
            document_title=doc_title,
            page_number=page_num,
            content_type="window",
        ))
        chunk_idx += 1
        i += step

    return ChunkResult(
        document_hash=doc_hash,
        document_title=doc_title,
        chunks=chunks,
        config=config,
    )


def _chunk_fixed_words(pages: list[dict[str, Any]], doc_hash: str,
                       doc_title: str, config: ChunkConfig) -> ChunkResult:
    """Chunk by fixed word count (no overlap)."""
    # Use sliding window with zero overlap
    no_overlap_config = ChunkConfig(
        strategy=ChunkStrategy.SLIDING_WINDOW,
        max_tokens=config.max_tokens,
        overlap_tokens=0,
    )
    result = _chunk_sliding_window(pages, doc_hash, doc_title, no_overlap_config)
    result.config = config
    return result


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: words × 1.3."""
    return int(len(text.split()) * 1.3)


def _split_at_sentences(text: str, max_tokens: int) -> list[str]:
    """Split text at sentence boundaries respecting max_tokens."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    parts: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = _estimate_tokens(sentence)
        if current_tokens + sent_tokens > max_tokens and current:
            parts.append(" ".join(current))
            current = [sentence]
            current_tokens = sent_tokens
        else:
            current.append(sentence)
            current_tokens += sent_tokens

    if current:
        parts.append(" ".join(current))
    return parts


def _serialize_table(table: dict[str, Any]) -> str:
    """Convert a table dict into searchable text."""
    rows = table.get("rows", [])
    if not rows:
        cells = table.get("cells", [])
        if cells:
            # Flat cell list — just join text
            return " | ".join(c.get("text", "") for c in cells if c.get("text"))
        return ""

    lines: list[str] = []
    for row in rows:
        if isinstance(row, list):
            lines.append(" | ".join(str(cell) for cell in row))
        elif isinstance(row, dict):
            cells = row.get("cells", [])
            lines.append(" | ".join(c.get("text", "") for c in cells))
    return "\n".join(lines)


_STRATEGIES = {
    ChunkStrategy.FIXED_WORDS: _chunk_fixed_words,
    ChunkStrategy.PARAGRAPH: _chunk_paragraph,
    ChunkStrategy.SECTION: _chunk_section,
    ChunkStrategy.SLIDING_WINDOW: _chunk_sliding_window,
    # SEMANTIC strategy requires Bedrock — placeholder for eval harness
}
