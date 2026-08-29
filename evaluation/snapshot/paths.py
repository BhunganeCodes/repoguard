"""Snapshot store layout.

Snapshots are written once to a fixed location below the repository-local
snapshot store and are never moved after acquisition.
"""

from __future__ import annotations

import re
from pathlib import Path

from evaluation.snapshot.models import ManifestCase

SNAPSHOT_RECORD_FILE = "snapshot.yaml"
INVENTORY_FILE = "inventory.yaml"
CHECKOUT_DIR = "checkout"

_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def project_root() -> Path:
    """Repo root: evaluation/snapshot -> evaluation -> repo root."""
    return Path(__file__).resolve().parents[2]


def default_store() -> Path:
    """Default local snapshot store: <repo>/evaluation/snapshots (gitignored)."""
    return project_root() / "evaluation" / "snapshots"


def snapshot_dir_name(case: ManifestCase) -> str:
    """Deterministic on-disk name for a case: <id>-<name-slug>."""
    slug = _SLUG.sub("-", case.name).strip("-").lower()
    if not slug:
        slug = "repo"
    return f"{case.candidate_id}-{slug}"


def snapshot_dir(store: Path, case: ManifestCase) -> Path:
    """Fixed, immutable location of a case's snapshot under the store."""
    return store / snapshot_dir_name(case)
