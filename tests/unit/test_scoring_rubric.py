"""Canonical rubric data and score bounds."""

from __future__ import annotations

import pytest

from evaluation.evidence.statuses import CATEGORIES
from evaluation.scoring.compute import normalize_score, round_half_up
from evaluation.scoring.rubric import (
    CRITERIA,
    CRITERIA_PER_DIMENSION,
    DIMENSIONS,
    MAX_CRITERION_SCORE,
    MAX_DIMENSION_SCORE,
    RUBRIC_VERSION,
    criterion_dimension,
    score_bounds_for_status,
)
from evaluation.scoring.statuses import PENDING, SCORE_BOUNDS

ALL_CRITERION_IDS = {
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
    "maintainability.code_readability",
    "maintainability.complexity",
    "maintainability.duplication",
    "maintainability.error_handling",
    "maintainability.technical_debt",
    "dependencies.dependency_hygiene",
    "dependencies.version_management",
    "dependencies.dependency_necessity",
    "dependencies.vulnerability_risk_awareness",
    "dependencies.supply_chain_discipline",
    "documentation.readme",
    "documentation.installation_and_execution",
    "documentation.architecture_documentation",
    "documentation.api_interface_documentation",
    "documentation.developer_documentation",
}


def test_rubric_version() -> None:
    assert RUBRIC_VERSION == "1.0"


def test_25_criteria_exactly() -> None:
    assert len(CRITERIA) == 25
    assert set(CRITERIA) == ALL_CRITERION_IDS


def test_five_dimensions_exactly() -> None:
    assert DIMENSIONS == CATEGORIES
    assert len(DIMENSIONS) == 5


def test_five_criteria_per_dimension() -> None:
    assert CRITERIA_PER_DIMENSION == 5
    for dimension in DIMENSIONS:
        criteria = [cid for cid in CRITERIA if criterion_dimension(cid) == dimension]
        assert len(criteria) == 5


def test_dimension_and_criterion_maxima() -> None:
    assert MAX_CRITERION_SCORE == 4
    assert MAX_DIMENSION_SCORE == 20


def test_criterion_dimension_mapping() -> None:
    for criterion_id, spec in CRITERIA.items():
        assert criterion_dimension(criterion_id) == spec["dimension"]
        assert criterion_dimension(criterion_id) in DIMENSIONS


def test_score_bounds_follow_rubric_35() -> None:
    assert score_bounds_for_status("FOUND") == (0, 4)
    assert score_bounds_for_status("UNCERTAIN") == (0, 2)
    assert score_bounds_for_status("NOT_FOUND") == (0, 0)
    assert score_bounds_for_status("NOT_APPLICABLE") is None
    assert score_bounds_for_status(PENDING) is None


def test_status_bounds_equivalent_in_statuses_module() -> None:
    for status, bounds in SCORE_BOUNDS.items():
        assert score_bounds_for_status(status) == bounds


@pytest.mark.parametrize(
    "value,expected",
    [
        (2.05, 2.1),
        (0.05, 0.1),
        (0.35, 0.4),
        (0.04, 0.0),
        (94.85, 94.9),
        (1.25, 1.3),
    ],
)
def test_round_half_up(value: float, expected: float) -> None:
    assert round_half_up(value, 1) == expected


def test_normalize_score_full_marks() -> None:
    assert normalize_score(100, 100) == 100.0
    assert normalize_score(50, 100) == 50.0
    assert normalize_score(0, 100) == 0.0


def test_normalize_score_na_normalization() -> None:
    assert normalize_score(91, 96) == 94.8
    assert normalize_score(73, 96) == 76.0
    assert normalize_score(7, 8) == 87.5


def test_normalize_score_non_positive_possible_rejected() -> None:
    with pytest.raises(Exception, match="possible"):
        normalize_score(0, 0)
