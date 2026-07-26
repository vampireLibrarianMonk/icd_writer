"""CLI entry point for the ICD Document Editor pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ICD Document Editor - PDF to structured ICD pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest and process a PDF file")
    ingest_parser.add_argument("pdf_path", type=str, help="Path to the PDF file")
    ingest_parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory for extracted data (default: ./output)",
    )
    ingest_parser.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (default: yaml)",
    )

    # Render command
    render_parser = subparsers.add_parser("render", help="Render pages back to PDF")
    render_parser.add_argument("pdf_path", type=str, help="Path to the source PDF file")
    render_parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Page range to render, e.g. '1-3' or '1,2,5' (default: all pages)",
    )
    render_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output PDF path (default: output/<stem>_regenerated.pdf)",
    )
    render_parser.add_argument(
        "--report",
        action="store_true",
        help="Generate a fidelity report after rendering",
    )

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate fidelity report for a rendered PDF")
    report_parser.add_argument("pdf_path", type=str, help="Path to the original PDF")
    report_parser.add_argument("regen_path", type=str, help="Path to the regenerated PDF")
    report_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output report path (default: output/<stem>_report.md)",
    )

    # Info command
    info_parser = subparsers.add_parser("info", help="Show PDF metadata without full extraction")
    info_parser.add_argument("pdf_path", type=str, help="Path to the PDF file")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "info":
        _cmd_info(Path(args.pdf_path))
    elif args.command == "ingest":
        _cmd_ingest(Path(args.pdf_path), Path(args.output_dir), args.format)
    elif args.command == "render":
        _cmd_render(Path(args.pdf_path), args.pages, args.output, args.report)
    elif args.command == "report":
        _cmd_report(Path(args.pdf_path), Path(args.regen_path), args.output)


def _cmd_info(pdf_path: Path) -> None:
    """Print PDF metadata."""
    from src.ingestion.pdf_reader import ingest_pdf

    result = ingest_pdf(pdf_path)
    m = result.metadata
    print(f"File:       {m.filename}")
    print(f"SHA-256:    {m.sha256}")
    print(f"Pages:      {m.page_count}")
    print(f"Size:       {m.file_size_bytes:,} bytes")
    if m.title:
        print(f"Title:      {m.title}")
    if m.author:
        print(f"Author:     {m.author}")
    if m.creator:
        print(f"Creator:    {m.creator}")
    if m.creation_date:
        print(f"Created:    {m.creation_date}")

    print("\nPage dimensions (pt):")
    for i, (w, h) in enumerate(result.page_dimensions, 1):
        print(f"  Page {i:3d}: {w:.1f} x {h:.1f}")


def _cmd_ingest(pdf_path: Path, output_dir: Path, output_format: str) -> None:
    """Run full extraction pipeline and save results."""
    from src.pipeline import process_pdf
    from src.serialization import to_json, to_yaml

    print(f"Processing: {pdf_path}")
    document_ir = process_pdf(pdf_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem

    if output_format == "yaml":
        out_path = output_dir / f"{stem}_document_ir.yaml"
        to_yaml(document_ir, out_path)
    else:
        out_path = output_dir / f"{stem}_document_ir.json"
        to_json(document_ir, out_path)

    print(f"Pages processed: {document_ir.page_count}")
    total_blocks = sum(len(p.text_blocks) for p in document_ir.pages)
    print(f"Text blocks extracted: {total_blocks}")
    print(f"Output: {out_path}")


def _parse_page_range(page_spec: str | None, total_pages: int) -> list[int]:
    """Parse a page specification like '1-3' or '1,2,5' into a list of page numbers."""
    if page_spec is None:
        return list(range(1, total_pages + 1))

    pages: list[int] = []
    for part in page_spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))

    return [p for p in pages if 1 <= p <= total_pages]


def _cmd_render(pdf_path: Path, pages_spec: str | None, output: str | None, report: bool = False) -> None:
    """Render pages from a PDF back to a new PDF via the extraction pipeline."""
    from src.rendering.page_renderer import render_pages_to_pdf
    import fitz

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()

    page_numbers = _parse_page_range(pages_spec, total_pages)

    if output:
        output_path = Path(output)
    else:
        output_path = Path("output") / f"{pdf_path.stem}_regenerated.pdf"

    print(f"Source: {pdf_path} ({total_pages} pages)")
    print(f"Rendering pages: {page_numbers}")

    result = render_pages_to_pdf(pdf_path, page_numbers, output_path)
    print(f"Output: {result} ({len(page_numbers)} pages)")

    if report:
        _cmd_report(pdf_path, output_path, None)


def _cmd_report(pdf_path: Path, regen_path: Path, output: str | None) -> None:
    """Generate a fidelity report comparing original vs regenerated PDF."""
    from src.report import generate_report

    if output:
        report_path = Path(output)
    else:
        report_path = Path("output") / f"{pdf_path.stem}_report.md"

    print(f"Generating report...")
    report = generate_report(pdf_path, regen_path, report_path)
    print(f"Report: {report_path}")

    # Print summary to console
    for line in report.split("\n"):
        if line.startswith("| Average") or line.startswith("| Pages with") or line.startswith("| Word"):
            print(f"  {line}")


if __name__ == "__main__":
    main()
