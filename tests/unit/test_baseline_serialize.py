"""Deterministic serialization, identity separation, and redaction."""

from __future__ import annotations

from baseline_helpers import mock_valid
from scoring_helpers import make_evidence

from evaluation.baseline.pipeline import run_case
from evaluation.baseline.serialize import (
    compose_result,
    mask_secrets,
    recompute_identity,
    render_result,
    result_identity,
    sanitize_config,
)

_FIXED_AT = "2026-08-28T00:00:00Z"


def _result(requested_at: str = _FIXED_AT):
    evidence = make_evidence()
    return run_case(evidence, mock_valid(evidence), requested_at=requested_at)


def test_result_identity_separated_from_timestamps() -> None:
    assert result_identity(_result("T-1")) == result_identity(_result("T-2"))


def test_compose_result_includes_runtime_but_identity_excludes_it() -> None:
    composed = compose_result(_result())
    assert composed["runtime"]["requested_at"] == _FIXED_AT
    assert composed["result_identity"].startswith("repoguard-baseline-v1:")
    assert recompute_identity(composed) == composed["result_identity"]


def test_semantic_fields_present() -> None:
    composed = compose_result(_result())
    assert composed["system"] == "baseline"
    assert composed["status"] == "succeeded"
    assert isinstance(composed["baseline_version"], str)
    assert composed["prompt_version"] == "1.0"
    assert composed["rubric_version"] == "1.0"
    assert composed["case_id"] == "C001"
    assert composed["evidence_identity"].startswith("repoguard-evidence-v1:")
    assert composed["provider"]["name"] == "mock"
    assert composed["provider"]["model"] == "mock"
    assert composed["assessment"]["assessment_identity"].startswith("repoguard-assessment-v1:")
    assert composed["scoring"]["score"] == 50.0
    assert composed["error"] is None
    assert composed["model_response"] is None


def test_render_is_byte_deterministic() -> None:
    from copy import deepcopy

    result = _result()
    assert render_result(result) == render_result(deepcopy(result))


def test_failure_results_have_stable_identity() -> None:
    from evaluation.baseline.provider import MockProvider

    evidence = make_evidence()
    provider = MockProvider("garbage")
    first = run_case(evidence, provider, requested_at="T-1")
    second = run_case(evidence, MockProvider("garbage"), requested_at="T-2")
    assert first.status == "failed" and second.status == "failed"
    assert result_identity(first) == result_identity(second)
    composed = compose_result(first)
    assert composed["error"]["kind"] == "malformed_response"
    assert composed["model_response"] == "garbage"


def test_sanitize_config_drops_credential_keys() -> None:
    dirty: dict[str, object] = {
        "mode": "openai-compatible",
        "api_key": "sk-1",
        "nested": {"api-key": "sk-2", "Authorization": "Bearer sk-3", "ok": "fine"},
        "list": [{"secret": "sk-4", "credential": "sk-5"}, "plain"],
    }
    clean = sanitize_config(dirty)
    assert clean == {
        "mode": "openai-compatible",
        "nested": {"ok": "fine"},
        "list": [{}, "plain"],
    }


def test_mask_secrets_replaces_known_values() -> None:
    assert mask_secrets("token=abc123 end abc123", ["abc123"]) == "token=<redacted> end <redacted>"
    assert mask_secrets("nothing to hide", ["abc"]) == "nothing to hide"


def test_rendered_failure_artifact_no_secrets() -> None:
    from evaluation.baseline.pipeline import EvaluatorConfig
    from evaluation.baseline.provider import MockProvider

    evidence = make_evidence()
    result = run_case(
        evidence,
        MockProvider("garbage"),
        config=EvaluatorConfig(extra={"api_key": "sk-leak"}),
        requested_at=_FIXED_AT,
    )
    rendered = render_result(result, secrets=["sk-leak"])
    assert "sk-leak" not in rendered
