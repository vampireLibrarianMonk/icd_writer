# =============================================================================
# ICD Writer — Backend API Server (FastAPI + Uvicorn)
# Serves the REST API for document loading, editing, search, and RAG.
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
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

WORKDIR /app

# Install Python dependencies
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

# Install additional runtime dependencies not in lock file
RUN pip install --no-cache-dir \
    boto3>=1.35.0 \
    python-multipart>=0.0.20 \
    opensearch-py==2.8.0 \
    requests-aws4auth>=1.3.0

# Install project in editable mode
COPY pyproject.toml .
COPY src/ src/
COPY schemas/ schemas/
RUN pip install --no-cache-dir -e .

# Create output directory for Document IR files
RUN mkdir -p /app/output /app/icds

# Expose the API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# Run the FastAPI server
CMD ["uvicorn", "src.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
