"""Typed models for metric values and consumed run/ground-truth records.

A metric is represented as a :class:`MetricValue` with one of three states:
``available`` (computed from recorded data), ``unavailable`` (the data this
run would require was not recorded), or ``pending`` (the evaluation protocol
does not yet define the input structure needed). Missing data is never
replaced by an estimate or a fabricated default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Metric value states.
STATE_AVAILABLE = "available"
STATE_PENDING = "pending"
STATE_UNAVAILABLE = "unavailable"

# Evaluator outcome status words used in the report (mirrors the benchmark
# runner's vocabulary).
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

# A system that was not requested/enabled for a case.
STATUS_NOT_PRESENT = "not_present"


@dataclass(slots=True)
class MetricValue:
    """One measurement or an explicit missing/undefined representation.

    ``value`` is only ever a recorded, computed number; it is ``None`` for
    pending and unavailable states. ``covered`` is the number of measurements
    that contributed (when some are missing, the rest are reported as-is).
    """

    state: str
    value: float | int | None = None
    unit: str | None = None
    covered: int | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "value": self.value,
            "unit": self.unit,
            "covered": self.covered,
            "note": self.note,
        }


@dataclass(slots=True)
class SystemCaseRecord:
    """What is known about one system's outcome for one case.

    Scores and runtime facts are copied from the recorded result artifact
    only; nothing is estimated or derived from other cases.
    """

    case_id: str
    status: str
    score: float | None
    result_identity: str | None
    error_kind: str | None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "score": self.score,
            "result_identity": self.result_identity,
            "error_kind": self.error_kind,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost": self.estimated_cost,
            "citations": list(self.citations),
        }


@dataclass(slots=True)
class GroundTruthCase:
    """The consensus (or contested) ground-truth score for one case."""

    case_id: str
    status: str
    score: float | None
    identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "score": self.score,
            "identity": self.identity,
        }


def pending(kind: str, note: str) -> MetricValue:
    """A metric the protocol does not yet define operably."""
    return MetricValue(STATE_PENDING, None, note=note)


def unavailable(kind: str, note: str) -> MetricValue:
    """A metric whose input data was not recorded for this run."""
    return MetricValue(STATE_UNAVAILABLE, None, note=note)
