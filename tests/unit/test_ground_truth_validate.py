"""Reviewer-assessment validation (fail closed)."""

from __future__ import annotations

from ground_truth_helpers import base_rows, make_review, stamp_review
from scoring_helpers import make_evidence

from evaluation.ground_truth.validate import validate_review


def _problems(review, evidence=None):
    return validate_review(review, evidence or make_evidence())


def test_valid_review_has_no_problems() -> None:
    review, evidence = make_review()
    assert _problems(review, evidence) == []


def test_review_identity_checks_out_and_tampering_is_detected() -> None:
    review, evidence = make_review()
    stamped = stamp_review(review)
    assert _problems(stamped, evidence) == []

    stamped["criteria"][0]["score"] = 4
    problems = _problems(stamped, evidence)
    assert ["review_identity does not match recomputed content"][0] in problems


def test_citation_of_nonexistent_evidence_is_rejected() -> None:
    review, evidence = make_review(
        overrides={
            "documentation.readme": {
                "citations": ["documentation.non_existent_item"],
            }
        }
    )
    problems = _problems(review, evidence)
    assert any("nonexistent evidence" in p for p in problems)


def test_missing_criterion_is_rejected() -> None:
    rows = base_rows()[1:]
    review, evidence = make_review(rows=rows)
    problems = _problems(review, evidence)
    assert any("missing required criterion" in p for p in problems)


def test_duplicate_criterion_is_rejected() -> None:
    rows = base_rows()
    rows.append(dict(rows[0], rationale="again"))
    review, evidence = make_review(rows=rows)
    problems = _problems(review, evidence)
    assert any("duplicate criterion" in p for p in problems)


def test_score_outside_status_bounds_is_rejected() -> None:
    review, evidence = make_review(overrides={"maintainability.duplication": {"score": 5}})
    problems = _problems(review, evidence)
    assert any("outside allowed range" in p for p in problems)


def test_pending_is_not_a_canonical_reviewer_status() -> None:
    review, evidence = make_review(overrides={"documentation.readme": {"status": "PENDING"}})
    problems = _problems(review, evidence)
    assert any("PENDING" in p and "not a" in p for p in problems)


def test_invalid_status_is_rejected() -> None:
    review, evidence = make_review(
        overrides={"documentation.readme": {"status": "BOGUS", "score": 2}}
    )
    problems = _problems(review, evidence)
    assert any("BOGUS" in p for p in problems)


def test_unknown_fields_are_rejected() -> None:
    review, evidence = make_review(extra={"repoguard_score": 62.5, "tier": "good", "rank": 7})
    for key in ("repoguard_score", "tier", "rank"):
        problems = _problems(review, evidence)
        assert any(f"unexpected field {key!r}" in p for p in problems)
        review.pop(key)


def test_pseudonymous_reviewer_id_is_enforced() -> None:
    review, evidence = make_review(reviewer_id="Jane Doe")
    assert any("pseudonymous" in p for p in _problems(review, evidence))


def test_dataset_version_must_be_frozen() -> None:
    review, evidence = make_review(extra={"dataset_version": "9.9.9"})
    assert any("dataset version" in p for p in _problems(review, evidence))


def test_evidence_identity_must_match() -> None:
    review, evidence = make_review()
    other = make_evidence(case_id="C002")
    problems = _problems(review, other)
    assert any("evidence identity does not match" in p for p in problems)


def test_rubric_version_must_be_supported() -> None:
    review, evidence = make_review(extra={"rubric_version": "9.9"})
    assert any("rubric version" in p for p in _problems(review, evidence))


def test_inspected_files_must_be_repository_relative() -> None:
    for bad in ("C:/repo/main.go", "repo/../../etc", "sub\\dir"):
        review, evidence = make_review(inspected_files=[bad])
        assert any("inspected path" in p for p in _problems(review, evidence))


def test_not_applicable_requires_justification_and_citations() -> None:
    review, evidence = make_review(
        overrides={"documentation.readme": {"status": "NOT_APPLICABLE", "score": None}}
    )
    problems = _problems(review, evidence)
    assert any("NOT_APPLICABLE lacks justification" in p for p in problems)

    review, evidence = make_review(
        overrides={
            "documentation.readme": {
                "status": "NOT_APPLICABLE",
                "score": None,
                "justification": "no README exists",
            }
        }
    )
    assert _problems(review, evidence) == []


def test_uncertain_requires_reason_and_bounds() -> None:
    review, evidence = make_review(
        overrides={"documentation.readme": {"status": "UNCERTAIN", "score": 3}}
    )
    problems = _problems(review, evidence)
    assert any("outside allowed range" in p for p in problems)

    review, evidence = make_review(
        overrides={
            "documentation.readme": {
                "status": "UNCERTAIN",
                "score": 1,
                "uncertainty_reason": "partial evidence",
            }
        }
    )
    assert _problems(review, evidence) == []


def test_unsupported_only_for_uncertain_and_zero() -> None:
    review, evidence = make_review(
        overrides={"documentation.readme": {"unsupported": True, "status": "FOUND"}}
    )
    assert any("unsupported only valid for UNCERTAIN" in p for p in _problems(review, evidence))

    review, evidence = make_review(
        overrides={
            "documentation.readme": {
                "status": "UNCERTAIN",
                "score": 1,
                "uncertainty_reason": "reason",
                "unsupported": True,
            }
        }
    )
    assert any(
        "unsupported requires an UNCERTAIN score of 0" in p for p in _problems(review, evidence)
    )


def test_non_yaml_inputs_fail_closed() -> None:
    assert _problems([]) != []
    assert _problems("not a review") != []
