#!/usr/bin/env bash

set -euo pipefail

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "Docker detected. Starting RepoGuard with Docker Compose..."
    docker compose up --build
else
    echo "Docker unavailable. Starting RepoGuard locally..."

    python -m uvicorn repoguard.main:app \
        --host 127.0.0.1 \
        --port 8000 \
        --reload
fi