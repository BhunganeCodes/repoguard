"""Typed models for baseline results.

A :class:`BaselineResult` records one single-pass LLM assessment attempt:
the produced assessment, the scoring outcome, the provider/model facts, any
failure, and runtime metadata. Semantic fields (everything except the
runtime block) drive the deterministic result identity in
:mod:`evaluation.baseline.serialize`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Result status word. Only ``succeeded`` carries a scored assessment.
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"


@dataclass(slots=True)
class ErrorRecord:
    """A recorded failure. Never silently converted to a score."""

    kind: str
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "details": list(self.details)}


@dataclass(slots=True)
class RuntimeMetadata:
    """Non-semantic, per-run facts excluded from the result identity."""

    requested_at: str
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    response_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_at": self.requested_at,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost": self.estimated_cost,
            "response_metadata": dict(self.response_metadata),
        }


@dataclass(slots=True)
class BaselineResult:
    """One baseline assessment attempt.

    ``assessment`` carries the full scoring-engine artifact (including its
    own ``assessment_identity``); ``scoring`` is its compact summary. Both
    are ``None`` on a failed run.
    """

    baseline_version: str
    prompt_version: str
    rubric_version: str
    case_id: str
    name: str
    evidence_identity: str
    status: str
    provider_name: str
    provider_model: str
    model_config: dict[str, Any]
    assessment: dict[str, Any] | None
    scoring: dict[str, Any] | None
    error: ErrorRecord | None
    model_response: str | None
    runtime: RuntimeMetadata
