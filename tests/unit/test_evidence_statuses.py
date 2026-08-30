"""Canonical status and category validation tests."""

from __future__ import annotations

import pytest

from evaluation.evidence.errors import EvidenceError
from evaluation.evidence.statuses import (
    CATEGORIES,
    EVIDENCE_STATUSES,
    validate_category,
    validate_status,
)


def test_canonical_status_set() -> None:
    assert EVIDENCE_STATUSES == {"FOUND", "NOT_FOUND", "UNCERTAIN", "NOT_APPLICABLE"}


def test_canonical_categories() -> None:
    assert CATEGORIES == (
        "architecture",
        "testing",
        "maintainability",
        "dependencies",
        "documentation",
    )


@pytest.mark.parametrize("status", ["FOUND", "NOT_FOUND", "UNCERTAIN", "NOT_APPLICABLE"])
def test_valid_statuses_accepted(status: str) -> None:
    validate_status(status)


@pytest.mark.parametrize("category", CATEGORIES)
def test_valid_categories_accepted(category: str) -> None:
    validate_category(category)


@pytest.mark.parametrize("status", ["found", "MISSING", "FOUND ", "", "Scored"])
def test_invalid_statuses_rejected(status: str) -> None:
    with pytest.raises(EvidenceError):
        validate_status(status)


@pytest.mark.parametrize("category", ["Architecture", "tests", "", "score"])
def test_invalid_categories_rejected(category: str) -> None:
    with pytest.raises(EvidenceError):
        validate_category(category)
