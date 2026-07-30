#!/usr/bin/env python
"""Run the Docker-only (WeasyPrint-dependent) test suite.

This script is intended to be executed inside the Docker backend container
where GTK/Pango/WeasyPrint are properly installed.

Usage from host:
    docker compose exec backend python -m pytest tests/ -m docker_only -v
    # OR
    docker compose exec backend python tests/run_docker_tests.py

Usage locally (if GTK/Pango installed):
    python -m pytest tests/ -m docker_only -v
"""

import subprocess
import sys


def main():
    """Run pytest with docker_only marker."""
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-m", "docker_only",
        "-v",
        "--tb=short",
        "-q",
    ]
    result = subprocess.run(cmd, cwd=str(__file__).rsplit("tests", 1)[0].rstrip("/\\"))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
