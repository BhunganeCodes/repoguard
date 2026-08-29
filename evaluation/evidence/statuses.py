"""Canonical statuses and evidence categories.

The status set and category names are part of the evidence schema. Do not
introduce alternative spellings: downstream consumers (scoring, reporting)
depend on these exact values.
"""

from __future__ import annotations

from evaluation.evidence.errors import EvidenceError

EVIDENCE_STATUSES: frozenset[str] = frozenset({"FOUND", "NOT_FOUND", "UNCERTAIN", "NOT_APPLICABLE"})

CATEGORIES: tuple[str, ...] = (
    "architecture",
    "testing",
    "maintainability",
    "dependencies",
    "documentation",
)


def validate_status(status: str) -> None:
    if status not in EVIDENCE_STATUSES:
        raise EvidenceError(
            f"invalid evidence status {status!r}; expected one of "
            + ", ".join(sorted(EVIDENCE_STATUSES))
        )


def validate_category(category: str) -> None:
    if category not in CATEGORIES:
        raise EvidenceError(
            f"invalid evidence category {category!r}; expected one of " + ", ".join(CATEGORIES)
        )
