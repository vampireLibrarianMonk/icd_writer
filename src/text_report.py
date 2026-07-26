"""Detailed text accuracy report generator.

Produces a per-page breakdown of text differences between original and
regenerated PDFs — exact matches, missing words, and extra words.

Usage:
    python3 -m src.text_report icds/20150010976.pdf output/20150010976_regenerated.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz


def generate_text_report(
    original_pdf: Path | str,
    regenerated_pdf: Path | str,
    output_path: Path | str | None = None,
) -> str:
    """Generate a detailed text accuracy report.

    Compares extracted text from original vs regenerated PDF page by page,
    reporting exact matches, missing words, extra words, and whitespace changes.
    """
    original_pdf = Path(original_pdf)
    regenerated_pdf = Path(regenerated_pdf)

    orig = fitz.open(str(original_pdf))
    regen = fitz.open(str(regenerated_pdf))

    num_pages = min(len(orig), len(regen))

    lines = []
    lines.append(f"# Text Accuracy Report: {original_pdf.name}")
    lines.append("")
    lines.append(f"Comparing text content between original and regenerated PDF.")
    lines.append(f"Pages compared: {num_pages}")
    lines.append("")

    total_pages_exact = 0
    total_orig_words = 0
    total_missing_words = 0
    total_extra_words = 0
    pages_with_issues = []

    lines.append("## Per-Page Results")
    lines.append("")
    lines.append("| Page | Status | Words Orig | Missing | Extra | Notes |")
    lines.append("|------|--------|-----------|---------|-------|-------|")

    for i in range(num_pages):
        orig_text = " ".join(orig[i].get_text("text").split())
        regen_text = " ".join(regen[i].get_text("text").split())

        orig_words = orig_text.split()
        regen_words = regen_text.split()

        orig_word_set = set(orig_words)
        regen_word_set = set(regen_words)

        missing = orig_word_set - regen_word_set
        extra = regen_word_set - orig_word_set

        total_orig_words += len(orig_word_set)
        total_missing_words += len(missing)
        total_extra_words += len(extra)

        is_exact = orig_text == regen_text
        if is_exact:
            total_pages_exact += 1
            status = "✓ Exact"
            notes = ""
        elif not missing and not extra:
            status = "~ Whitespace"
            notes = "Same words, different spacing"
            pages_with_issues.append((i + 1, "whitespace", missing, extra, orig_text, regen_text))
        else:
            status = "✗ Differs"
            notes = f"Missing: {list(missing)[:3]}" if missing else ""
            if extra:
                notes += f" Extra: {list(extra)[:3]}" if notes else f"Extra: {list(extra)[:3]}"
            pages_with_issues.append((i + 1, "content", missing, extra, orig_text, regen_text))

        lines.append(
            f"| {i+1} | {status} | {len(orig_word_set)} | "
            f"{len(missing)} | {len(extra)} | {notes} |"
        )

    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Pages with exact text match | {total_pages_exact}/{num_pages} |")
    lines.append(
        f"| Word retention | "
        f"{(total_orig_words - total_missing_words) / total_orig_words * 100:.1f}% |"
    )
    lines.append(f"| Total unique words in original | {total_orig_words:,} |")
    lines.append(f"| Total missing words | {total_missing_words} |")
    lines.append(f"| Total extra words | {total_extra_words} |")

    # Detailed section for pages with issues
    if pages_with_issues:
        lines.append("")
        lines.append("## Detailed Differences")
        lines.append("")
        lines.append(
            "Below are the specific text differences found. "
            "These help identify what content may need attention."
        )

        for page_num, issue_type, missing, extra, orig_text, regen_text in pages_with_issues:
            lines.append("")
            lines.append(f"### Page {page_num}")
            lines.append("")

            if issue_type == "whitespace":
                # Find where whitespace differs
                lines.append("**Type:** Whitespace difference (same words, different spacing)")
                lines.append("")
                # Find first difference
                for j, (a, b) in enumerate(zip(orig_text, regen_text)):
                    if a != b:
                        context_start = max(0, j - 30)
                        context_end = min(len(orig_text), j + 30)
                        lines.append("First difference at character position " f"{j}:")
                        lines.append("")
                        lines.append(
                            f"- Original: `...{orig_text[context_start:context_end]}...`"
                        )
                        lines.append(
                            f"- Regenerated: `...{regen_text[context_start:context_end]}...`"
                        )
                        break
            else:
                if missing:
                    lines.append(f"**Missing words** ({len(missing)}):")
                    lines.append("")
                    for word in sorted(missing)[:20]:
                        lines.append(f"- `{word}`")

                if extra:
                    lines.append("")
                    lines.append(f"**Extra words** ({len(extra)}):")
                    lines.append("")
                    for word in sorted(extra)[:20]:
                        lines.append(f"- `{word}`")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## How to Read This Report")
    lines.append("")
    lines.append("- **✓ Exact**: The text on this page is character-for-character identical")
    lines.append(
        "- **~ Whitespace**: All words are present but spacing differs "
        "(e.g., double space → single space)"
    )
    lines.append(
        "- **✗ Differs**: Some words are missing or extra "
        "(may be from z-order hiding or image-embedded text)"
    )
    lines.append(
        "- **Missing words**: Words in the original PDF that don't appear in the regenerated version"
    )
    lines.append(
        "- **Extra words**: Words in the regenerated version that don't appear in the original"
    )

    orig.close()
    regen.close()

    report = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")

    return report


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 -m src.text_report <original.pdf> <regenerated.pdf> [output.md]")
        sys.exit(1)

    orig_path = Path(sys.argv[1])
    regen_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    if out_path is None:
        out_path = Path("output") / f"{orig_path.stem}_text_report.md"

    report = generate_text_report(orig_path, regen_path, out_path)
    print(f"Report written to: {out_path}")

    # Print summary
    for line in report.split("\n"):
        if line.startswith("| Pages with") or line.startswith("| Word retention"):
            print(f"  {line}")
