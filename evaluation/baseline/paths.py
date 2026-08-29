"""Baseline result storage conventions.

Results are local, in-progress artifacts under the gitignored
``evaluation/results/local/`` tree per docs/evaluation.md Section 13.2;
finalized, manifest-complete results are promoted to committed locations by
later issues.
"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repo root: evaluation/baseline -> evaluation -> repo root."""
    return Path(__file__).resolve().parents[2]


def default_results_dir() -> Path:
    """Default local (gitignored) location for baseline run artifacts."""
    return project_root() / "evaluation" / "results" / "local" / "baseline"
