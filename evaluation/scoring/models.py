"""Typed models for the deterministic scoring subsystem.

* :class:`CriterionAssessment` - one authored/assessed criterion row
* :class:`DimensionAssessment` - computed totals for one dimension
* :class:`ScoringSummary` - computed aggregate for the repository
* :class:`RepositoryAssessment` - the structured assessment artifact

Criteria are authored (by a human or, later, an LLM); dimensions, summary,
and the artifact identity are computed deterministically by the scorer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CriterionAssessment:
    """One criterion row: status, score (where applicable), and citations."""

    criterion_id: str
    dimension: str
    status: str
    score: int | None
    citations: list[str] = field(default_factory=list)
    justification: str | None = None
    uncertainty_reason: str | None = None
    unsupported: bool | None = None
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "criterion_id": self.criterion_id,
            "dimension": self.dimension,
            "status": self.status,
            "score": self.score,
            "citations": list(self.citations),
        }
        if self.justification is not None:
            data["justification"] = self.justification
        if self.uncertainty_reason is not None:
            data["uncertainty_reason"] = self.uncertainty_reason
        if self.unsupported is not None:
            data["unsupported"] = self.unsupported
        if self.rationale is not None:
            data["rationale"] = self.rationale
        return data


@dataclass(slots=True)
class DimensionAssessment:
    """Computed per-dimension totals (rubric Section 6.1)."""

    dimension: str
    earned: int
    maximum: int
    scored: int
    status_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "earned": self.earned,
            "maximum": self.maximum,
            "scored": self.scored,
            "status_counts": dict(self.status_counts),
        }


@dataclass(slots=True)
class ScoringSummary:
    """Computed aggregate (rubric Section 6.2)."""

    complete: bool
    earned: int | None
    possible: int
    score: float | None
    not_applicable: list[str] = field(default_factory=list)
    uncertain: list[dict[str, str]] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "earned": self.earned,
            "possible": self.possible,
            "score": self.score,
            "not_applicable": list(self.not_applicable),
            "uncertain": [
                {"criterion_id": row["criterion_id"], "reason": row["reason"]}
                for row in self.uncertain
            ],
            "pending": list(self.pending),
        }


@dataclass(slots=True)
class RepositoryAssessment:
    """Structured assessment artifact produced by the scoring engine."""

    schema_version: int
    assessment_identity: str
    case_id: str
    name: str
    rubric_version: str
    evidence_identity: str
    criteria: list[CriterionAssessment] = field(default_factory=list)
    dimensions: list[DimensionAssessment] = field(default_factory=list)
    summary: ScoringSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "assessment_identity": self.assessment_identity,
            "case_id": self.case_id,
            "name": self.name,
            "rubric_version": self.rubric_version,
            "evidence_identity": self.evidence_identity,
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
        }
        if self.summary is not None:
            data["summary"] = self.summary.to_dict()
        return data
