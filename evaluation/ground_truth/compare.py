"""Deterministic disagreement detection between independent reviews.

The comparison implements the discussion thresholds of docs/evaluation.md
Section 6.6 exactly:

* a criterion is disputed when the recorded scores differ by *more than one
  point*;
* a case needs discussion when the aggregate scores differ by *more than
  five points*;
* a criterion one reviewer marks ``NOT_APPLICABLE`` and another scores is
  disputed on applicability regardless of numbers.

Thresholds are configured in :mod:`evaluation.ground_truth._version` and
must not be tuned here. The comparison is deterministic: reviews are compared
in sorted reviewer-id pairs and criteria are reported in canonical rubric
order.
"""

from __future__ import annotations

from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.ground_truth._version import (
    AGGREGATE_DISAGREEMENT_POINTS,
    CRITERION_DISAGREEMENT_POINTS,
    DATASET_VERSION,
)
from evaluation.ground_truth.errors import GroundTruthError
from evaluation.ground_truth.schema import (
    review_to_assessment,
    rows_by_criterion,
    validate_review_set,
)
from evaluation.ground_truth.validate import validate_review
from evaluation.scoring.rubric import CRITERIA, RUBRIC_VERSION
from evaluation.scoring.serialize import compose_payload


def aggregate_score(review: dict[str, Any], evidence: EvidenceArtifact) -> float:
    """Normalized aggregate score produced by the deterministic scorer."""
    payload, _identity = compose_payload(review_to_assessment(review), evidence)
    summary = payload["summary"]
    if summary.get("complete") is not True:
        raise GroundTruthError(
            "cannot compare an incomplete review: pending criteria "
            + ", ".join(summary.get("pending") or [])
        )
    score = summary.get("score")
    if not isinstance(score, (int, float)):
        raise GroundTruthError("cannot compute an aggregate score for the review")
    return float(score)


def _criterion_comparison(
    first: tuple[str, dict[str, Any]], second: tuple[str, dict[str, Any]]
) -> tuple[bool, str | None, int | None]:
    """``(disputed, kind, difference)`` for one criterion across two reviewers."""
    first_id, first_row = first
    second_id, second_row = second
    first_status = first_row.get("status")
    second_status = second_row.get("status")
    first_na = first_status == "NOT_APPLICABLE"
    second_na = second_status == "NOT_APPLICABLE"

    if first_na and second_na:
        return False, None, None
    if first_na != second_na:
        return True, "applicability", None

    first_score = first_row.get("score")
    second_score = second_row.get("score")
    if not isinstance(first_score, int) or not isinstance(second_score, int):
        return True, "score", None
    difference = abs(first_score - second_score)
    return difference > CRITERION_DISAGREEMENT_POINTS, "score", difference


def compare(reviews: list[dict[str, Any]], evidence: EvidenceArtifact) -> dict[str, Any]:
    """Compare ``len(reviews) >= 2`` independent reviews and flag disputes."""
    validate_review_set(reviews)
    for review in reviews:
        problems = validate_review(review, evidence)
        if problems:
            raise GroundTruthError(
                f"invalid review for reviewer {review.get('reviewer_id')!r}:\n"
                + "\n".join(problems)
            )

    reviewers = sorted(str(review["reviewer_id"]) for review in reviews)
    by_id = {str(review["reviewer_id"]): review for review in reviews}
    rows = {reviewer_id: rows_by_criterion(by_id[reviewer_id]) for reviewer_id in reviewers}

    aggregates = {
        reviewer_id: aggregate_score(by_id[reviewer_id], evidence) for reviewer_id in reviewers
    }

    contested: dict[str, dict[str, Any]] = {}
    pairwise: list[dict[str, Any]] = []
    pairs = [
        (reviewers[i], reviewers[j])
        for i in range(len(reviewers))
        for j in range(i + 1, len(reviewers))
    ]

    for first, second in pairs:
        pair_contested: list[dict[str, Any]] = []
        status_notes: list[dict[str, Any]] = []
        for criterion_id in ordered_criteria():
            first_row = rows[first].get(criterion_id) or {}
            second_row = rows[second].get(criterion_id) or {}
            disputed, kind, difference = _criterion_comparison(
                (first, first_row), (second, second_row)
            )
            if kind == "score":
                first_status = first_row.get("status")
                second_status = second_row.get("status")
                if first_status != second_status and not disputed:
                    status_notes.append(
                        {
                            "criterion_id": criterion_id,
                            "reviewers": {first: first_status, second: second_status},
                        }
                    )
            if disputed:
                entry = contested.setdefault(
                    criterion_id,
                    {
                        "criterion_id": criterion_id,
                        "kind": kind,
                        "difference": difference,
                        "reviewers": {},
                        "pairs": [],
                    },
                )
                entry["reviewers"][first] = _present(first_row)
                entry["reviewers"][second] = _present(second_row)
                entry["pairs"].append([first, second])
                pair_contested.append(
                    {
                        "criterion_id": criterion_id,
                        "kind": kind,
                        "difference": difference,
                        "reviewers": {
                            first: _present(first_row),
                            second: _present(second_row),
                        },
                    }
                )
        aggregate_difference = round(abs(aggregates[first] - aggregates[second]), 1)
        pairwise.append(
            {
                "pair": [first, second],
                "aggregate": {first: aggregates[first], second: aggregates[second]},
                "aggregate_difference": aggregate_difference,
                "criterion_disagreement": bool(pair_contested),
                "aggregate_disagreement": aggregate_difference > AGGREGATE_DISAGREEMENT_POINTS,
                "contested_criteria": pair_contested,
                "status_notes": status_notes,
            }
        )

    case_id = str(reviews[0]["case_id"])
    return {
        "schema_version": 1,
        "case_id": case_id,
        "dataset_version": DATASET_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "evidence_identity": str(reviews[0]["evidence_identity"]),
        "reviewers": reviewers,
        "aggregates": aggregates,
        "thresholds": {
            "criterion_score": {"dispute_when_more_than": CRITERION_DISAGREEMENT_POINTS},
            "aggregate_score": {"discussion_when_more_than": AGGREGATE_DISAGREEMENT_POINTS},
        },
        "pairwise": pairwise,
        "contested_criteria": [
            contested[criterion_id]
            for criterion_id in ordered_criteria()
            if criterion_id in contested
        ],
        "needs_discussion": any(
            pair["criterion_disagreement"] or pair["aggregate_disagreement"] for pair in pairwise
        ),
    }


def ordered_criteria() -> list[str]:
    """Canonical rubric criterion order used for deterministic reporting."""
    return list(CRITERIA)


def _present(row: dict[str, Any]) -> dict[str, Any]:
    return {"status": row.get("status"), "score": row.get("score")}


def contested_criteria_ids(report: dict[str, Any]) -> list[str]:
    return [entry["criterion_id"] for entry in report.get("contested_criteria", [])]


__all__ = [
    "aggregate_score",
    "compare",
    "contested_criteria_ids",
    "ordered_criteria",
]
