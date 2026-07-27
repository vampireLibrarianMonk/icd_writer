"""Page content analysis — labels each element by type.

Provides structured information about what's on each page so the UI
can inform users what they're editing (header, footer, table, TOC,
title, paragraph, list, etc.)
"""

from __future__ import annotations

from pathlib import Path

import fitz


def analyze_page_content(pdf_path: Path | str, page_number: int) -> dict:
    """Analyze a page and return labeled content regions.

    Returns a dict with categorized elements the user can edit.
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]
    page_width = page.rect.width
    page_height = page.rect.height

    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    drawings_count = len(page.get_drawings())

    headers = []
    footers = []
    body_spans = []

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                text = "".join(c["c"] for c in chars).strip()
                if not text:
                    continue

                y = span["bbox"][1]
                x = span["bbox"][0]
                entry = {
                    "text": text,
                    "x": x,
                    "y": y,
                    "x1": span["bbox"][2],
                    "y1": span["bbox"][3],
                    "font": span["font"],
                    "size": span["size"],
                }

                if y < 60:
                    # Determine left/center/right
                    if x < page_width * 0.33:
                        entry["alignment"] = "left"
                    elif x > page_width * 0.66:
                        entry["alignment"] = "right"
                    else:
                        entry["alignment"] = "center"
                    headers.append(entry)
                elif y > page_height - 72:
                    if x < page_width * 0.33:
                        entry["alignment"] = "left"
                    elif x > page_width * 0.66:
                        entry["alignment"] = "right"
                    else:
                        entry["alignment"] = "center"
                    footers.append(entry)
                else:
                    body_spans.append(entry)

    # Determine body content type
    has_toc = any("..." in s["text"] for s in body_spans)
    has_table = drawings_count > 20
    has_bullets = any(
        s["text"].startswith("•") or s["text"].startswith("- ")
        for s in body_spans
    )

    # Classify body elements
    titles = [s for s in body_spans if s["size"] > 13]
    paragraphs = [
        s for s in body_spans
        if s["size"] <= 13 and not s["text"].startswith("•")
    ]
    list_items = [
        s for s in body_spans
        if s["text"].startswith("•") or s["text"].startswith("- ")
    ]

    # Determine page type
    if has_toc:
        page_type = "table_of_contents"
    elif has_table:
        page_type = "table"
    elif titles and len(paragraphs) < 15 and not headers:
        # Title/cover page: has large text, few paragraphs, no header
        page_type = "title_page"
    elif has_bullets:
        page_type = "list"
    else:
        page_type = "text"

    doc.close()

    return {
        "page_number": page_number,
        "page_type": page_type,
        "header": {
            "left": next((h["text"] for h in headers if h["alignment"] == "left"), None),
            "center": next(
                (h["text"] for h in headers if h["alignment"] == "center"), None
            ),
            "right": next(
                (h["text"] for h in headers if h["alignment"] == "right"), None
            ),
        },
        "footer": {
            "left": next((f["text"] for f in footers if f["alignment"] == "left"), None),
            "center": next(
                (f["text"] for f in footers if f["alignment"] == "center"), None
            ),
            "right": next(
                (f["text"] for f in footers if f["alignment"] == "right"), None
            ),
        },
        "body": {
            "titles": [{"text": t["text"], "size": t["size"]} for t in titles],
            "paragraphs": len(paragraphs),
            "list_items": [li["text"] for li in list_items],
            "has_table": has_table,
            "table_grid_elements": drawings_count if has_table else 0,
            "table_y_min": min((s["y"] for s in body_spans), default=0) if has_table else 0,
            "table_y_max": max((s["y"] for s in body_spans if s["y"] < 500), default=0) + 20 if has_table else 0,
            "has_toc": has_toc,
        },
    }
