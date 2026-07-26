# ICD Writer - Software Bill of Materials (SBOM)
# Generated: 2026-07-25
# Python 3.10+

## Core Dependencies (pinned in pyproject.toml)
pydantic==2.11.3
pyyaml==6.0.2
pymupdf==1.25.5
pdfplumber==0.11.6
pikepdf==9.7.0
pillow==11.2.1
numpy==2.2.6
weasyprint==69.0

## API
fastapi==0.115.12
uvicorn==0.34.2

## Templating
jinja2==3.1.6

## Development
pytest==8.3.5
pytest-cov==6.1.1
ruff==0.11.12
mypy==1.15.0

## System Dependencies (apt packages required)

### WeasyPrint rendering
# libpango-1.0-0
# libpangocairo-1.0-0
# libgdk-pixbuf-2.0-0
# libffi-dev
# libcairo2
# libglib2.0-0

### Font packages (metric-compatible substitutes)
# fonts-crosextra-carlito   — Calibri substitute (Google Carlito)
# fonts-crosextra-caladea   — Cambria substitute (Google Caladea)
# fonts-liberation2         — Arial/Times/Courier substitutes (Liberation Sans/Serif/Mono)
# fonts-dejavu-core         — Fallback sans/serif/mono

### Utilities
# fontconfig                — Font discovery and configuration
