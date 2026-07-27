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
    report_parser = subparsers.add_parser(
        "report", help="Generate fidelity report for a rendered PDF"
    )
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

    # OCR ingest command
    ocr_parser = subparsers.add_parser(
        "ocr-ingest", help="Ingest a scanned/flattened PDF using OCR models"
    )
    ocr_parser.add_argument("pdf_path", type=str, help="Path to the scanned PDF file")
    ocr_parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory (default: ./output)",
    )
    ocr_parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="AWS region for API calls (default: us-east-1)",
    )
    ocr_parser.add_argument(
        "--no-rekognition",
        action="store_true",
        help="Skip Rekognition (diagram label detection)",
    )
    ocr_parser.add_argument(
        "--no-classify",
        action="store_true",
        help="Skip Bedrock page classification",
    )
    ocr_parser.add_argument(
        "--no-disambiguate",
        action="store_true",
        help="Skip Bedrock conflict resolution",
    )

    # Search commands
    search_index_parser = subparsers.add_parser(
        "search-index", help="Index a Document IR file into search indices"
    )
    search_index_parser.add_argument(
        "ir_path", type=str, help="Path to Document IR YAML file"
    )
    search_index_parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region"
    )

    search_parser = subparsers.add_parser(
        "search", help="Search across indexed ICD documents"
    )
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument(
        "-k", type=int, default=10, help="Number of results (default: 10)"
    )
    search_parser.add_argument(
        "--mode",
        choices=["keyword", "vector", "hybrid", "rrf"],
        default="rrf",
        help="Retrieval mode (default: rrf)",
    )
    search_parser.add_argument(
        "--rag", action="store_true",
        help="Use RAG: generate a synthesized answer with citations instead of raw results",
    )
    search_parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region"
    )

    search_eval_parser = subparsers.add_parser(
        "search-eval",
        help="Run search evaluation benchmark across all model/strategy combinations",
    )
    search_eval_parser.add_argument(
        "-k", type=int, default=10, help="Top-K for recall measurement"
    )
    search_eval_parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region"
    )

    search_models_parser = subparsers.add_parser(
        "search-models",
        help="Check for new/deprecated embedding models on Bedrock",
    )
    search_models_parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region"
    )

    search_status_parser = subparsers.add_parser(
        "search-status", help="Show search pipeline status"
    )
    search_status_parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region"
    )

    # Benchmark command
    benchmark_parser = subparsers.add_parser(
        "search-benchmark",
        help="Benchmark newly-discovered embedding models (staged evaluation)",
    )
    benchmark_parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region"
    )
    benchmark_parser.add_argument(
        "--budget-cap",
        type=float,
        default=10.0,
        help="Maximum cost in USD before stopping (default: $10)",
    )
    benchmark_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be tested without calling APIs",
    )
    benchmark_parser.add_argument(
        "--subset-doc",
        type=str,
        default=None,
        help="Document IR path for subset evaluation (default: auto-detect smallest)",
    )

    # Version diff command
    diff_parser = subparsers.add_parser(
        "version-diff",
        help="Compare two document versions and generate differential report",
    )
    diff_parser.add_argument("version_a", type=str, help="Path to older version")
    diff_parser.add_argument("version_b", type=str, help="Path to newer version")
    diff_parser.add_argument(
        "--format", choices=["markdown", "text", "html"], default="markdown",
        help="Report format (default: markdown)",
    )
    diff_parser.add_argument(
        "--output", type=str, default=None,
        help="Output file path (default: print to stdout)",
    )

    # Version check command
    version_check_parser = subparsers.add_parser(
        "version-check",
        help="Detect document version families in the corpus",
    )

    # TBD Dashboard command
    tbd_parser = subparsers.add_parser(
        "tbd-dashboard",
        help="Cross-document TBD/TBR tracking dashboard",
    )
    tbd_parser.add_argument(
        "--ingest",
        type=str,
        nargs="*",
        help="Document IR YAML files to ingest TBDs from",
    )
    tbd_parser.add_argument(
        "--correlate",
        action="store_true",
        help="Run cross-document TBD correlation",
    )
    tbd_parser.add_argument(
        "--export",
        choices=["csv", "markdown"],
        default=None,
        help="Export TBD list in specified format",
    )
    tbd_parser.add_argument(
        "--filter-status",
        choices=["open", "assigned", "resolved", "verified"],
        default=None,
        help="Filter by status",
    )
    tbd_parser.add_argument(
        "--region", type=str, default="us-east-1", help="AWS region"
    )

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
    elif args.command == "ocr-ingest":
        _cmd_ocr_ingest(args)
    elif args.command == "search-index":
        _cmd_search_index(args)
    elif args.command == "search":
        _cmd_search(args)
    elif args.command == "search-eval":
        _cmd_search_eval(args)
    elif args.command == "search-models":
        _cmd_search_models(args)
    elif args.command == "search-status":
        _cmd_search_status(args)
    elif args.command == "search-benchmark":
        _cmd_search_benchmark(args)
    elif args.command == "tbd-dashboard":
        _cmd_tbd_dashboard(args)
    elif args.command == "version-diff":
        _cmd_version_diff(args)
    elif args.command == "version-check":
        _cmd_version_check(args)


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


def _cmd_render(
    pdf_path: Path, pages_spec: str | None, output: str | None, report: bool = False
) -> None:
    """Render pages from a PDF back to a new PDF via the extraction pipeline."""
    import fitz

    from src.output_dir import OutputDir
    from src.rendering import render_pages_to_pdf

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()

    page_numbers = _parse_page_range(pages_spec, total_pages)

    if output:
        output_path = Path(output)
    else:
        out = OutputDir(document_name=pdf_path.stem)
        output_path = out.reconstructed_pdf_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Source: {pdf_path} ({total_pages} pages)")
    print(f"Rendering pages: {page_numbers}")

    result = render_pages_to_pdf(pdf_path, page_numbers, output_path)
    print(f"Output: {result} ({len(page_numbers)} pages)")

    if report:
        report_path = output_path.parent / "report.md"
        _cmd_report(pdf_path, output_path, str(report_path))


def _cmd_report(pdf_path: Path, regen_path: Path, output: str | None) -> None:
    """Generate a fidelity report comparing original vs regenerated PDF."""
    from src.report import generate_report

    if output:
        report_path = Path(output)
    else:
        report_path = Path("output") / f"{pdf_path.stem}_report.md"

    print("Generating report...")
    report = generate_report(pdf_path, regen_path, report_path)
    print(f"Report: {report_path}")

    # Print summary to console
    for line in report.split("\n"):
        if (
            line.startswith("| Average")
            or line.startswith("| Pages with")
            or line.startswith("| Word")
        ):
            print(f"  {line}")


def _cmd_ocr_ingest(args) -> None:
    """Run OCR pipeline on a scanned/flattened PDF."""
    from src.ocr import ocr_ingest
    from src.ocr.ocr_renderer import render_ocr_searchable
    from src.output_dir import OutputDir
    from src.serialization import to_yaml

    pdf_path = Path(args.pdf_path)
    out = OutputDir(base_dir=args.output_dir, document_name=pdf_path.stem)

    print(f"OCR Ingestion: {pdf_path}")
    print(f"  Region: {args.region}")
    print(f"  Rekognition: {'yes' if not args.no_rekognition else 'no'}")
    print(f"  Bedrock classify: {'yes' if not args.no_classify else 'no'}")
    print(f"  Bedrock disambiguate: {'yes' if not args.no_disambiguate else 'no'}")
    print()

    document_ir, cost_tracker, review_flags = ocr_ingest(
        pdf_path,
        region=args.region,
        use_rekognition=not args.no_rekognition,
        use_bedrock_classify=not args.no_classify,
        use_bedrock_disambiguate=not args.no_disambiguate,
    )

    # Save intermediate artifacts
    to_yaml(document_ir, out.ir_path)
    print(f"Document IR: {out.ir_path}")
    print(f"  Pages: {document_ir.page_count}")
    total_blocks = sum(len(p.text_blocks) for p in document_ir.pages)
    print(f"  Text blocks: {total_blocks}")

    # Save review flags
    if review_flags:
        with open(out.review_flags_path, "w") as f:
            f.write(f"# Human Review Flags: {pdf_path.name}\n\n")
            f.write(f"Total flags: {len(review_flags)}\n\n")
            f.write("| Page | Reason | Candidates | Confidence |\n")
            f.write("|------|--------|------------|------------|\n")
            for flag in review_flags:
                cands = ", ".join(f'"{c}"' for c in flag.candidates)
                f.write(
                    f"| {flag.page} | {flag.reason} | {cands} | "
                    f"{flag.confidence:.0f}% |\n"
                )
        print(f"  Review flags: {len(review_flags)} -> {out.review_flags_path}")
    else:
        print("  Review flags: 0 (all high confidence)")

    # Save cost report
    with open(out.ocr_cost_path, "w") as f:
        f.write(f"# OCR Cost Report: {pdf_path.name}\n\n")
        f.write(cost_tracker.summary())

    # Generate final searchable PDF
    render_ocr_searchable(pdf_path, document_ir, out.reconstructed_pdf_path)
    print(f"\nFinal PDF: {out.reconstructed_pdf_path}")

    # Cost summary
    print()
    print(cost_tracker.summary())
    print(f"\n{out.summary()}")


def _cmd_search_index(args) -> None:
    """Index a Document IR file into all configured search indices."""
    from src.search.config import SearchConfig
    from src.search.pipeline import SearchPipeline

    ir_path = Path(args.ir_path)
    if not ir_path.exists():
        print(f"Error: {ir_path} not found")
        sys.exit(1)

    config = SearchConfig(aws_region=args.region)
    pipeline = SearchPipeline(config=config, region=args.region)

    print(f"Indexing: {ir_path}")
    results = pipeline.ingest_document(ir_path)
    print("\nResults:")
    for index_name, count in results.items():
        print(f"  {index_name}: {count} chunks")


def _cmd_search(args) -> None:
    """Search across indexed ICD documents."""
    from src.search.config import SearchConfig
    from src.search.retrieval import RetrievalMode

    mode_map = {
        "keyword": RetrievalMode.KEYWORD_ONLY,
        "vector": RetrievalMode.VECTOR_ONLY,
        "hybrid": RetrievalMode.HYBRID,
        "rrf": RetrievalMode.HYBRID_RRF,
    }

    config = SearchConfig(
        opensearch_host="localhost",
        opensearch_port=9200,
        opensearch_scheme="http",
        aws_region=args.region,
    )
    mode = mode_map[args.mode]

    if hasattr(args, "rag") and args.rag:
        # RAG mode: synthesized answer with citations
        from src.search.rag import RAGPipeline

        rag = RAGPipeline(search_config=config, region=args.region)
        answer = rag.ask(args.query, k=args.k, mode=mode)
        print(answer.formatted())
    else:
        # Standard search: raw results
        from src.search.pipeline import SearchPipeline

        pipeline = SearchPipeline(config=config, region=args.region)
        result = pipeline.search(args.query, k=args.k, mode=mode)

        print(f"Query: {args.query}")
        print(f"Mode: {args.mode} | Index: {result.index_name} | Took: {result.took_ms}ms")
        print(f"Results ({len(result.hits)}/{result.total_hits}):\n")

        for i, hit in enumerate(result.hits, 1):
            print(f"  {i}. [{hit.score:.4f}] {hit.document_title} (p{hit.page_number})")
            if hit.section_heading:
                print(f"     Section: {hit.section_heading}")
            # Show first 120 chars of text
            preview = hit.text[:120].replace("\n", " ")
            if len(hit.text) > 120:
                preview += "..."
            print(f"     {preview}")
            print()


def _cmd_search_eval(args) -> None:
    """Run search evaluation benchmark."""
    from src.search.config import SearchConfig
    from src.search.pipeline import SearchPipeline

    config = SearchConfig(aws_region=args.region)
    pipeline = SearchPipeline(config=config, region=args.region)

    print("Running search evaluation benchmark...")
    print(f"  K={args.k}")
    print()

    run = pipeline.run_eval(k=args.k)
    print(run.summary_table())


def _cmd_search_models(args) -> None:
    """Check embedding model availability on Bedrock."""
    from src.search.model_registry import ModelRegistry

    registry = ModelRegistry(region=args.region)
    report = registry.check_availability()
    print(report.summary())


def _cmd_search_status(args) -> None:
    """Show search pipeline status."""
    from src.search.config import SearchConfig
    from src.search.pipeline import SearchPipeline

    config = SearchConfig(aws_region=args.region)
    pipeline = SearchPipeline(config=config, region=args.region)
    status = pipeline.status()

    print("Search Pipeline Status")
    print("=" * 40)
    print(f"Configured models: {status['configured_models']}")
    print(f"Total indexed chunks: {status['total_documents_indexed']}")
    print(f"Last eval run: {status['last_eval_run'] or 'never'}")
    if status['best_config']:
        print(f"Best config: {status['best_config']} ({status['best_recall']:.1%} recall)")
    print()
    if status['indices']:
        print("Indices:")
        for idx in status['indices']:
            size_kb = idx['size_bytes'] / 1024
            print(f"  {idx['index_name']}: {idx['doc_count']} chunks ({size_kb:.1f} KB)")
    else:
        print("No indices found (run search-index first)")


def _cmd_search_benchmark(args) -> None:
    """Benchmark newly-discovered embedding models."""
    from src.search.benchmark import ModelBenchmark
    from src.search.config import SearchConfig

    config = SearchConfig(
        opensearch_host="localhost",
        opensearch_port=9200,
        opensearch_scheme="http",
        aws_region=args.region,
    )

    benchmark = ModelBenchmark(
        search_config=config,
        region=args.region,
        budget_cap=args.budget_cap,
    )

    # Find subset document for Stage 2
    subset_path = args.subset_doc
    if not subset_path:
        # Auto-detect: use smallest document IR in output/
        output_dir = Path("output")
        ir_files = list(output_dir.glob("*_document_ir.yaml"))
        if ir_files:
            subset_path = str(min(ir_files, key=lambda p: p.stat().st_size))
        else:
            print("Error: No Document IR files found in output/. Run 'ingest' first.")
            sys.exit(1)

    # All IR files for Stage 3
    output_dir = Path("output")
    all_ir_paths = [str(p) for p in output_dir.glob("*_document_ir.yaml")]

    if args.dry_run:
        print("DRY RUN — showing what would be tested:")
        print()

    report = benchmark.run(
        subset_ir_path=subset_path,
        full_ir_paths=all_ir_paths,
        dry_run=args.dry_run,
    )

    print(report.summary())


def _cmd_tbd_dashboard(args) -> None:
    """Cross-document TBD/TBR tracking dashboard."""
    from src.search.config import SearchConfig
    from src.search.tbd_dashboard import TBDDashboard

    config = SearchConfig(
        opensearch_host="localhost",
        opensearch_port=9200,
        opensearch_scheme="http",
        aws_region=args.region,
    )
    dashboard = TBDDashboard(search_config=config, region=args.region)

    # Ingest new documents if specified
    if args.ingest:
        for ir_path in args.ingest:
            path = Path(ir_path)
            if path.exists():
                count = dashboard.ingest_document(path)
                print(f"  Ingested {count} TBD items from {path.name}")
            else:
                print(f"  Warning: {ir_path} not found, skipping")
        dashboard.save_state()
        print()

    # Run correlation if requested
    if args.correlate:
        print("Running cross-document correlation...")
        correlations = dashboard.correlate()
        dashboard.save_state()
        if correlations:
            print(f"  Found {len(correlations)} correlations")
            for c in correlations[:5]:
                conflict = " ⚠️ CONFLICT" if c.conflict else ""
                print(f"    {c.item_a_id} ↔ {c.item_b_id} ({c.confidence}){conflict}")
        else:
            print("  No cross-document correlations found")
        print()

    # Export if requested
    if args.export == "csv":
        print(dashboard.export_csv())
    elif args.export == "markdown":
        print(dashboard.export_markdown())
    elif not args.ingest and not args.correlate:
        # Default: show summary
        print(dashboard.summary())


def _cmd_version_diff(args) -> None:
    """Compare two document versions and generate a differential report."""
    from src.version_diff import full_diff, generate_report

    path_a = Path(args.version_a)
    path_b = Path(args.version_b)

    if not path_a.exists():
        print(f"Error: {path_a} not found")
        sys.exit(1)
    if not path_b.exists():
        print(f"Error: {path_b} not found")
        sys.exit(1)

    print(f"Comparing: {path_a.name} → {path_b.name}")
    print("Running differential analysis...")
    print()

    report = full_diff(path_a, path_b)
    output = generate_report(report, format=args.format)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output)
        print(f"Report saved: {out_path}")
    else:
        print(output)


def _cmd_version_check(args) -> None:
    """Detect document version families in the corpus."""
    from src.version_diff import detect_families

    families = detect_families()

    if not families:
        print("No document version families detected.")
        return

    print(f"Document Version Families ({len(families)} found)")
    print("=" * 50)
    for family in families:
        status_icon = {
            "identical": "✅",
            "page_count_differs": "⚠️",
            "content_differs": "🔍",
        }.get(family.status, "❓")
        print(f"\n{status_icon} {family.base_name} ({len(family.versions)} versions) — {family.status}")
        for v in family.versions:
            rev = f" Rev {v.revision}" if v.revision else ""
            print(f"    {v.filename}: {v.page_count}pg{rev} ({v.doc_type})")


if __name__ == "__main__":
    main()
