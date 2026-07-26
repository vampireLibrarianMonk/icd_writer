#!/usr/bin/env bash
# Setup script for local development
# Run: source setup.sh

set -e

echo "=== ICD Writer Setup ==="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1-2)
echo "Python version: $PYTHON_VERSION"
if [[ "$PYTHON_VERSION" < "3.10" ]]; then
    echo "ERROR: Python 3.10+ required"
    exit 1
fi

# Install system font dependencies
echo ""
echo "Installing system font packages..."
if command -v apt-get &> /dev/null; then
    sudo apt-get install -y --no-install-recommends \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
        fonts-liberation2 \
        fonts-dejavu-core \
        fontconfig \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libglib2.0-0
    sudo fc-cache -fv
elif command -v dnf &> /dev/null; then
    sudo dnf install -y \
        google-carlito-fonts \
        google-caladea-fonts \
        liberation-sans-fonts \
        liberation-serif-fonts \
        dejavu-sans-fonts \
        pango \
        cairo \
        gdk-pixbuf2
    sudo fc-cache -fv
else
    echo "WARNING: Unsupported package manager. Install fonts manually:"
    echo "  - Carlito (Calibri substitute)"
    echo "  - Caladea (Cambria substitute)"
    echo "  - Liberation Sans/Serif (Arial/Times substitutes)"
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install project with dev dependencies
echo ""
echo "Installing project..."
pip install --upgrade pip
pip install -e ".[dev]"

# Install rendering dependencies
pip install weasyprint numpy

# Verify
echo ""
echo "Running tests..."
python3 -m pytest tests/ -q

echo ""
echo "=== Setup complete ==="
echo "Activate with: source .venv/bin/activate"
echo "Run: python3 -m src.cli --help"
