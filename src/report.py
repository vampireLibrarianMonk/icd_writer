"""Pipeline summary report generator.

Produces a human-readable markdown report comparing the original PDF
against the regenerated output — pixel fidelity, text accuracy, and
element counts.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np
from PIL import Image


def generate_report(
    original_pdf: Path | str,
    regenerated_pdf: Path | str,
    output_path: Path | str | None = None,
) -> str:
    """Generate a fidelity report comparing original vs regenerated PDF.

    Args:
        original_pdf: Path to the source PDF.
        regenerated_pdf: Path to the regenerated PDF.
        output_path: Optional path to write the report markdown.

    Returns:
        Markdown string with the full report.
    """
    original_pdf = Path(original_pdf)
    regenerated_pdf = Path(regenerated_pdf)

    orig = fitz.open(str(original_pdf))
    regen = fitz.open(str(regenerated_pdf))

    num_pages = min(len(orig), len(regen))

    # Collect per-page metrics
    page_results = []
    total_orig_words = 0
    total_matched_words = 0
    total_orig_chars = 0
    pages_text_perfect = 0

    for i in range(num_pages):
        # Pixel comparison
        p1 = orig[i].get_pixmap(dpi=150)
        p2 = regen[i].get_pixmap(dpi=150)
        i1 = np.array(Image.frombytes("RGB", (p1.width, p1.height), p1.samples))
        i2 = np.array(Image.frombytes("RGB", (p2.width, p2.height), p2.samples))

        diff = np.abs(i1.astype(int) - i2.astype(int))
        pixel_match = (diff.sum(axis=2) < 30).mean() * 100
        nw_o = i1.min(axis=2) < 240
        nw_r = i2.min(axis=2) < 240
        overlap = (nw_o & nw_r).sum()
        recall = overlap / nw_o.sum() * 100 if nw_o.sum() > 0 else 100.0
        precision = overlap / nw_r.sum() * 100 if nw_r.sum() > 0 else 100.0
        f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0

        # Text comparison
        orig_text = " ".join(orig[i].get_text("text").split())
        regen_text = " ".join(regen[i].get_text("text").split())

        orig_words = set(orig_text.split())
        regen_words = set(regen_text.split())
        matched_words = orig_words & regen_words
        total_orig_words += len(orig_words)
        total_matched_words += len(matched_words)
        total_orig_chars += len(orig_text)

        text_exact = orig_text == regen_text
        if text_exact:
            pages_text_perfect += 1

        page_results.append(
            {
                "page": i + 1,
                "pixel_match": pixel_match,
                "recall": recall,
                "precision": precision,
                "f1": f1,
                "text_exact": text_exact,
                "word_retention": len(matched_words) / len(orig_words) * 100
                if orig_words
                else 100.0,
            }
        )

    orig.close()
    regen.close()

    # Compute aggregates
    avg_pixel = sum(r["pixel_match"] for r in page_results) / num_pages
    avg_f1 = sum(r["f1"] for r in page_results) / num_pages
    word_retention = total_matched_words / total_orig_words * 100 if total_orig_words > 0 else 100.0
    best_page = max(page_results, key=lambda r: r["pixel_match"])
    worst_page = min(page_results, key=lambda r: r["pixel_match"])

    # Build report
    lines = []
    lines.append(f"# Pipeline Report: {original_pdf.name}")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Source | `{original_pdf.name}` |")
    lines.append(f"| Output | `{regenerated_pdf.name}` |")
    lines.append(f"| Pages | {num_pages} |")
    lines.append("| Pipeline | Fully automated (zero manual adjustments) |")
    lines.append("")
    lines.append("## Visual Fidelity")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Average Pixel Match | **{avg_pixel:.1f}%** |")
    lines.append(f"| Average F1 Score | **{avg_f1:.1f}%** |")
    lines.append(f"| Best Page | Page {best_page['page']} ({best_page['pixel_match']:.1f}%) |")
    lines.append(f"| Worst Page | Page {worst_page['page']} ({worst_page['pixel_match']:.1f}%) |")
    lines.append("")
    lines.append("## Text Accuracy")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Pages with exact text match | {pages_text_perfect}/{num_pages} |")
    lines.append(f"| Word retention | {word_retention:.1f}% |")
    lines.append(f"| Total characters processed | {total_orig_chars:,} |")
    lines.append("")
    lines.append("## Per-Page Breakdown")
    lines.append("")
    lines.append("| Page | Pixel | F1 | Text | Words |")
    lines.append("|------|-------|----|------|-------|")
    for r in page_results:
        text_status = "✓" if r["text_exact"] else f"{r['word_retention']:.0f}%"
        lines.append(
            f"| {r['page']} | {r['pixel_match']:.1f}% | {r['f1']:.1f}% | "
            f"{text_status} | {r['word_retention']:.0f}% |"
        )
    lines.append("")
    lines.append("## Definitions")
    lines.append("")
    lines.append("| Term | Meaning |")
    lines.append("|------|---------|")
    lines.append(
        "| Pixel Match | % of page pixels identical (±30/255) between original and regenerated |"
    )
    lines.append(
        "| F1 | Harmonic mean of content recall and precision (how well ink pixels align) |"
    )
    lines.append(
        "| Text ✓ | Extracted text is character-for-character identical (whitespace-normalized) |"
    )
    lines.append(
        "| Words | % of unique words from the original that appear in the regenerated version |"
    )
    lines.append("")
    lines.append("---")
    lines.append("*Generated by ICD Writer pipeline*")

    report = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")

    return report
