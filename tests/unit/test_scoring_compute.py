"""Deterministic scoring arithmetic: dimensions, aggregates, and identity."""

from __future__ import annotations

import pytest
import yaml
from scoring_helpers import make_assessment

from evaluation.evidence.serialize import recompute_identity
from evaluation.scoring.compute import compute_dimensions, compute_summary, parse_criterion
from evaluation.scoring.errors import ScoringError
from evaluation.scoring.serialize import compose_assessment, compose_payload, require_complete

# Three benchmark criteria used to exercise N/A normalization and rounding.
DOWNGRADE_TO_NA = {
    "architecture.project_organization": {
        "status": "NOT_APPLICABLE",
        "score": None,
        "justification": "no separate project shell in this synthetic repo",
    },
    "testing.unit_testing": {
        "status": "NOT_APPLICABLE",
        "score": None,
        "justification": "no unit-testable logic in this synthetic repo",
    },
    "documentation.readme": {
        "status": "NOT_APPLICABLE",
        "score": None,
        "justification": "no user-facing package in this synthetic repo",
    },
}


def _typed(assessment: dict) -> list:
    return [parse_criterion(row) for row in assessment["criteria"]]


def _summary_of(assessment: dict, evidence) -> dict:
    payload, _identity = compose_payload(assessment, evidence)
    summary = payload["summary"]
    assert isinstance(summary, dict)
    return summary


def test_default_assessment_scores_half() -> None:
    assessment, evidence = make_assessment()
    typed = _typed(assessment)
    dimensions = compute_dimensions(typed)
    summary = compute_summary(typed, dimensions)
    assert summary.complete is True
    assert summary.earned == 50
    assert summary.possible == 100
    assert summary.score == 50.0
    assert summary.not_applicable == []
    assert summary.pending == []
    for dimension in dimensions:
        assert dimension.earned == 10
        assert dimension.maximum == 20
        assert dimension.scored == 5
        assert dimension.status_counts == {"FOUND": 5}
    assert sum(d.earned for d in dimensions) == summary.earned


def test_na_normalization_and_dimension_totals() -> None:
    assessment, evidence = make_assessment(overrides=DOWNGRADE_TO_NA)
    scored = compose_assessment(assessment, evidence)
    dims = {row["dimension"]: row for row in scored["dimensions"]}
    assert dims["architecture"] == {
        "dimension": "architecture",
        "earned": 8,
        "maximum": 16,
        "scored": 4,
        "status_counts": {"FOUND": 4, "NOT_APPLICABLE": 1},
    }
    assert dims["testing"]["earned"] == 8
    assert dims["testing"]["maximum"] == 16
    assert dims["documentation"]["earned"] == 8
    assert dims["documentation"]["maximum"] == 16
    assert dims["maintainability"] == {
        "dimension": "maintainability",
        "earned": 10,
        "maximum": 20,
        "scored": 5,
        "status_counts": {"FOUND": 5},
    }
    summary = scored["summary"]
    assert summary["earned"] == 44
    assert summary["possible"] == 88
    assert summary["score"] == 50.0
    assert set(summary["not_applicable"]) == set(DOWNGRADE_TO_NA)


def test_rounding_to_one_decimal() -> None:
    tips = dict(DOWNGRADE_TO_NA)
    tips["dependencies.dependency_hygiene"] = {
        "status": "FOUND",
        "score": 1,
        "citations": ["dependencies.dependency_manifests"],
    }
    assessment, evidence = make_assessment(overrides=tips)
    scored = compose_assessment(assessment, evidence)
    summary = scored["summary"]
    assert summary["earned"] == 43
    assert summary["possible"] == 88
    assert summary["score"] == 48.9


def test_uncertain_score_conservative() -> None:
    assessment, evidence = make_assessment(
        overrides={
            "dependencies.supply_chain_discipline": {
                "status": "UNCERTAIN",
                "score": 1,
                "uncertainty_reason": "vendored content unchecked in sample",
            }
        }
    )
    scored = compose_assessment(assessment, evidence)
    summary = scored["summary"]
    assert summary["earned"] == 49
    assert summary["score"] == 49.0
    assert summary["uncertain"] == [
        {
            "criterion_id": "dependencies.supply_chain_discipline",
            "reason": "vendored content unchecked in sample",
        }
    ]


def test_not_found_scores_zero() -> None:
    assessment, evidence = make_assessment(
        overrides={"maintainability.duplication": {"status": "NOT_FOUND", "score": 0}}
    )
    scored = compose_assessment(assessment, evidence)
    assert scored["dimensions"][2]["earned"] == 8
    assert scored["summary"]["earned"] == 48


def test_pending_assessment_is_incomplete_without_score() -> None:
    assessment, evidence = make_assessment(
        overrides={"architecture.extensibility": {"status": "PENDING", "score": None}}
    )
    scored = compose_assessment(assessment, evidence)
    summary = scored["summary"]
    assert summary["complete"] is False
    assert summary["earned"] is None
    assert summary["score"] is None
    assert summary["pending"] == ["architecture.extensibility"]


def test_pending_assessment_cannot_be_scored() -> None:
    assessment, evidence = make_assessment(
        overrides={"architecture.extensibility": {"status": "PENDING", "score": None}}
    )
    scored = compose_assessment(assessment, evidence)
    with pytest.raises(ScoringError, match="not scoreable"):
        require_complete(scored)


def test_dimension_assessment_model_export() -> None:
    assessment, evidence = make_assessment()
    typed = _typed(assessment)
    dimensions = compute_dimensions(typed)
    rendered = [dimension.to_dict() for dimension in dimensions]
    assert len(rendered) == 5
    for row in rendered:
        assert set(row) == {"dimension", "earned", "maximum", "scored", "status_counts"}


def test_repeated_scoring_produces_identical_output() -> None:
    assessment, evidence = make_assessment(overrides=DOWNGRADE_TO_NA)
    first = compose_assessment(assessment, evidence)
    second = compose_assessment(assessment, evidence)
    assert first == second
    assert yaml.safe_dump(first, sort_keys=False) == yaml.safe_dump(second, sort_keys=False)
    assert first["assessment_identity"] == second["assessment_identity"]


def test_identity_is_stable_across_generated_at() -> None:
    assessment, evidence = make_assessment()
    first = compose_assessment(assessment, evidence)
    evidence.generated_at = "2030-01-01T00:00:00Z"
    evidence.evidence_identity = recompute_identity(evidence)
    assessment["evidence_identity"] = evidence.evidence_identity
    second = compose_assessment(assessment, evidence)
    assert first["assessment_identity"] == second["assessment_identity"]


def test_identity_changes_when_criteria_change() -> None:
    assessment, evidence = make_assessment()
    first = compose_assessment(assessment, evidence)
    assessment, _ = make_assessment(overrides={"architecture.extensibility": {"score": 3}})
    second = compose_assessment(assessment, evidence)
    assert first["assessment_identity"] != second["assessment_identity"]


def test_composed_assessment_has_all_required_sections() -> None:
    assessment, evidence = make_assessment()
    scored = compose_assessment(assessment, evidence)
    assert set(scored) == {
        "schema_version",
        "assessment_identity",
        "case_id",
        "name",
        "rubric_version",
        "evidence_identity",
        "criteria",
        "dimensions",
        "summary",
    }
    assert len(scored["criteria"]) == 25
    assert len(scored["dimensions"]) == 5
    assert scored["assessment_identity"].startswith("repoguard-assessment-v1:")
