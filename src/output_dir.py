"""Output directory management.

Organizes pipeline output into a structured directory hierarchy:

    output/
    └── YYYY-MM-DD_HHMMSS/          ← run timestamped
        └── <document_stem>/
            ├── intermediate/        ← IR, cost reports, review flags
            │   ├── document_ir.yaml
            │   ├── ocr_cost.md
            │   └── review_flags.md
            ├── final/               ← deliverable output
            │   ├── reconstructed.pdf
            │   └── report.md
            └── debug/               ← page images, diffs (optional)
                ├── page1_original.png
                └── page1_regenerated.png
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class OutputDir:
    """Manages structured output directory for a pipeline run."""

    def __init__(self, base_dir: Path | str = "output", document_name: str = "document"):
        base_dir = Path(base_dir)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        self.run_dir = base_dir / timestamp / document_name
        self.intermediate = self.run_dir / "intermediate"
        self.final = self.run_dir / "final"
        self.debug = self.run_dir / "debug"

        # Create directories
        self.intermediate.mkdir(parents=True, exist_ok=True)
        self.final.mkdir(parents=True, exist_ok=True)

    def enable_debug(self) -> None:
        """Create debug directory (only when needed)."""
        self.debug.mkdir(parents=True, exist_ok=True)

    @property
    def ir_path(self) -> Path:
        return self.intermediate / "document_ir.yaml"

    @property
    def ocr_cost_path(self) -> Path:
        return self.intermediate / "ocr_cost.md"

    @property
    def review_flags_path(self) -> Path:
        return self.intermediate / "review_flags.md"

    @property
    def reconstructed_pdf_path(self) -> Path:
        return self.final / "reconstructed.pdf"

    @property
    def report_path(self) -> Path:
        return self.final / "report.md"

    @property
    def text_report_path(self) -> Path:
        return self.final / "text_accuracy.md"

    def page_original_path(self, page_num: int) -> Path:
        self.enable_debug()
        return self.debug / f"page{page_num}_original.png"

    def page_regenerated_path(self, page_num: int) -> Path:
        self.enable_debug()
        return self.debug / f"page{page_num}_regenerated.png"

    def summary(self) -> str:
        """Print the output directory structure."""
        lines = [f"Output: {self.run_dir}"]
        for subdir in [self.intermediate, self.final, self.debug]:
            if subdir.exists():
                files = sorted(subdir.iterdir())
                if files:
                    lines.append(f"  {subdir.name}/")
                    for f in files:
                        lines.append(f"    {f.name} ({f.stat().st_size:,} bytes)")
        return "\n".join(lines)
