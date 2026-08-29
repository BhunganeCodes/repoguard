"""Pipeline behavior: mock LLM -> assessment -> scoring, and fail-closed paths."""

from __future__ import annotations

import json

import pytest
from baseline_helpers import mock_valid, valid_assessment_text
from scoring_helpers import make_evidence

from evaluation.baseline.errors import BaselineError
from evaluation.baseline.pipeline import EvaluatorConfig, parse_assessment, run_case
from evaluation.baseline.provider import MockProvider
from evaluation.baseline.serialize import render_result, result_identity

_FIXED_AT = "2026-08-28T00:00:00Z"


def _run(evidence, provider, **kwargs):
    config = EvaluatorConfig(**kwargs.get("config", {}))
    return run_case(evidence, provider, config=config, requested_at=kwargs.get("requested_at"))


def test_happy_path_synthetic_evidence_mock_llm() -> None:
    evidence = make_evidence()
    result = _run(evidence, mock_valid(evidence), requested_at=_FIXED_AT)
    assert result.status == "succeeded"
    assert result.error is None
    assert result.model_response is None
    assert result.provider_name == "mock"
    assert result.scoring is not None
    assert result.scoring["complete"] is True
    assert result.scoring["earned"] == 50
    assert result.scoring["possible"] == 100
    assert result.scoring["score"] == 50.0
    assert result.assessment is not None
    assert result.assessment["summary"]["score"] == 50.0
    assert result.assessment["assessment_identity"].startswith("repoguard-assessment-v1:")
    assert result.model_config["mode"] == "mock"
    assert result.runtime.input_tokens == 30
    assert result.runtime.output_tokens == 60
    assert result.runtime.latency_ms is not None


def test_repeated_identical_runs_identical_semantics() -> None:
    evidence = make_evidence()
    provider = mock_valid(evidence)
    first = _run(evidence, provider, requested_at=_FIXED_AT)
    second = _run(evidence, provider, requested_at=_FIXED_AT)
    assert first.scoring == second.scoring
    assert first.assessment["assessment_identity"] == second.assessment["assessment_identity"]
    assert result_identity(first) == result_identity(second)
    assert first.error == second.error


def test_requested_at_changes_bytes_but_not_identity() -> None:
    evidence = make_evidence()
    provider = mock_valid(evidence)
    first = _run(evidence, provider, requested_at="T-A")
    second = _run(evidence, provider, requested_at="T-B")
    assert result_identity(first) == result_identity(second)
    assert render_result(first) != render_result(second)


def test_malformed_response_recorded_not_scored() -> None:
    evidence = make_evidence()
    result = _run(evidence, MockProvider("this is not an assessment"), requested_at=_FIXED_AT)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "malformed_response"
    assert result.assessment is None
    assert result.scoring is None
    assert result.model_response == "this is not an assessment"


def test_invalid_citation_fails_closed() -> None:
    evidence = make_evidence()
    text = valid_assessment_text(
        evidence,
        overrides={
            "architecture.project_organization": {"citations": ["documentation.nonexistent"]}
        },
    )
    result = _run(evidence, MockProvider(text), requested_at=_FIXED_AT)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "invalid_assessment"
    assert any("nonexistent evidence" in detail for detail in result.error.details)


def test_invalid_score_fails_closed() -> None:
    evidence = make_evidence()
    text = valid_assessment_text(
        evidence, overrides={"architecture.project_organization": {"score": 9}}
    )
    result = _run(evidence, MockProvider(text), requested_at=_FIXED_AT)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "invalid_assessment"
    assert any("outside allowed range" in detail for detail in result.error.details)


def test_missing_criterion_fails_closed() -> None:
    evidence = make_evidence()
    data = json.loads(valid_assessment_text(evidence))
    data["criteria"] = [
        row for row in data["criteria"] if row["criterion_id"] != "testing.unit_testing"
    ]
    result = _run(evidence, MockProvider(json.dumps(data)), requested_at=_FIXED_AT)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "invalid_assessment"
    assert any("missing required criterion" in detail for detail in result.error.details)


def test_pending_criteria_never_scored() -> None:
    evidence = make_evidence()
    text = valid_assessment_text(
        evidence,
        overrides={"maintainability.technical_debt": {"status": "PENDING", "score": None}},
    )
    result = _run(evidence, MockProvider(text), requested_at=_FIXED_AT)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "incomplete_assessment"
    assert "maintainability.technical_debt" in result.error.details
    assert result.scoring is None


def test_provider_failure_recorded() -> None:
    evidence = make_evidence()
    provider = MockProvider(exc=RuntimeError("connection refused"))
    result = _run(evidence, provider, requested_at=_FIXED_AT)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "provider_error"
    assert "connection refused" in result.error.message
    assert result.scoring is None


def test_evidence_identity_mismatch_fails_closed() -> None:
    evidence = make_evidence()
    evidence.evidence_identity = (
        "repoguard-evidence-v1:0000000000000000000000000000000000000000000000000000000000000000"
    )
    with pytest.raises(BaselineError, match="identity does not match"):
        _run(evidence, mock_valid(evidence), requested_at=_FIXED_AT)


def test_invalid_evidence_artifact_fails_closed() -> None:
    evidence = make_evidence()
    evidence.schema_version = 99
    with pytest.raises(BaselineError, match="invalid evidence artifact"):
        _run(evidence, mock_valid(evidence), requested_at=_FIXED_AT)


def test_parse_assessment_strips_fences_and_accepts_yaml_and_json() -> None:
    assert parse_assessment('{"case_id": "C001", "criteria": []}') == {
        "case_id": "C001",
        "criteria": [],
    }
    assert parse_assessment("case_id: C001\ncriteria: []\n") == {"case_id": "C001", "criteria": []}
    assert parse_assessment('```json\n{"case_id": "C001"}\n```') == {"case_id": "C001"}


def test_parse_assessment_rejects_scalar_text() -> None:
    from evaluation.baseline.errors import MalformedResponse

    with pytest.raises(MalformedResponse):
        parse_assessment("just prose")
    with pytest.raises(MalformedResponse):
        parse_assessment("---\nsome: [1, 2")


def test_secrets_never_reach_rendered_artifact() -> None:
    evidence = make_evidence()
    config = EvaluatorConfig(extra={"api_key": "sk-super-secret", "trace_id": "trace-123"})
    provider = MockProvider(valid_assessment_text(evidence), metadata={"trace": "sk-super-secret"})
    result = run_case(
        evidence,
        provider,
        config=config,
        requested_at=_FIXED_AT,
    )
    rendered = render_result(result, secrets=["sk-super-secret"])
    assert "sk-super-secret" not in rendered
    assert "trace-123" in rendered
