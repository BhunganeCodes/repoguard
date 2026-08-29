"""Synthetic reviewer-assessment fixtures for the ground-truth unit tests.

These helpers build small, structurally valid reviewer assessments against a
synthetic evidence artifact. They are fixtures only: they are not real
ground truth, not scored repositories, and must never be treated as
evaluation results.
"""

from __future__ import annotations

from typing import Any

from scoring_helpers import DEFAULT_CITATION, make_evidence

from evaluation.evidence.models import EvidenceArtifact
from evaluation.ground_truth._version import DATASET_VERSION
from evaluation.ground_truth.serialize import review_identity
from evaluation.scoring.rubric import RUBRIC_VERSION


def base_rows() -> list[dict[str, Any]]:
    """25 canonical rows scored FOUND 2 each, citing the synthetic evidence."""
    rows: list[dict[str, Any]] = []
    for criterion_id in DEFAULT_CITATION:
        rows.append(
            {
                "criterion_id": criterion_id,
                "status": "FOUND",
                "score": 2,
                "citations": list(DEFAULT_CITATION[criterion_id]),
                "rationale": f"reviewer reasoning for {criterion_id}",
            }
        )
    return rows


def apply_overrides(
    rows: list[dict[str, Any]], overrides: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        patch = overrides.get(row["criterion_id"])
        merged = dict(row)
        if patch:
            merged.update(patch)
        result.append(merged)
    return result


def make_review(
    *,
    case_id: str = "C001",
    reviewer_id: str = "R01",
    rows: list[dict[str, Any]] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
    inspected_files: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    evidence: EvidenceArtifact | None = None,
) -> tuple[dict[str, Any], EvidenceArtifact]:
    """A reviewer assessment (without ``review_identity``) plus its evidence."""
    if evidence is None:
        evidence = make_evidence(case_id)
    criteria = base_rows() if rows is None else list(rows)
    if overrides:
        criteria = apply_overrides(criteria, overrides)
    data: dict[str, Any] = {
        "schema_version": 1,
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "dataset_version": DATASET_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "evidence_identity": evidence.evidence_identity,
        "inspected_files": inspected_files or ["go.mod", "cmd/main.go"],
        "criteria": criteria,
    }
    if extra:
        data.update(extra)
    return data, evidence


def stamp_review(review: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a reviewer assessment with its content identity."""
    stamped = dict(review)
    stamped["review_identity"] = review_identity(stamped)
    return stamped
