"""Adjudication records and final consensus artifacts."""

from __future__ import annotations

import copy

import pytest
from ground_truth_helpers import make_review

from evaluation.ground_truth.consensus import (
    build_adjudication,
    build_consensus,
    validate_adjudication,
)
from evaluation.ground_truth.errors import ConsensusError
from evaluation.ground_truth.serialize import ground_truth_identity
from evaluation.ground_truth.validate import validate_ground_truth


def _decisions(
    criterion_id: str,
    *,
    adjudicator_id: str = "R03",
    case_id: str = "C001",
    contested: bool = False,
    **row,
) -> dict:
    decision = {
        "criterion_id": criterion_id,
        "status": "FOUND",
        "score": 3,
        "citations": ["documentation.readme"],
        "rationale": "final rationale",
    }
    decision.update(row)
    return {
        "schema_version": 1,
        "case_id": case_id,
        "adjudicator_id": adjudicator_id,
        "contested": contested,
        "decisions": [decision],
    }


def _disputed_pair() -> tuple[dict, dict, dict]:
    review_a, evidence = make_review(
        reviewer_id="R01",
        overrides={"maintainability.duplication": {"score": 4}},
    )
    review_b, _ = make_review(
        reviewer_id="R02",
        overrides={"maintainability.duplication": {"score": 2}},
    )
    return review_a, review_b, evidence


def test_adjudication_record_preserves_originals_and_is_verifiable() -> None:
    review_a, review_b, evidence = _disputed_pair()
    a_before = copy.deepcopy(review_a)
    b_before = copy.deepcopy(review_b)

    record = build_adjudication(
        reviews=[review_a, review_b],
        evidence=evidence,
        decisions_data=_decisions("maintainability.duplication"),
    )

    assert review_a == a_before and review_b == b_before
    assert record["adjudicator_id"] == "R03"
    assert record["case_id"] == "C001"
    assert record["adjudication_identity"].startswith("repoguard-adjudication-v1:")
    assert len(record["contested_criteria"]) == 1
    entry = record["contested_criteria"][0]
    assert entry["criterion_id"] == "maintainability.duplication"
    assert entry["original_assessments"] == {
        "R01": {"status": "FOUND", "score": 4},
        "R02": {"status": "FOUND", "score": 2},
    }
    assert entry["decision"]["score"] == 3
    assert entry["rationale"] == "final rationale"
    assert validate_adjudication(record, [review_a, review_b], evidence) == []


def test_adjudication_requires_every_disputed_criterion() -> None:
    review_a, review_b, evidence = _disputed_pair()
    decisions = _decisions("documentation.readme")
    with pytest.raises(ConsensusError) as exc_info:
        build_adjudication(
            reviews=[review_a, review_b], evidence=evidence, decisions_data=decisions
        )
    assert "missing disputed criteria" in str(exc_info.value)


def test_adjudicator_must_be_distinct_from_reviewers() -> None:
    review_a, review_b, evidence = _disputed_pair()
    decisions = _decisions("maintainability.duplication", adjudicator_id="R02")
    with pytest.raises(ConsensusError) as exc_info:
        build_adjudication(
            reviews=[review_a, review_b], evidence=evidence, decisions_data=decisions
        )
    assert "distinct from the reviewers" in str(exc_info.value)


def test_adjudication_not_needed_when_reviews_agree() -> None:
    review_a, evidence = make_review(reviewer_id="R01")
    review_b, _ = make_review(reviewer_id="R02")
    with pytest.raises(ConsensusError) as exc_info:
        build_adjudication(
            reviews=[review_a, review_b],
            evidence=evidence,
            decisions_data=_decisions("maintainability.duplication"),
        )
    assert "no adjudication is required" in str(exc_info.value)
    with pytest.raises(ConsensusError):
        build_consensus(reviews=[review_a, review_b], evidence=evidence, adjudication={})


def test_decisions_must_target_the_right_case() -> None:
    review_a, review_b, evidence = _disputed_pair()
    decisions = _decisions("maintainability.duplication", case_id="C009")
    with pytest.raises(ConsensusError) as exc_info:
        build_adjudication(
            reviews=[review_a, review_b], evidence=evidence, decisions_data=decisions
        )
    assert "targets case" in str(exc_info.value)


def test_decision_must_use_canonical_status_and_rationale() -> None:
    review_a, review_b, evidence = _disputed_pair()
    for patch in (
        {"status": "PENDING"},
        {"rationale": ""},
        {"score": 7},
    ):
        with pytest.raises(ConsensusError):
            build_adjudication(
                reviews=[review_a, review_b],
                evidence=evidence,
                decisions_data=_decisions("maintainability.duplication", **patch),
            )


def test_consensus_without_adjudication_is_rejected_when_disputed() -> None:
    review_a, review_b, evidence = _disputed_pair()
    with pytest.raises(ConsensusError) as exc_info:
        build_consensus(reviews=[review_a, review_b], evidence=evidence)
    assert "adjudication record is required" in str(exc_info.value)


def test_consensus_artifact_uses_adjudicator_decisions_and_validates() -> None:
    review_a, review_b, evidence = _disputed_pair()
    record = build_adjudication(
        reviews=[review_a, review_b],
        evidence=evidence,
        decisions_data=_decisions("maintainability.duplication"),
    )
    artifact = build_consensus(reviews=[review_a, review_b], evidence=evidence, adjudication=record)

    assert artifact["status"] == "consensus"
    assert artifact["reviewers"] == {"independent": ["R01", "R02"], "adjudicator": "R03"}
    assert artifact["adjudication_identity"] == record["adjudication_identity"]
    assert artifact["ground_truth_identity"].startswith("repoguard-ground-truth-v1:")

    provenance = artifact["provenance"]["maintainability.duplication"]
    assert provenance == {"source": ["R03"], "basis": "adjudicated"}
    other = artifact["provenance"]["documentation.readme"]
    assert other["basis"] == "agreement"
    assert other["source"] == ["R01", "R02"]

    assert artifact["assessment"]["summary"]["score"] == 51.0
    assert validate_ground_truth(artifact, evidence) == []


def test_consensus_artifact_is_deterministic() -> None:
    review_a, review_b, evidence = _disputed_pair()
    first = build_consensus(
        reviews=[review_a, review_b],
        evidence=evidence,
        adjudication=build_adjudication(
            reviews=[review_a, review_b],
            evidence=evidence,
            decisions_data=_decisions("maintainability.duplication"),
        ),
    )
    second = build_consensus(
        reviews=[review_a, review_b],
        evidence=evidence,
        adjudication=build_adjudication(
            reviews=[review_a, review_b],
            evidence=evidence,
            decisions_data=_decisions("maintainability.duplication"),
        ),
    )
    assert first == second
    assert ground_truth_identity(first) == first["ground_truth_identity"]


def test_ground_truth_tampering_is_detected() -> None:
    review_a, review_b, evidence = _disputed_pair()
    record = build_adjudication(
        reviews=[review_a, review_b],
        evidence=evidence,
        decisions_data=_decisions("maintainability.duplication"),
    )
    artifact = build_consensus(reviews=[review_a, review_b], evidence=evidence, adjudication=record)
    assessment = artifact["assessment"]
    for row in assessment["criteria"]:
        if row["criterion_id"] == "documentation.readme":
            row["score"] = 4
            break
    problems = validate_ground_truth(artifact, evidence)
    assert problems
    assert ground_truth_identity(artifact) != artifact["ground_truth_identity"]


def test_contested_case_is_marked_contested() -> None:
    review_a, review_b, evidence = _disputed_pair()
    decisions = _decisions("maintainability.duplication", contested=True)
    record = build_adjudication(
        reviews=[review_a, review_b], evidence=evidence, decisions_data=decisions
    )
    artifact = build_consensus(reviews=[review_a, review_b], evidence=evidence, adjudication=record)
    assert artifact["status"] == "contested"


def test_aggregate_only_disagreement_is_adjudicable() -> None:
    drift = {
        criterion_id: {"score": 3}
        for criterion_id in (
            "architecture.project_organization",
            "architecture.separation_of_responsibilities",
            "architecture.dependency_direction",
            "architecture.coupling_and_complexity",
            "architecture.extensibility",
            "testing.test_presence",
            "testing.test_organization",
            "testing.unit_testing",
            "testing.integration_testing",
            "testing.failure_path_coverage",
        )
    }
    review_a, evidence = make_review(reviewer_id="R01")
    review_b, _ = make_review(reviewer_id="R02", overrides=drift)

    decisions = _decisions(
        "architecture.project_organization",
        citations=["architecture.top_level_structure"],
    )
    record = build_adjudication(
        reviews=[review_a, review_b], evidence=evidence, decisions_data=decisions
    )
    assert [e["criterion_id"] for e in record["contested_criteria"]] == [
        "architecture.project_organization"
    ]
    artifact = build_consensus(reviews=[review_a, review_b], evidence=evidence, adjudication=record)
    assert artifact["status"] == "consensus"
    assert artifact["provenance"]["architecture.project_organization"]["basis"] == "adjudicated"
    assert (
        artifact["provenance"]["architecture.separation_of_responsibilities"]["basis"] == "tiebreak"
    )
    assert artifact["provenance"]["documentation.readme"]["basis"] == "agreement"
    assert validate_ground_truth(artifact, evidence) == []


def test_reviewer_records_are_never_modified() -> None:
    review_a, review_b, evidence = _disputed_pair()
    record = build_adjudication(
        reviews=[review_a, review_b],
        evidence=evidence,
        decisions_data=_decisions("maintainability.duplication"),
    )
    build_consensus(reviews=[review_a, review_b], evidence=evidence, adjudication=record)
    duplication = "maintainability.duplication"
    assert next(r["score"] for r in review_a["criteria"] if r["criterion_id"] == duplication) == 4
    assert next(r["score"] for r in review_b["criteria"] if r["criterion_id"] == duplication) == 2


def test_adjudication_record_for_undisputed_case_is_invalid() -> None:
    review_a, evidence = make_review(reviewer_id="R01")
    review_b, _ = make_review(reviewer_id="R02")
    forged: dict = {
        "schema_version": 1,
        "adjudication_identity": "",
        "case_id": "C001",
        "adjudicator_id": "R03",
        "reviewer_ids": ["R01", "R02"],
        "dataset_version": "1.0.0",
        "rubric_version": "1.0",
        "evidence_identity": evidence.evidence_identity,
        "contested": False,
        "contested_criteria": [],
    }
    problems = validate_adjudication(forged, [review_a, review_b], evidence)
    assert problems
