#!/usr/bin/env bash
#
# Set up the RepoGuard development environment.
#
# Requirements: Python 3.12+
#
# Usage:
#   ./scripts/setup.sh

set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" --version >/dev/null 2>&1; then
    echo "error: Python 3.12+ is required (set PYTHON if 'python3' is not correct)." >&2
    exit 1
fi

echo "Creating virtual environment..."
"$PYTHON" -m venv .venv

if [ -f .venv/bin/python ]; then
    VENV_PYTHON=".venv/bin/python"
else
    VENV_PYTHON=".venv/Scripts/python"
fi

echo "Installing project with dev dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e ".[dev]"

echo ""
echo "Setup complete."
echo "Run tests:       ./scripts/test.sh"
echo "Run the API:     ./scripts/run.sh"