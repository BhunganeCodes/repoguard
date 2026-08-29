"""Shared helpers for ground-truth artifact schemas.

The schemas are intentionally strict: a reviewer assessment carries only the
fields a human reviewer can truthfully record (rubric-scored criteria with
evidence citations and a pseudonymous reviewer id). Unknown top-level fields
are rejected so system results (tiers, ranks, baseline or RepoGuard scores)
can never be smuggled into a reviewer assessment.
"""

from __future__ import annotations

import re
from typing import Any

from evaluation.ground_truth._version import (
    ADJUDICATION_SCHEMA_VERSION,
    DATASET_VERSION,
    GROUND_TRUTH_SCHEMA_VERSION,
    REVIEW_SCHEMA_VERSION,
)
from evaluation.ground_truth.errors import GroundTruthError
from evaluation.scoring.rubric import CRITERIA, criterion_dimension

REVIEWER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

REVIEW_KEYS = frozenset(
    {
        "schema_version",
        "review_identity",
        "reviewer_id",
        "case_id",
        "dataset_version",
        "rubric_version",
        "evidence_identity",
        "inspected_files",
        "criteria",
        "review_time_minutes",
    }
)

DECISIONS_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "adjudicator_id",
        "contested",
        "decisions",
    }
)

CONSENSUS_KEYS = frozenset(
    {
        "schema_version",
        "ground_truth_identity",
        "dataset_version",
        "case_id",
        "name",
        "rubric_version",
        "evidence_identity",
        "status",
        "reviewers",
        "adjudication_identity",
        "provenance",
        "assessment",
    }
)


def _path_problem(path: str) -> str | None:
    """Mirror of evidence/validate.py path rules: repo-relative POSIX paths."""
    if not path:
        return "empty inspected path"
    absolute = re.compile(r"^[A-Za-z]:[\\/]|^/|\\")
    traversal = re.compile(r"(^|/)\.\.(/|$)")
    if absolute.search(path) or traversal.search(path):
        return f"inspected path is not a repository-relative POSIX path: {path!r}"
    return None


def authored_row(raw: Any) -> dict[str, Any]:
    """Convert a reviewer criterion row into an authored scoring-engine row.

    The dimension is always derived from the canonical rubric rather than
    trusted from the reviewer, keeping the engine's checks authoritative.
    """
    if not isinstance(raw, dict):
        raise GroundTruthError("criterion row is not a mapping")
    criterion_id = raw.get("criterion_id")
    if not isinstance(criterion_id, str) or criterion_id not in CRITERIA:
        raise GroundTruthError(f"unknown criterion id {criterion_id!r}")
    row = dict(raw)
    row["dimension"] = criterion_dimension(criterion_id)
    return row


def review_to_assessment(review: dict[str, Any]) -> dict[str, Any]:
    """The authored assessment dict the deterministic scoring engine consumes."""
    return {
        "schema_version": 1,
        "case_id": str(review["case_id"]),
        "rubric_version": str(review["rubric_version"]),
        "evidence_identity": str(review["evidence_identity"]),
        "criteria": [authored_row(row) for row in review["criteria"]],
    }


def rows_by_criterion(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map ``criterion_id`` to the reviewer's row (first occurrence wins)."""
    rows: dict[str, dict[str, Any]] = {}
    for row in review["criteria"]:
        if isinstance(row, dict) and isinstance(row.get("criterion_id"), str):
            rows.setdefault(row["criterion_id"], row)
    return rows


def reviewer_ids(reviews: list[dict[str, Any]]) -> list[str]:
    ids = [str(review["reviewer_id"]) for review in reviews]
    if len(set(ids)) != len(ids):
        raise GroundTruthError(f"duplicate reviewer ids: {', '.join(sorted(ids))}")
    return sorted(ids)


def validate_review_set(reviews: list[dict[str, Any]]) -> None:
    """Shared invariants across a set of independent reviews for one case."""
    if len(reviews) < 2:
        raise GroundTruthError("at least two independent reviewer assessments are required")
    for review in reviews:
        if str(review.get("dataset_version")) != DATASET_VERSION:
            raise GroundTruthError(
                f"reviewer {review.get('reviewer_id')!r} records dataset version "
                f"{review.get('dataset_version')!r}; expected {DATASET_VERSION!r}"
            )
    cases = {str(review["case_id"]) for review in reviews}
    if len(cases) != 1:
        raise GroundTruthError(f"reviews span multiple cases: {', '.join(sorted(cases))}")
    reviewer_ids(reviews)


__all__ = [
    "ADJUDICATION_SCHEMA_VERSION",
    "CONSENSUS_KEYS",
    "DATASET_VERSION",
    "DECISIONS_KEYS",
    "GROUND_TRUTH_SCHEMA_VERSION",
    "REVIEW_KEYS",
    "REVIEW_SCHEMA_VERSION",
    "REVIEWER_ID",
    "authored_row",
    "review_to_assessment",
    "reviewer_ids",
    "rows_by_criterion",
    "validate_review_set",
]
