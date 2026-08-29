"""Persisting per-case outcomes for a benchmark run.

Case records are deterministic (key-sorted) YAML, written under the run's
``cases/`` directory; every result path is stored relative to the run
directory so a run is byte-identical and relocatable. Results are never
overwritten: the run directory is created fresh by the runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.benchmark.models import ExecutedCase
from evaluation.benchmark.paths import case_record_file
from evaluation.evidence.serialize import canonical_dump

_SCHEMA_VERSION = 1


def relative_to_run(base_dir: Path, path: Path) -> str:
    """Stable experiment-relative location of a result artifact."""
    return path.relative_to(base_dir).as_posix()


def write_case_record(results_dir: Path, run_id: str, case: ExecutedCase) -> Path:
    """Write ``cases/<case-id>.yaml`` for one executed case."""
    record: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "system": "benchmark",
        "case_id": case.case_id,
        "status": case.status,
        "evidence_identity": case.evidence_identity,
        "baseline": case.baseline.to_dict() if case.baseline is not None else None,
        "repoguard": case.repoguard.to_dict() if case.repoguard is not None else None,
        "delta": case.delta,
        "error": case.error.to_dict() if case.error is not None else None,
    }
    record_path = case_record_file(results_dir, run_id, case.case_id)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(canonical_dump(record), encoding="utf-8", newline="\n")
    return record_path
