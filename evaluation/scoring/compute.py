"""Deterministic scoring computations (rubric Section 6).

This module contains the exact arithmetic of the canonical rubric:

* dimension score = sum of the scores of its applicable criteria;
* ``earned`` = sum of all five dimension scores;
* ``possible`` = 100 - (4 x number of NOT_APPLICABLE criteria);
* ``score`` = (earned / possible) x 100, rounded to one decimal (0.05 up).

Criteria whose status is ``PENDING`` never contribute to any number; the
engine refuses to score an assessment that is not complete.
"""

from __future__ import annotations

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from evaluation.scoring.errors import ScoringError
from evaluation.scoring.models import CriterionAssessment, DimensionAssessment, ScoringSummary
from evaluation.scoring.rubric import (
    CRITERIA,
    DIMENSIONS,
    MAX_CRITERION_SCORE,
    MAX_DIMENSION_SCORE,
    criterion_dimension,
)
from evaluation.scoring.statuses import PENDING, SCOREABLE_STATUSES


def round_half_up(value: float, digits: int = 1) -> float:
    """Round a float to ``digits`` decimals, rounding ties away from zero.

    Floats are round-tripped through their shortest string form first so
    that ``round_half_up(2.05, 1) == 2.1`` as a reader of the number would
    expect, rather than rounding the float's exact binary representation.
    """
    decimal_value = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    quantum = Decimal(1).scaleb(-digits)
    return float(decimal_value.quantize(quantum, rounding=ROUND_HALF_UP))


def normalize_score(earned: int, possible: int, digits: int = 1) -> float:
    """``earned / possible * 100`` rounded to ``digits`` decimals (0.05 up).

    Uses exact decimal arithmetic on the integer numerator/denominator so
    the rounded value is exact and reproducible.
    """
    if possible <= 0:
        raise ScoringError(f"possible score must be positive, got {possible}")
    if earned < 0:
        raise ScoringError(f"earned score must be non-negative, got {earned}")
    quantum = Decimal(1).scaleb(-digits)
    exact = Decimal(earned) * Decimal(100) / Decimal(possible)
    return float(exact.quantize(quantum, rounding=ROUND_HALF_UP))


def parse_criterion(raw: Any) -> CriterionAssessment:
    """Strictly build a :class:`CriterionAssessment` from a raw mapping.

    Callers must validate first; this parser additionally guards against
    structurally invalid content so the scorer can never misaggregate.
    """
    if not isinstance(raw, dict):
        raise ScoringError("criterion is not a mapping")

    def _opt_str(key: str) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ScoringError(f"{key} must be a string")
        return value

    criterion_id = raw.get("criterion_id")
    if not isinstance(criterion_id, str) or not criterion_id:
        raise ScoringError("missing criterion_id")
    if criterion_id not in CRITERIA:
        raise ScoringError(f"unknown criterion id {criterion_id!r}")

    dimension = raw.get("dimension")
    if not isinstance(dimension, str) or not dimension:
        raise ScoringError("missing dimension")
    if dimension != criterion_dimension(criterion_id):
        raise ScoringError(f"dimension mismatch for {criterion_id}: recorded {dimension!r}")

    status = raw.get("status")
    if not isinstance(status, str) or not status:
        raise ScoringError("missing status")

    score = raw.get("score")
    if score is not None and (not isinstance(score, int) or isinstance(score, bool)):
        raise ScoringError(f"score must be an integer or null, got {score!r}")

    citations_raw = raw.get("citations", [])
    if not isinstance(citations_raw, list) or not all(isinstance(c, str) for c in citations_raw):
        raise ScoringError("citations must be a list of evidence ids")
    citations = list(citations_raw)

    justification = _opt_str("justification")
    uncertainty_reason = _opt_str("uncertainty_reason")
    rationale = _opt_str("rationale")

    unsupported = raw.get("unsupported")
    if unsupported is not None and not isinstance(unsupported, bool):
        raise ScoringError("unsupported must be a boolean")

    return CriterionAssessment(
        criterion_id=criterion_id,
        dimension=dimension,
        status=status,
        score=score,
        citations=citations,
        justification=justification,
        uncertainty_reason=uncertainty_reason,
        unsupported=unsupported,
        rationale=rationale,
    )


def compute_dimensions(criteria: list[CriterionAssessment]) -> list[DimensionAssessment]:
    """Per-dimension totals (rubric Section 6.1), in canonical order."""
    result: list[DimensionAssessment] = []
    for dimension in DIMENSIONS:
        rows = [c for c in criteria if c.dimension == dimension]
        applicable = [c for c in rows if c.status in SCOREABLE_STATUSES]
        earned = sum(c.score for c in applicable if c.score is not None)
        not_applicable = sum(1 for c in rows if c.status == "NOT_APPLICABLE")
        maximum = MAX_DIMENSION_SCORE - MAX_CRITERION_SCORE * not_applicable
        status_counts = dict(Counter(c.status for c in rows))
        result.append(
            DimensionAssessment(
                dimension=dimension,
                earned=earned,
                maximum=maximum,
                scored=len(applicable),
                status_counts=status_counts,
            )
        )
    return result


def compute_summary(
    criteria: list[CriterionAssessment],
    dimensions: list[DimensionAssessment],
) -> ScoringSummary:
    """Aggregate (rubric Section 6.2).

    ``complete`` is False as soon as any criterion is ``PENDING``. An
    incomplete assessment carries no ``earned`` or ``score``: the engine
    never invents a number for criteria that have not been assessed.
    """
    earned = sum(dimension.earned for dimension in dimensions)
    not_applicable = [c.criterion_id for c in criteria if c.status == "NOT_APPLICABLE"]
    pending = [c.criterion_id for c in criteria if c.status == PENDING]
    uncertain = [
        {"criterion_id": c.criterion_id, "reason": c.uncertainty_reason or ""}
        for c in criteria
        if c.status == "UNCERTAIN"
    ]
    possible = 100 - MAX_CRITERION_SCORE * len(not_applicable)
    complete = not pending
    if complete:
        score = normalize_score(earned, possible)
        final_earned: int | None = earned
    else:
        score = None
        final_earned = None
    return ScoringSummary(
        complete=complete,
        earned=final_earned,
        possible=possible,
        score=score,
        not_applicable=not_applicable,
        uncertain=uncertain,
        pending=pending,
    )
