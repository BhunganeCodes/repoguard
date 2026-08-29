"""Deterministic serialization, identity, and redaction of RepoGuard results."""

from __future__ import annotations

import yaml
from repoguard_helpers import staged_response
from scoring_helpers import make_evidence

from evaluation.baseline.pipeline import EvaluatorConfig
from evaluation.baseline.provider import MockProvider
from evaluation.repoguard._version import RESULT_SCHEME, SYSTEM_ID
from evaluation.repoguard.pipeline import run_case
from evaluation.repoguard.serialize import (
    compose_result,
    recompute_identity,
    render_result,
    result_identity,
    semantic_payload,
    write_result,
)


def _result():
    return run_case(
        make_evidence(),
        MockProvider(staged_response(make_evidence())),
        config=EvaluatorConfig(),
        requested_at="fixed",
    )


def test_identity_prefix_and_stability() -> None:
    result = _result()
    identity = result_identity(result)
    assert identity.startswith(f"{RESULT_SCHEME}:")
    assert result_identity(_result()) == identity


def test_identity_changes_when_semantic_payload_changes() -> None:
    base = _result()
    altered = _result()
    altered.scoring = {"complete": False, "earned": 0, "possible": 100, "score": 0.0}
    assert result_identity(altered) != result_identity(base)


def test_semantic_payload_excludes_runtime_and_identity() -> None:
    result = _result()
    payload = semantic_payload(result)
    assert "runtime" not in payload
    assert "result_identity" not in payload
    assert payload["system"] == SYSTEM_ID
    assert payload["evidence_identity"] == result.evidence_identity


def test_model_config_is_sanitized() -> None:
    result = _result()
    payload = semantic_payload(result)
    config = payload["provider"]["config"]
    assert "api_key" not in config
    assert "authorization" not in config


def test_compose_result_includes_identity_and_runtime() -> None:
    composed = compose_result(_result())
    assert composed["result_identity"].startswith(f"{RESULT_SCHEME}:")
    assert "requested_at" in composed["runtime"]
    assert composed["runtime"]["requested_at"] == "fixed"


def test_recompute_identity_matches_recorded() -> None:
    result = _result()
    composed = compose_result(result)
    assert recompute_identity(composed) == composed["result_identity"]
    assert recompute_identity("not a dict") is None


def test_render_result_is_deterministic() -> None:
    from copy import deepcopy

    result = _result()
    assert render_result(result) == render_result(deepcopy(result))


def test_render_result_masks_secrets() -> None:
    rendered = render_result(_result(), secrets=["sk-secret-token"])
    assert "sk-secret-token" not in rendered


def test_write_result_round_trip(tmp_path) -> None:
    out = tmp_path / "results" / "C001.yaml"
    result = _result()
    rendered = write_result(out, result)
    written = out.read_text(encoding="utf-8")
    assert written.splitlines(keepends=True) == rendered.splitlines(keepends=True)
    loaded = yaml.safe_load(written)
    composed = compose_result(result)
    assert loaded["result_identity"] == composed["result_identity"]
    assert loaded["assessment"]["assessment_identity"] == result.assessment["assessment_identity"]
