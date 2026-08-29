"""RepoGuard result storage conventions.

Results are local, in-progress artifacts under the gitignored
``evaluation/results/local/`` tree per docs/evaluation.md Section 13.2;
RepoGuard and baseline outputs are stored in separate directories.
"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repo root: evaluation/repoguard -> evaluation -> repo root."""
    return Path(__file__).resolve().parents[2]


def default_results_dir() -> Path:
    """Default local (gitignored) location for RepoGuard run artifacts."""
    return project_root() / "evaluation" / "results" / "local" / "repoguard"
