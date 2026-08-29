"""Fail-closed input validation for metrics computations.

Validation reuses the benchmark runner's authoritative manifest/result checks
(``validate_run`` verifies structure, per-case result identities, dataset,
rubric, and evidence bindings) and adds ground-truth binding checks: a
consumed consensus artifact must match the run's dataset version, rubric
version, case set, and per-case evidence identity, and must pass its own
content-identity check. Any problem fails the computation closed; problems
are never skipped silently.
"""

from __future__ import annotations

from typing import Any

from evaluation.benchmark.manifest import validate_run
from evaluation.ground_truth.serialize import ground_truth_identity
from evaluation.metrics._version import METRICS_SCHEMA_VERSION, SYSTEM_ID
from evaluation.metrics.serialize import recompute_identity

_GROUND_TRUTH_STATUSES = frozenset({"consensus", "contested"})


def validate_run_dir(run_dir: Any) -> list[str]:
    """Validate an entire benchmark run directory; returns problems."""
    return validate_run(run_dir)


def validate_ground_truth_artifact(
    artifact: dict[str, Any],
    *,
    dataset_version: str,
    rubric_version: str,
    evidence_identity: str | None,
    run_case_ids: set[str],
) -> list[str]:
    """Fail-closed checks on one consensus artifact bound to a run."""
    problems: list[str] = []

    case_id = artifact.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        problems.append("ground truth artifact has no case_id")
        return problems
    if case_id not in run_case_ids:
        problems.append(f"ground truth for unknown case {case_id!r} (not in the run)")
        return problems

    if artifact.get("dataset_version") != dataset_version:
        problems.append(
            f"case {case_id}: ground truth dataset version "
            f"{artifact.get('dataset_version')!r} != run {dataset_version!r}"
        )
    if artifact.get("rubric_version") != rubric_version:
        problems.append(
            f"case {case_id}: ground truth rubric version "
            f"{artifact.get('rubric_version')!r} != run {rubric_version!r}"
        )

    recorded = artifact.get("evidence_identity")
    if evidence_identity is None:
        problems.append(
            f"case {case_id}: the run produced no evidence for this case, "
            "so no ground truth can be bound to it"
        )
    elif recorded != evidence_identity:
        problems.append(
            f"case {case_id}: ground truth evidence identity does not match the run "
            f"({recorded!r} != {evidence_identity!r})"
        )

    status = artifact.get("status")
    if status not in _GROUND_TRUTH_STATUSES:
        problems.append(f"case {case_id}: invalid ground truth status {status!r}")

    recorded_identity = artifact.get("ground_truth_identity")
    recomputed = ground_truth_identity(artifact)
    if not isinstance(recorded_identity, str) or recorded_identity != recomputed:
        problems.append(
            f"case {case_id}: ground truth identity does not match the artifact content"
        )

    assessment = artifact.get("assessment")
    if not isinstance(assessment, dict):
        problems.append(f"case {case_id}: ground truth has no assessment")
    else:
        summary = assessment.get("summary")
        if not isinstance(summary, dict):
            problems.append(f"case {case_id}: ground truth assessment has no summary")
        else:
            score = summary.get("score")
            if not isinstance(score, (int, float)) or not (0 <= score <= 100):
                problems.append(
                    f"case {case_id}: impossible ground truth score {score!r} (must be 0-100)"
                )
    return problems


def validate_report(report: dict[str, Any]) -> list[str]:
    """Structural and identity checks on a serialized metrics report."""
    problems: list[str] = []
    if report.get("schema_version") != METRICS_SCHEMA_VERSION:
        problems.append("metrics report has an unknown schema version")
    if report.get("system") != SYSTEM_ID:
        problems.append("metrics report does not identify its producing system")
    for key in ("inputs", "primary_metric", "secondary_metrics", "cases"):
        if key not in report:
            problems.append(f"metrics report missing {key!r}")
    recorded = report.get("metrics_identity")
    recomputed = recompute_identity(report)
    if not isinstance(recorded, str) or recomputed is None or recorded != recomputed:
        problems.append("metrics report identity does not match its content")
    return problems


__all__ = [
    "validate_run_dir",
    "validate_ground_truth_artifact",
    "validate_report",
]
