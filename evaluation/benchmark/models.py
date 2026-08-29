"""Typed models for benchmark case outcomes.

An :class:`ExecutedCase` records one case of a run: whether the case
succeeded, which evaluators produced results (each with its own result
identity and score), the paired score delta, the shared evidence identity,
and any recorded failure. Scores are read from the composed evaluator
results only; they are never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Case status words. ``succeeded`` means every requested evaluator
# succeeded; a failed case still records any results that were produced.
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"


@dataclass(slots=True)
class ErrorRecord:
    """A recorded failure. Never silently converted into a score."""

    kind: str
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "details": list(self.details)}


@dataclass(slots=True)
class EvaluatorOutcome:
    """The recorded outcome of one system for one case.

    ``status`` is the evaluator's own status (``succeeded``/``failed``);
    ``score`` is only ever taken from a successful evaluator result.
    ``error_kind`` carries the evaluator's recorded failure kind when it
    failed (e.g. ``provider_error``), never an invented score.
    """

    status: str
    result_identity: str
    score: float | None
    result_path: str | None
    error_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "result_identity": self.result_identity,
            "score": self.score,
            "result_path": self.result_path,
            "error_kind": self.error_kind,
        }


@dataclass(slots=True)
class ExecutedCase:
    """One case within a benchmark run."""

    case_id: str
    status: str
    evidence_identity: str | None
    baseline: EvaluatorOutcome | None
    repoguard: EvaluatorOutcome | None
    delta: float | None
    error: ErrorRecord | None
    # Composed result artifacts (with runtime) for the report; kept as
    # objects so the results writer can render them deterministically.
    baseline_artifact: dict[str, Any] | None = None
    repoguard_artifact: dict[str, Any] | None = None
