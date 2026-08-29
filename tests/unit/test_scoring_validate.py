"""Fail-closed validation rules for scoring assessments."""

from __future__ import annotations

from scoring_helpers import make_assessment

from evaluation.scoring.serialize import compose_assessment
from evaluation.scoring.validate import validate_assessment

FIRST = "architecture.project_organization"


def problems_of(assessment: dict, evidence) -> list[str]:
    return validate_assessment(assessment, evidence)


def test_valid_assessment_has_no_problems() -> None:
    assessment, evidence = make_assessment()
    assert validate_assessment(assessment, evidence) == []


def test_valid_already_scored_assessment_has_no_problems() -> None:
    assessment, evidence = make_assessment()
    scored = compose_assessment(assessment, evidence)
    assert validate_assessment(scored, evidence) == []


def test_missing_evidence_identity_rejected() -> None:
    assessment, evidence = make_assessment()
    del assessment["evidence_identity"]
    assert any("missing evidence_identity" in p for p in problems_of(assessment, evidence))


def test_tampered_evidence_identity_rejected() -> None:
    assessment, evidence = make_assessment()
    assessment["evidence_identity"] = "repoguard-evidence-v1:deadbeef"
    assert any("does not match" in p for p in problems_of(assessment, evidence))


def test_missing_rubric_version_rejected() -> None:
    assessment, evidence = make_assessment()
    del assessment["rubric_version"]
    assert any("missing rubric version" in p for p in problems_of(assessment, evidence))


def test_unsupported_rubric_version_rejected() -> None:
    assessment, evidence = make_assessment()
    assessment["rubric_version"] = "2.0"
    assert any("unsupported rubric version" in p for p in problems_of(assessment, evidence))


def test_missing_case_id_rejected() -> None:
    assessment, evidence = make_assessment()
    del assessment["case_id"]
    assert any("missing case_id" in p for p in problems_of(assessment, evidence))


def test_case_id_mismatch_with_evidence_rejected() -> None:
    assessment, evidence = make_assessment(case_id="C001")
    assessment["case_id"] = "C002"
    assert any("does not match evidence case_id" in p for p in problems_of(assessment, evidence))


def test_missing_schema_version_rejected() -> None:
    assessment, evidence = make_assessment()
    del assessment["schema_version"]
    assert any("schema_version" in p for p in problems_of(assessment, evidence))


def test_missing_criteria_list_rejected() -> None:
    assessment, evidence = make_assessment()
    del assessment["criteria"]
    assert any("missing criteria list" in p for p in problems_of(assessment, evidence))


def test_unknown_criterion_id_rejected() -> None:
    assessment, evidence = make_assessment(
        overrides={FIRST: {"criterion_id": "quality.nonexistent"}}
    )
    assert any("unknown criterion id" in p for p in problems_of(assessment, evidence))


def test_missing_criterion_rejected() -> None:
    assessment, evidence = make_assessment()
    assessment["criteria"] = assessment["criteria"][1:]
    assert any("missing required criterion" in p for p in problems_of(assessment, evidence))


def test_duplicate_criterion_rejected() -> None:
    assessment, evidence = make_assessment()
    assessment["criteria"] = assessment["criteria"] + [dict(assessment["criteria"][0])]
    assert any("duplicate criterion" in p for p in problems_of(assessment, evidence))


def test_unknown_dimension_on_criterion_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"dimension": "quality"}})
    problems = problems_of(assessment, evidence)
    assert any("dimension mismatch" in p and "quality" in p for p in problems)


def test_score_above_four_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"score": 5}})
    assert any("outside allowed range 0-4" in p for p in problems_of(assessment, evidence))


def test_negative_score_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"score": -1}})
    assert any("outside allowed range 0-4" in p for p in problems_of(assessment, evidence))


def test_non_integer_score_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"score": 2.5}})
    assert any("score must be an integer or null" in p for p in problems_of(assessment, evidence))


def test_not_found_non_zero_score_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"status": "NOT_FOUND", "score": 1}})
    assert any("outside allowed range 0-0" in p for p in problems_of(assessment, evidence))


def test_not_found_zero_score_accepted() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"status": "NOT_FOUND", "score": 0}})
    assert validate_assessment(assessment, evidence) == []


def test_uncertain_score_three_rejected() -> None:
    assessment, evidence = make_assessment(
        overrides={
            FIRST: {
                "status": "UNCERTAIN",
                "score": 3,
                "uncertainty_reason": "partial evidence",
            }
        }
    )
    assert any("outside allowed range 0-2" in p for p in problems_of(assessment, evidence))


def test_uncertain_score_two_with_reason_accepted() -> None:
    assessment, evidence = make_assessment(
        overrides={
            FIRST: {
                "status": "UNCERTAIN",
                "score": 2,
                "uncertainty_reason": "partial evidence",
            }
        }
    )
    assert validate_assessment(assessment, evidence) == []


def test_uncertain_without_reason_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"status": "UNCERTAIN", "score": 1}})
    assert any("lacks uncertainty_reason" in p for p in problems_of(assessment, evidence))


def test_uncertain_unsupported_requires_zero_score() -> None:
    assessment, evidence = make_assessment(
        overrides={
            FIRST: {
                "status": "UNCERTAIN",
                "score": 2,
                "uncertainty_reason": "unsupported claims",
                "unsupported": True,
            }
        }
    )
    assert any("unsupported requires" in p for p in problems_of(assessment, evidence))


def test_unsupported_flag_only_valid_for_uncertain() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"unsupported": True}})
    assert any(
        "unsupported only valid for UNCERTAIN" in p for p in problems_of(assessment, evidence)
    )


def test_not_applicable_without_justification_rejected() -> None:
    assessment, evidence = make_assessment(
        overrides={FIRST: {"status": "NOT_APPLICABLE", "score": None}}
    )
    assert any("lacks justification" in p for p in problems_of(assessment, evidence))


def test_not_applicable_with_score_rejected() -> None:
    assessment, evidence = make_assessment(
        overrides={
            FIRST: {
                "status": "NOT_APPLICABLE",
                "score": 0,
                "justification": "no UI surface",
            }
        }
    )
    assert any("must not carry a score" in p for p in problems_of(assessment, evidence))


def test_not_applicable_without_evidence_rejected() -> None:
    assessment, evidence = make_assessment(
        overrides={
            FIRST: {
                "status": "NOT_APPLICABLE",
                "score": None,
                "justification": "no UI surface",
                "citations": [],
            }
        }
    )
    assert any(
        "requires at least one evidence citation" in p for p in problems_of(assessment, evidence)
    )


def test_not_applicable_valid_accepted() -> None:
    assessment, evidence = make_assessment(
        overrides={
            FIRST: {
                "status": "NOT_APPLICABLE",
                "score": None,
                "justification": "no UI surface",
            }
        }
    )
    assert validate_assessment(assessment, evidence) == []


def test_citation_referencing_nonexistent_evidence_rejected() -> None:
    assessment, evidence = make_assessment(
        overrides={FIRST: {"citations": ["documentation.unicorn"]}}
    )
    assert any("nonexistent evidence" in p for p in problems_of(assessment, evidence))


def test_scored_criterion_without_citations_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"citations": []}})
    assert any(
        "requires at least one evidence citation" in p for p in problems_of(assessment, evidence)
    )


def test_invalid_status_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"status": "SCORED"}})
    assert any("invalid status" in p for p in problems_of(assessment, evidence))


def test_pending_status_allowed_by_validation() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"status": "PENDING", "score": None}})
    assert validate_assessment(assessment, evidence) == []


def test_pending_with_score_rejected() -> None:
    assessment, evidence = make_assessment(overrides={FIRST: {"status": "PENDING", "score": 2}})
    assert any("PENDING must not carry a score" in p for p in problems_of(assessment, evidence))


def test_possible_not_positive_rejected() -> None:
    all_na: dict[str, dict] = {}
    for row in make_assessment()[0]["criteria"]:
        cid = row["criterion_id"]
        all_na[cid] = {
            "status": "NOT_APPLICABLE",
            "score": None,
            "justification": "not applicable to this synthetic repository",
        }
    assessment, evidence = make_assessment(overrides=all_na)
    assert any("possible is not positive" in p for p in problems_of(assessment, evidence))


def test_wrong_dimension_aggregation_rejected() -> None:
    assessment, evidence = make_assessment()
    scored = compose_assessment(assessment, evidence)
    scored["dimensions"][0]["earned"] = scored["dimensions"][0]["earned"] + 1
    assert any(".earned does not reconcile" in p for p in problems_of(scored, evidence))


def test_summary_missing_row_rejected() -> None:
    assessment, evidence = make_assessment()
    scored = compose_assessment(assessment, evidence)
    scored["dimensions"] = scored["dimensions"][:4]
    assert any("dimensions missing row" in p for p in problems_of(scored, evidence))


def test_summary_must_reconcile() -> None:
    assessment, evidence = make_assessment()
    scored = compose_assessment(assessment, evidence)
    scored["summary"]["score"] = 99.9
    assert any("summary.score does not reconcile" in p for p in problems_of(scored, evidence))


def test_assessment_identity_must_reconcile() -> None:
    assessment, evidence = make_assessment()
    scored = compose_assessment(assessment, evidence)
    scored["assessment_identity"] = "repoguard-assessment-v1:beef"
    assert any("assessment_identity does not match" in p for p in problems_of(scored, evidence))
