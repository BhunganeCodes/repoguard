"""The RepoGuard workflow state machine.

RepoGuard runs exactly five explicit, inspectable stages in a fixed order
(docs/repoguard.md, "Workflow"):

    LOAD -> PLAN -> ASSESS -> CROSS-CHECK -> FINALIZE

:class:`RunState` is a small accumulator: it records the current stage, the
transition trace, and the per-stage artifacts produced so far. It carries no
runtime metadata (timestamps, latency, token counts live elsewhere), so two
identical runs produce identical states and identical serialized output.

The machine is deliberately not a general-purpose agent framework: stages are
fixed, transitions are enforced, and a stage may only ever consume the
state left by the previous stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evaluation.repoguard._version import STAGE_ORDER
from evaluation.repoguard.errors import RepoGuardError

_NEXT: dict[str, str] = {
    stage: STAGE_ORDER[index + 1] for index, stage in enumerate(STAGE_ORDER[:-1])
}


@dataclass(slots=True)
class StageTrace:
    """One recorded stage transition."""

    stage: str
    status: str  # "ok" or "failed"
    notes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "status": self.status, "notes": dict(self.notes or {})}


@dataclass(slots=True)
class RunState:
    """Accumulated RepoGuard workflow state (no runtime metadata)."""

    stage: str = ""
    traces: list[StageTrace] = field(default_factory=list)
    plan_record: list[dict[str, Any]] = field(default_factory=list)
    authored: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    model_reported: list[dict[str, Any]] = field(default_factory=list)
    final_rows: list[dict[str, Any]] = field(default_factory=list)
    assessment: dict[str, Any] | None = None

    def advance(self, stage: str, status: str = "ok", notes: dict[str, Any] | None = None) -> None:
        """Transition to ``stage``, enforcing the fixed workflow order."""
        if stage not in STAGE_ORDER:
            raise RepoGuardError(f"unknown workflow stage {stage!r}")
        if self.stage:
            expected = _NEXT.get(self.stage)
            if expected != stage:
                raise RepoGuardError(
                    f"invalid stage transition {self.stage!r} -> {stage!r}; expected {expected!r}"
                )
        elif stage != STAGE_ORDER[0]:
            raise RepoGuardError(f"workflow must begin with {STAGE_ORDER[0]!r}, not {stage!r}")
        self.stage = stage
        self.traces.append(StageTrace(stage=stage, status=status, notes=notes))

    def is_complete(self) -> bool:
        return self.stage == STAGE_ORDER[-1]

    def trace(self) -> list[dict[str, Any]]:
        return [trace.to_dict() for trace in self.traces]
