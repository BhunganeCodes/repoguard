"""Adjudication records and final consensus artifacts.

An adjudication record captures, for every disputed criterion, the original
reviewer assessments (which are never overwritten), the adjudicator's final
decision, and the final rationale. The final consensus artifact merges the
adjudicator's decisions for disputed criteria with the reviewer agreement
for every other criterion, then runs the composed result through the same
deterministic scoring engine that scores every assessment in the project.
"""

from __future__ import annotations

from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.ground_truth._version import (
    ADJUDICATION_SCHEMA_VERSION,
    DATASET_VERSION,
    GROUND_TRUTH_SCHEMA_VERSION,
)
from evaluation.ground_truth.compare import compare, contested_criteria_ids, ordered_criteria
from evaluation.ground_truth.errors import ConsensusError
from evaluation.ground_truth.schema import (
    authored_row,
    reviewer_ids,
    rows_by_criterion,
    validate_review_set,
)
from evaluation.ground_truth.serialize import adjudication_identity, ground_truth_identity
from evaluation.ground_truth.validate import (
    validate_decisions,
    validate_record,
    validate_review,
)
from evaluation.scoring.rubric import RUBRIC_VERSION
from evaluation.scoring.serialize import compose_assessment, require_complete
from evaluation.scoring.statuses import PENDING
from evaluation.scoring.validate import validate_assessment


def build_adjudication(
    *, reviews: list[dict[str, Any]], evidence: EvidenceArtifact, decisions_data: dict[str, Any]
) -> dict[str, Any]:
    """Produce a validated adjudication record from an adjudicator's decisions.

    The original reviewer assessments are read but never modified. The
    decisions file must cover exactly the disputed criteria identified by
    :func:`compare`.
    """
    validate_review_set(reviews)
    for review in reviews:
        problems = validate_review(review, evidence)
        if problems:
            raise ConsensusError(
                f"invalid review for reviewer {review.get('reviewer_id')!r}:\n"
                + "\n".join(problems)
            )

    report = compare(reviews, evidence)
    contested = contested_criteria_ids(report)
    if not report.get("needs_discussion"):
        raise ConsensusError("reviewers do not disagree; no adjudication is required for this case")

    problems = validate_decisions(decisions_data)
    if problems:
        raise ConsensusError("invalid decisions file:\n" + "\n".join(problems))

    case_id = str(reviews[0]["case_id"])
    if decisions_data["case_id"] != case_id:
        raise ConsensusError(
            f"decisions file targets case {decisions_data['case_id']!r}; reviews target {case_id!r}"
        )

    adjudicator_id = str(decisions_data["adjudicator_id"])
    reviewers = reviewer_ids(reviews)
    if adjudicator_id in reviewers:
        raise ConsensusError(
            f"adjudicator {adjudicator_id!r} must be a third reviewer, distinct from the reviewers"
        )

    decision_rows = {row["criterion_id"]: row for row in decisions_data["decisions"]}
    missing = [c for c in contested if c not in decision_rows]
    if missing:
        raise ConsensusError(
            "decisions file is missing disputed criteria: " + ", ".join(sorted(missing))
        )
    if not decision_rows:
        raise ConsensusError("decisions file records no decisions for a disputed case")

    for criterion_id, row in decision_rows.items():
        if row.get("status") == PENDING:
            raise ConsensusError(f"decision for {criterion_id!r} must use a canonical status")
        rationale = row.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ConsensusError(f"decision for {criterion_id!r} lacks a final rationale")

    _combined_assessment(reviews, decision_rows, evidence)

    by_reviewer = rows_by_reviewer(reviews)
    decided = [c for c in ordered_criteria() if c in decision_rows]
    contested_criteria = [
        {
            "criterion_id": criterion_id,
            "original_assessments": {
                reviewer_id: _present(by_reviewer[reviewer_id].get(criterion_id) or {})
                for reviewer_id in reviewers
            },
            "decision": decision_rows[criterion_id],
            "rationale": decision_rows[criterion_id]["rationale"],
        }
        for criterion_id in decided
    ]

    record: dict[str, Any] = {
        "schema_version": ADJUDICATION_SCHEMA_VERSION,
        "adjudication_identity": "",
        "case_id": case_id,
        "adjudicator_id": adjudicator_id,
        "reviewer_ids": reviewers,
        "dataset_version": DATASET_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "evidence_identity": str(reviews[0]["evidence_identity"]),
        "contested": bool(decisions_data["contested"]),
        "contested_criteria": contested_criteria,
    }
    record["adjudication_identity"] = adjudication_identity(record)
    return record


def rows_by_reviewer(reviews: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    reviewers = reviewer_ids(reviews)
    by_id = {str(review["reviewer_id"]): review for review in reviews}
    return {reviewer_id: rows_by_criterion(by_id[reviewer_id]) for reviewer_id in reviewers}


def _present(row: dict[str, Any]) -> dict[str, Any]:
    return {"status": row.get("status"), "score": row.get("score")}


def _combined_assessment(
    reviews: list[dict[str, Any]],
    decision_rows: dict[str, dict[str, Any]],
    evidence: EvidenceArtifact,
) -> dict[str, Any]:
    """Merge reviewer rows with adjudicator decisions for scoring validation."""
    reviewers = reviewer_ids(reviews)
    by_reviewer = rows_by_reviewer(reviews)
    first = reviewers[0]
    rows: list[dict[str, Any]] = []
    for criterion_id in ordered_criteria():
        row = decision_rows.get(criterion_id)
        if row is None:
            row = by_reviewer[first][criterion_id]
        rows.append(authored_row(row))
    assessment = {
        "schema_version": 1,
        "case_id": str(reviews[0]["case_id"]),
        "rubric_version": str(reviews[0]["rubric_version"]),
        "evidence_identity": str(reviews[0]["evidence_identity"]),
        "criteria": rows,
    }
    problems = validate_assessment(assessment, evidence)
    if problems:
        raise ConsensusError(
            "adjudicator decisions fail scoring validation:\n" + "\n".join(problems)
        )
    return assessment


def validate_adjudication(
    record: dict[str, Any], reviews: list[dict[str, Any]], evidence: EvidenceArtifact
) -> list[str]:
    """Semantic validation of an adjudication record against its reviews."""
    problems: list[str] = validate_record(record, evidence)
    if problems:
        return problems

    validate_review_set(reviews)
    review_problems: list[str] = []
    for review in reviews:
        review_problems.extend(validate_review(review, evidence))
    if review_problems:
        return review_problems

    reviewers = reviewer_ids(reviews)
    case_id = str(reviews[0]["case_id"])
    if record.get("case_id") != case_id:
        problems.append(
            f"record case_id {record.get('case_id')!r} does not match reviews {case_id!r}"
        )
    if record.get("reviewer_ids") != reviewers:
        problems.append(f"record reviewer_ids {record.get('reviewer_ids')!r} do not match reviews")
    adjudicator_id = record.get("adjudicator_id")
    if adjudicator_id in reviewers:
        problems.append("adjudicator must be distinct from the reviewers")

    report = compare(reviews, evidence)
    expected = contested_criteria_ids(report)
    recorded = [e["criterion_id"] for e in record.get("contested_criteria", [])]
    if report.get("needs_discussion"):
        missing = [c for c in expected if c not in recorded]
        if missing:
            problems.append(
                "record does not adjudicate every disputed criterion: " + ", ".join(missing)
            )
        if not recorded:
            problems.append("a disputed case requires adjudicated criteria")
    elif recorded:
        problems.append("record adjudicates criteria for a case without disagreement")

    if not problems:
        decision_rows = {e["criterion_id"]: e["decision"] for e in record["contested_criteria"]}
        try:
            _combined_assessment(reviews, decision_rows, evidence)
        except ConsensusError as exc:
            problems.append(str(exc))
    return problems


def build_consensus(
    *,
    reviews: list[dict[str, Any]],
    evidence: EvidenceArtifact,
    adjudication: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the final consensus artifact from independent reviews.

    Disputed criteria are taken from the validated adjudication record; all
    other criteria keep the reviewers' shared value. Uncontested criteria
    where reviewers differ by at most one point deterministically adopt the
    value recorded by the first reviewer in reviewer-id order.
    """
    validate_review_set(reviews)
    for review in reviews:
        problems = validate_review(review, evidence)
        if problems:
            raise ConsensusError(
                f"invalid review for reviewer {review.get('reviewer_id')!r}:\n"
                + "\n".join(problems)
            )

    report = compare(reviews, evidence)

    decision_by_id: dict[str, dict[str, Any]] = {}
    adjudicator: str | None = None
    if report.get("needs_discussion"):
        if adjudication is None:
            raise ConsensusError(
                "the reviewers disagree; an adjudication record is required "
                "before a final consensus artifact can be produced"
            )
        problems = validate_adjudication(adjudication, reviews, evidence)
        if problems:
            raise ConsensusError("invalid adjudication record:\n" + "\n".join(problems))
        decision_by_id = {
            e["criterion_id"]: e["decision"] for e in adjudication["contested_criteria"]
        }
        adjudicator = str(adjudication["adjudicator_id"])
        status = "contested" if adjudication["contested"] else "consensus"
    else:
        if adjudication is not None:
            raise ConsensusError(
                "reviews agree on every criterion; an adjudication record is not applicable"
            )
        status = "consensus"

    reviewers = reviewer_ids(reviews)
    by_reviewer = rows_by_reviewer(reviews)
    first = reviewers[0]

    rows: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {}
    for criterion_id in ordered_criteria():
        if criterion_id in decision_by_id:
            rows.append(authored_row(decision_by_id[criterion_id]))
            provenance[criterion_id] = {"source": [adjudicator], "basis": "adjudicated"}
        else:
            candidate_rows = [
                by_reviewer[reviewer_id].get(criterion_id) or {} for reviewer_id in reviewers
            ]
            value_set = {(row.get("status"), row.get("score")) for row in candidate_rows}
            basis = "agreement" if len(value_set) == 1 else "tiebreak"
            source = list(reviewers) if basis == "agreement" else [first]
            rows.append(authored_row(by_reviewer[first][criterion_id]))
            provenance[criterion_id] = {"source": source, "basis": basis}

    authored = {
        "schema_version": 1,
        "case_id": str(reviews[0]["case_id"]),
        "rubric_version": str(reviews[0]["rubric_version"]),
        "evidence_identity": str(reviews[0]["evidence_identity"]),
        "criteria": rows,
    }
    problems = validate_assessment(authored, evidence)
    if problems:
        raise ConsensusError(
            "consensus assessment fails scoring validation:\n" + "\n".join(problems)
        )
    assessment = require_complete(compose_assessment(authored, evidence))

    case_id = str(reviews[0]["case_id"])
    evidence_identity = str(reviews[0]["evidence_identity"])
    artifact: dict[str, Any] = {
        "schema_version": GROUND_TRUTH_SCHEMA_VERSION,
        "ground_truth_identity": "",
        "dataset_version": DATASET_VERSION,
        "case_id": case_id,
        "name": str(assessment["name"]),
        "rubric_version": RUBRIC_VERSION,
        "evidence_identity": evidence_identity,
        "status": status,
        "reviewers": {"independent": reviewers, "adjudicator": adjudicator},
        "adjudication_identity": adjudication["adjudication_identity"] if adjudication else None,
        "provenance": {
            criterion_id: provenance[criterion_id] for criterion_id in ordered_criteria()
        },
        "assessment": assessment,
    }
    artifact["ground_truth_identity"] = ground_truth_identity(artifact)
    return artifact


__all__ = [
    "build_adjudication",
    "build_consensus",
    "validate_adjudication",
]
