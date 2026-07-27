# ICD Writer

NASA Interface Control Document (ICD) PDF conversion and regeneration pipeline. Extracts text, tables, diagrams, and images into a structured intermediate representation (YAML/JSON), then regenerates faithful PDFs via HTML/CSS with word-level positioning, stroke calibration, and font-metric correction.

## Architecture

```
Original PDF
    → PDF ingestion (SHA-256 hash, metadata)
    → Page classification (text, scanned, table, diagram)
    → Text extraction (character-level positions, fonts, bounding boxes)
    → Image extraction (with border detection)
    → Vector graphics extraction (lines, curves, paths)
    → Document IR (YAML/JSON — the editable intermediate)
    → HTML/CSS rendering (absolute positioning, word-level kerning)
    → WeasyPrint PDF generation
    → Visual fidelity comparison
```

## Quick Start

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e ".[dev]"
pip install weasyprint numpy boto3 python-multipart

# Install metric-compatible fonts (recommended)
sudo apt install fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation2

# Run tests
python3 -m pytest tests/ -v
```

## Running the Editor (UI)

```bash
# Terminal 1 — Backend API
source .venv/bin/activate
uvicorn src.api.app:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. Click **Open** to load a PDF.

## CLI Usage (No UI)

```bash
# Show PDF metadata
python3 -m src.cli info path/to/document.pdf

# Run full extraction pipeline
python3 -m src.cli ingest path/to/document.pdf --output-dir ./output --format yaml

# Render pages back to PDF (faithful reproduction)
python3 -m src.cli render path/to/document.pdf --pages 1-5 --report

# OCR pipeline for scanned/flattened PDFs (requires AWS credentials)
python3 -m src.cli ocr-ingest path/to/scanned.pdf --region us-east-1
```

## Visual Fidelity Results

Tested against `icds/20150010976.pdf` (NASA LVC ICD, 35 pages):

| Page | Type | Pixel Match | F1 Score |
|------|------|-------------|----------|
| 1 | Cover (logo + title) | 98.2% | 88.7% |
| 2 | Title/author | 98.4% | 87.6% |
| 3 | Full-page image | 100.0% | 100.0% |
| 4 | Revision table (136 rects) | 99.1% | 84.7% |
| 5 | System architecture diagram | 90.9% | 78.2% |

## Key Techniques

- **Word-level positioning** — each word placed at its exact PDF x-coordinate with `overflow:hidden` to prevent column bleed
- **Stroke width calibration** — empirically scaled (0.5×) to match PDF antialiasing behavior
- **Font substitution** — Carlito for Calibri, Liberation Sans/Serif for Arial/Times
- **Connector image filtering** — solid-black narrow PNGs (redundant with stroked lines) are detected and skipped
- **Bordered box inset** — diagram element images with black borders are inset 0.5pt to prevent overlap stacking
- **SVG path rendering** — bezier curves and complex paths rendered via inline SVG

## Project Structure

```
src/
├── models/              # Pydantic data models (Document IR, ICD IR)
│   ├── common.py        # BoundingBox, Provenance, DocumentMetadata
│   ├── document_ir.py   # Physical layout: pages, blocks, tables, figures
│   └── icd_ir.py        # Engineering meaning: requirements, interfaces, signals
├── ingestion/           # PDF reading, hashing, metadata extraction
├── classification/      # Page content classification
├── extraction/          # Text block extraction with coordinates
├── rendering/           # PDF regeneration via HTML/CSS/WeasyPrint
│   └── page_renderer.py # Core rendering engine
├── pipeline.py          # Extraction orchestrator
├── serialization.py     # YAML/JSON import/export
└── cli.py              # Command-line interface

schemas/                 # Auto-generated JSON Schema from models
tests/
├── unit/               # Model and utility tests
└── integration/        # Full pipeline tests against sample PDFs
```

## Technology Stack

- **Python 3.10+**
- **PyMuPDF** — text/geometry/image extraction with character-level positioning
- **WeasyPrint** — HTML/CSS to PDF rendering
- **Pydantic** — data models, validation, serialization
- **PyYAML** — canonical intermediate format
- **NumPy/Pillow** — visual fidelity comparison
- **FastAPI** — API layer (future)
- **pytest** — testing

## Strategy

See `STRATEGY.md` for the full project strategy document covering:
- Proven techniques and their empirical calibration
- Visual fidelity results across all 35 pages
- Two-layer IR (Document IR + Semantic ICD IR)
- What was and wasn't needed from the original plan
- Delivery phases and next steps
