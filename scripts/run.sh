#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.."

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "Docker detected. Starting RepoGuard with Docker Compose..."
    docker compose up --build
else
    echo "Docker unavailable. Starting RepoGuard locally..."

    if [ -f .venv/bin/python ]; then
        PYTHON=".venv/bin/python"
    elif [ -f .venv/Scripts/python ]; then
        PYTHON=".venv/Scripts/python"
    else
        echo "No virtual environment found. Run ./scripts/setup.sh first, or set PYTHON." >&2
        PYTHON="${PYTHON:-python}"
    fi

    "$PYTHON" -m uvicorn repoguard.main:app \
        --host 127.0.0.1 \
        --port 8000 \
        --reload
fi