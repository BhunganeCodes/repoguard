"""Runtime data store for the product interface.

Assessment outputs are written once to an immutable repository-local store
(similar to the evaluation framework's snapshot/results stores) so users can
re-open any assessment later by identity. Nothing here writes into the frozen
evaluation dataset, snapshots, or benchmark results.

The base directory is configurable via ``REPOGUARD_DATA_DIR`` and defaults
to ``<repo>/data``. All outputs are content-addressed by the assessment
result identity.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from evaluation.snapshot.paths import project_root

ENV_DATA_DIR = "REPOGUARD_DATA_DIR"

RESULT_IDENTITY_PREFIX = "repoguard-v1:"


def data_dir() -> Path:
    configured = os.environ.get(ENV_DATA_DIR, "").strip()
    return Path(configured) if configured else project_root() / "data"


def snapshots_dir() -> Path:
    return data_dir() / "snapshots"


def results_dir() -> Path:
    return data_dir() / "results"


def digest_of(identity: str) -> str:
    """Normalize an identity (full ``repoguard-v1:<sha>`` or bare sha) to its digest."""
    stripped = identity.strip()
    if stripped.lower().startswith(RESULT_IDENTITY_PREFIX):
        return stripped.split(":", 1)[1]
    return stripped


def result_path(digest: str) -> Path:
    return results_dir() / f"{digest}.yaml"


def evidence_path(digest: str) -> Path:
    return results_dir() / f"{digest}.evidence.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"artifact is not a YAML mapping: {path}")
    return raw
