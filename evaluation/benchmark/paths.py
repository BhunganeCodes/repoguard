"""Benchmark result storage layout.

Each benchmark run owns a single, immutable output directory below the
default benchmark results area ``evaluation/results/benchmark/``:

.. code-block:: text

    <out>/
      <run-id>/
        run-manifest.yaml
        baseline/<case-id>/result.yaml
        repoguard/<case-id>/result.yaml
        cases/<case-id>.yaml

A run directory is created fresh (never overwritten); previous runs are
never touched. ``run-manifest.yaml`` records which evaluators ran, the exact
input identities, and the relative location of every result, so a run is
reproducible from the manifest alone (docs/benchmark-runner.md,
"Result isolation").
"""

from __future__ import annotations

from pathlib import Path

RUN_MANIFEST_FILE = "run-manifest.yaml"

_BASELINE = "baseline"
_REPOGUARD = "repoguard"
_CASES = "cases"


def project_root() -> Path:
    """Repo root: evaluation/benchmark -> evaluation -> repo root."""
    return Path(__file__).resolve().parents[2]


def default_results_dir() -> Path:
    """Default (gitignored) location of benchmark run outputs."""
    return project_root() / "evaluation" / "results" / "benchmark"


def run_dir(results_dir: Path, run_id: str) -> Path:
    """The immutable output directory for one run."""
    return results_dir / run_id


def run_manifest_file(results_dir: Path, run_id: str) -> Path:
    return run_dir(results_dir, run_id) / RUN_MANIFEST_FILE


def baseline_result_file(results_dir: Path, run_id: str, case_id: str) -> Path:
    return run_dir(results_dir, run_id) / _BASELINE / case_id / "result.yaml"


def repoguard_result_file(results_dir: Path, run_id: str, case_id: str) -> Path:
    return run_dir(results_dir, run_id) / _REPOGUARD / case_id / "result.yaml"


def case_record_file(results_dir: Path, run_id: str, case_id: str) -> Path:
    return run_dir(results_dir, run_id) / _CASES / f"{case_id}.yaml"
