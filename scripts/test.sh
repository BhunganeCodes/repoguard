#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .venv/bin/python ]; then
    PYTHON=".venv/bin/python"
elif [ -f .venv/Scripts/python ]; then
    PYTHON=".venv/Scripts/python"
else
    echo "No virtual environment found. Run ./scripts/setup.sh first, or set PYTHON." >&2
    PYTHON="${PYTHON:-python}"
fi

"$PYTHON" -m pytest