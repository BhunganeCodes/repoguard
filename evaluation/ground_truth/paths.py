"""Local storage conventions for ground-truth artifacts.

Ground truth is the human-produced reference for each frozen case and must
never be mixed with system results (docs/evaluation.md Section 6, Section
13.2 and docs/ground-truth.md). Reviewer assessments, adjudication records,
and consensus artifacts are stored under a gitignored ``local/`` tree that
is separate from ``evaluation/results/``, ``evaluation/baseline/``, and
``evaluation/repoguard/`` outputs.
"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repo root: evaluation/ground_truth -> evaluation -> repo root."""
    return Path(__file__).resolve().parents[2]


def default_ground_truth_dir() -> Path:
    """Default local (gitignored) root for ground-truth artifacts."""
    return project_root() / "evaluation" / "ground_truth" / "local"


def reviews_dir(base: Path | None = None) -> Path:
    return (base or default_ground_truth_dir()) / "reviews"


def adjudications_dir(base: Path | None = None) -> Path:
    return (base or default_ground_truth_dir()) / "adjudications"


def consensus_dir(base: Path | None = None) -> Path:
    return (base or default_ground_truth_dir()) / "consensus"


def review_file(case_id: str, reviewer_id: str, base: Path | None = None) -> Path:
    """``C001-R01-review.yaml`` for a case and pseudonymous reviewer."""
    return reviews_dir(base) / f"{case_id}-{reviewer_id}-review.yaml"


def adjudication_file(case_id: str, base: Path | None = None) -> Path:
    return adjudications_dir(base) / f"{case_id}-adjudication.yaml"


def consensus_file(case_id: str, base: Path | None = None) -> Path:
    """``C001-ground-truth.yaml``: the final consensus artifact for a case."""
    return consensus_dir(base) / f"{case_id}-ground-truth.yaml"
