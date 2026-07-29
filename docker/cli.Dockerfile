# =============================================================================
# ICD Writer — CLI Tool (Ingestion, Rendering, Search Indexing)
# Standalone image for running the pipeline commands (ingest, render, report).
# Usage: docker run icd-cli ingest <pdf_path>
# =============================================================================
FROM python:3.10-slim

# System dependencies for WeasyPrint, PyMuPDF, and font rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    # WeasyPrint dependencies
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    # PyMuPDF / PDF rendering
    libmupdf-dev \
    # Font packages (metric-compatible substitutes)
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    fonts-liberation2 \
    fonts-dejavu-core \
    # Utilities
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

WORKDIR /app

# Install Python dependencies
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

# Install project
COPY pyproject.toml .
COPY src/ src/
COPY schemas/ schemas/
COPY tests/ tests/
RUN pip install --no-cache-dir -e .

# Verify installation
RUN python -m pytest tests/unit/ -q

ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--help"]
