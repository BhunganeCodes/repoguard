"""The PLAN stage: deterministic relevance planning and its validation."""

from __future__ import annotations

from repoguard_helpers import plan_rows_for_evidence
from scoring_helpers import make_evidence

from evaluation.repoguard import plan
from evaluation.repoguard.errors import RepoGuardError
from evaluation.scoring.rubric import CRITERIA

VALID = {"criteria": plan_rows_for_evidence(make_evidence())}


def test_deterministic_plan_covers_all_criteria() -> None:
    evidence = make_evidence()
    result = plan.build_deterministic_plan(evidence)
    assert set(result) == set(CRITERIA)
    for criterion_id, entry in result.items():
        assert entry["criterion_id"] == criterion_id
        assert entry["dimension"] == CRITERIA[criterion_id]["dimension"]
        assert entry["evidence_pool"], "every criterion must have a suggested evidence pool"
        assert entry["coverage"]


def test_deterministic_plan_pool_derived_from_evidence() -> None:
    evidence = make_evidence()
    result = plan.build_deterministic_plan(evidence)
    existing = {item.evidence_id for item in evidence.items}
    for entry in result.values():
        assert all(candidate in existing for candidate in entry["evidence_pool"])


def test_plan_from_model_accepts_valid_plan() -> None:
    model_plan = plan.plan_from_model(VALID, make_evidence())
    assert set(model_plan) == set(CRITERIA)
    assert model_plan == {
        row["criterion_id"]: row["relevant_evidence"] for row in VALID["criteria"]
    }


def test_plan_from_model_rejects_missing_criterion() -> None:
    rows = [
        dict(row) for row in VALID["criteria"] if row["criterion_id"] != "testing.test_presence"
    ]
    try:
        plan.plan_from_model({"criteria": rows}, make_evidence())
    except RepoGuardError as exc:
        assert "missing criterion" in str(exc)
    else:  # pragma: no cover - failure expected
        raise AssertionError("expected PlanProblem for missing criterion")


def test_plan_from_model_rejects_duplicate_criteria() -> None:
    rows = [dict(row) for row in VALID["criteria"]]
    rows[0] = dict(rows[0], criterion_id=rows[1]["criterion_id"])
    try:
        plan.plan_from_model({"criteria": rows}, make_evidence())
    except RepoGuardError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - failure expected
        raise AssertionError("expected PlanProblem for duplicate criterion")


def test_plan_from_model_rejects_nonexistent_evidence_id() -> None:
    rows = [dict(row) for row in VALID["criteria"]]
    rows[0]["relevant_evidence"] = ["does.not.exist"]
    try:
        plan.plan_from_model({"criteria": rows}, make_evidence())
    except RepoGuardError as exc:
        assert "does.not.exist" in str(exc)
    else:  # pragma: no cover - failure expected
        raise AssertionError("expected PlanProblem for nonexistent evidence id")


def test_plan_from_model_rejects_non_mapping() -> None:
    try:
        plan.plan_from_model("not a mapping", make_evidence())
    except RepoGuardError:
        pass
    else:  # pragma: no cover - failure expected
        raise AssertionError("expected PlanProblem for non-mapping plan")


def test_make_plan_record_merges_deterministic_pool_and_model_selection() -> None:
    evidence = make_evidence()
    model_plan = plan.plan_from_model(VALID, evidence)
    record = plan.make_plan_record(evidence, model_plan)
    assert len(record) == len(CRITERIA)
    entry = next(item for item in record if item["criterion_id"] == "testing.test_presence")
    expected = next(
        row["relevant_evidence"]
        for row in VALID["criteria"]
        if row["criterion_id"] == "testing.test_presence"
    )
    assert entry["evidence_pool"]
    assert entry["relevant_evidence"] == expected
    assert entry["coverage"]
