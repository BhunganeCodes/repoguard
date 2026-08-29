"""Deterministic disagreement detection."""

from __future__ import annotations

from ground_truth_helpers import make_review

from evaluation.ground_truth.compare import compare
from evaluation.ground_truth.errors import GroundTruthError


def test_agreeing_reviews_need_no_discussion() -> None:
    review_a, evidence = make_review(reviewer_id="R01")
    review_b, _ = make_review(reviewer_id="R02")
    report = compare([review_a, review_b], evidence)
    assert report["needs_discussion"] is False
    assert report["contested_criteria"] == []
    assert report["aggregates"] == {"R01": 50.0, "R02": 50.0}


def test_score_difference_over_one_point_is_disputed() -> None:
    review_a, evidence = make_review(
        reviewer_id="R01",
        overrides={"maintainability.duplication": {"score": 4}},
    )
    review_b, _ = make_review(
        reviewer_id="R02",
        overrides={"maintainability.duplication": {"score": 2}},
    )
    report = compare([review_a, review_b], evidence)
    assert report["needs_discussion"] is True
    [contest] = report["contested_criteria"]
    assert contest["criterion_id"] == "maintainability.duplication"
    assert contest["kind"] == "score"
    assert contest["difference"] == 2
    assert contest["reviewers"] == {
        "R01": {"status": "FOUND", "score": 4},
        "R02": {"status": "FOUND", "score": 2},
    }
    assert report["pairwise"][0]["criterion_disagreement"] is True


def test_exactly_one_point_is_below_the_threshold() -> None:
    review_a, evidence = make_review(
        reviewer_id="R01",
        overrides={"maintainability.duplication": {"score": 3}},
    )
    review_b, _ = make_review(
        reviewer_id="R02",
        overrides={"maintainability.duplication": {"score": 2}},
    )
    report = compare([review_a, review_b], evidence)
    assert report["contested_criteria"] == []
    assert report["needs_discussion"] is False


def test_applicability_disagreement_is_disputed() -> None:
    review_a, evidence = make_review(
        reviewer_id="R01",
        overrides={
            "documentation.readme": {
                "status": "NOT_APPLICABLE",
                "score": None,
                "justification": "no readme",
            }
        },
    )
    review_b, _ = make_review(
        reviewer_id="R02",
        overrides={"documentation.readme": {"status": "FOUND", "score": 3}},
    )
    report = compare([review_a, review_b], evidence)
    [contest] = report["contested_criteria"]
    assert contest["criterion_id"] == "documentation.readme"
    assert contest["kind"] == "applicability"


def test_aggregate_disagreement_over_five_points_flags_the_case() -> None:
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
    report = compare([review_a, review_b], evidence)
    assert report["aggregates"] == {"R01": 50.0, "R02": 60.0}
    assert report["contested_criteria"] == []
    assert report["pairwise"][0]["criterion_disagreement"] is False
    assert report["pairwise"][0]["aggregate_disagreement"] is True
    assert report["needs_discussion"] is True


def test_exactly_five_point_aggregate_difference_is_below_threshold() -> None:
    drift = {
        criterion_id: {"score": 3}
        for criterion_id in (
            "architecture.project_organization",
            "architecture.separation_of_responsibilities",
            "architecture.dependency_direction",
            "architecture.coupling_and_complexity",
            "architecture.extensibility",
        )
    }
    review_a, evidence = make_review(reviewer_id="R01")
    review_b, _ = make_review(reviewer_id="R02", overrides=drift)
    report = compare([review_a, review_b], evidence)
    assert report["aggregates"]["R02"] == 55.0
    assert report["pairwise"][0]["aggregate_disagreement"] is False
    assert report["needs_discussion"] is False


def test_multiple_reviewers_are_compared_pairwise() -> None:
    review_a, evidence = make_review(
        reviewer_id="R01",
        overrides={"testing.test_presence": {"score": 4}},
    )
    review_b, _ = make_review(reviewer_id="R02")
    review_c, _ = make_review(
        reviewer_id="R03",
        overrides={"testing.test_presence": {"score": 1}},
    )
    report = compare([review_a, review_b, review_c], evidence)
    assert len(report["pairwise"]) == 3
    [contest] = report["contested_criteria"]
    assert contest["criterion_id"] == "testing.test_presence"
    assert set(map(tuple, contest["pairs"])) == {("R01", "R02"), ("R01", "R03")}
    assert report["reviewers"] == ["R01", "R02", "R03"]


def test_compare_fails_closed_on_invalid_review() -> None:
    review_a, evidence = make_review(reviewer_id="R01")
    review_b, _ = make_review(reviewer_id="R02")
    review_a["criteria"] = review_a["criteria"][:-1]
    try:
        compare([review_a, review_b], evidence)
    except GroundTruthError as exc:
        assert "invalid review" in str(exc)
    else:
        raise AssertionError("expected compare to fail closed on an invalid review")


def test_compare_requires_independent_reviewers() -> None:
    review_a, evidence = make_review(reviewer_id="R01")
    review_b, _ = make_review(reviewer_id="R01")
    try:
        compare([review_a, review_b], evidence)
    except GroundTruthError as exc:
        assert "duplicate reviewer ids" in str(exc)
    else:
        raise AssertionError("expected compare to reject duplicate reviewer ids")
