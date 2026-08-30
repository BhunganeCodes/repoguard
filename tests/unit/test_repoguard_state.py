"""RunState: the explicit stage machine of one RepoGuard run."""

from __future__ import annotations

import pytest

from evaluation.repoguard._version import STAGE_ORDER
from evaluation.repoguard.errors import RepoGuardError
from evaluation.repoguard.state import RunState


def test_advance_walks_canonical_order() -> None:
    state = RunState()
    assert state.stage == ""
    for stage in STAGE_ORDER:
        state.advance(stage, "ok", notes={"n": 1})
        assert state.stage == stage


def test_advance_records_trace() -> None:
    state = RunState()
    state.advance("load", "ok", notes={"items": 3})
    state.advance("plan", "failed", notes={"kind": "x"})
    assert len(state.trace()) == 2
    assert state.trace()[0] == {"stage": "load", "status": "ok", "notes": {"items": 3}}
    assert state.trace()[1]["status"] == "failed"


def test_advance_rejects_wrong_order() -> None:
    state = RunState()
    with pytest.raises(RepoGuardError):
        state.advance("finalize")
    state.advance("load", "ok")
    with pytest.raises(RepoGuardError):
        state.advance("load", "ok")


def test_advance_rejects_unknown_stage() -> None:
    state = RunState()
    with pytest.raises(RepoGuardError):
        state.advance("not_a_stage")


def test_is_complete_only_at_finalize() -> None:
    state = RunState()
    for stage in STAGE_ORDER[:-1]:
        state.advance(stage, "ok")
        assert not state.is_complete()
    state.advance("finalize", "ok")
    assert state.is_complete()


def test_failed_final_stage_not_complete_when_missing() -> None:
    state = RunState()
    state.advance("load", "failed", notes={"kind": "x"})
    assert not state.is_complete()
