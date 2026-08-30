"""The RepoGuard orchestrator: run_case end-to-end (mock provider only)."""

from __future__ import annotations

from dataclasses import replace

from repoguard_helpers import assert_stage_order, evidence_with_statuses, staged_response
from scoring_helpers import make_evidence

from evaluation.baseline.pipeline import EvaluatorConfig
from evaluation.baseline.provider import MockProvider
from evaluation.repoguard._version import STAGE_ORDER, __version__
from evaluation.repoguard.models import STATUS_FAILED, STATUS_SUCCEEDED
from evaluation.repoguard.pipeline import (
    FAIL_ASSESSMENT,
    FAIL_CROSS_CHECK,
    FAIL_EVIDENCE,
    FAIL_INCOMPLETE,
    FAIL_MALFORMED,
    FAIL_PLAN,
    FAIL_PROVIDER,
    run_case,
)
from evaluation.repoguard.prompts import PROMPT_VERSION

_NON_FOUND = "testing.integration_e2e_indicators"


def _run(*, evidence=None, text=None, provider=None, requested_at=None, **kw):
    evidence = evidence or make_evidence()
    if provider is None:
        resp = text or staged_response(evidence, **kw)
        provider = MockProvider(resp, input_tokens=20, output_tokens=80)
    return run_case(evidence, provider, config=EvaluatorConfig(), requested_at=requested_at)


def test_run_succeeds_with_clean_staged_response() -> None:
    result = _run()
    assert result.status == STATUS_SUCCEEDED
    assert result.error is None
    assert result.assessment is not None
    assert result.scoring["score"] == 50.0
    assert result.repoguard_version == __version__
    assert result.prompt_version == PROMPT_VERSION
    assert result.case_id == "C001"


def test_run_records_full_stage_trace() -> None:
    result = _run()
    assert_stage_order(result.process)
    assert [trace["stage"] for trace in result.process.stages] == list(STAGE_ORDER)


def test_run_records_plan_and_cross_check_in_process() -> None:
    result = _run()
    assert len(result.process.plan) == 25
    assert "findings" in result.process.cross_check
    assert "model_reported" in result.process.cross_check


def test_run_invalid_evidence_fails_fast() -> None:
    empty = replace(make_evidence(), items=[])
    result = _run(evidence=empty, text="{}")
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_EVIDENCE
    assert result.process.stages[0]["stage"] == "load"
    assert result.process.stages[0]["status"] == "failed"


def test_run_provider_failure_records_no_response() -> None:
    class FailingProvider(MockProvider):
        def generate(self, request):
            raise RuntimeError("boom")

    result = _run(provider=FailingProvider("ignored"))
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_PROVIDER
    assert result.model_response is None
    assert "boom" in result.error.message


def test_run_malformed_json_fails() -> None:
    result = _run(text="this is not json")
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_MALFORMED


def test_run_missing_sections_fails() -> None:
    result = _run(text='{"foo": 1}')
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_MALFORMED


def test_run_invalid_plan_fails() -> None:
    evidence = make_evidence()
    result = _run(evidence=evidence, plan={"criteria": []})
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_PLAN


def test_run_invalid_citations_fail_closed() -> None:
    evidence = make_evidence()
    result = _run(
        evidence=evidence,
        criteria=[
            {
                "criterion_id": "architecture.project_organization",
                "dimension": "architecture",
                "status": "FOUND",
                "score": 3,
                "citations": ["does.not.exist"],
            }
        ],
    )
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_ASSESSMENT
    assert result.error.details


def test_run_invalid_cross_check_fails() -> None:
    result = _run(cross_check={"findings": "oops"})
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_CROSS_CHECK


def test_run_incomplete_pending_fails() -> None:
    evidence = make_evidence()
    result = _run(
        evidence=evidence,
        overrides={
            "testing.test_presence": {
                "status": "PENDING",
                "score": None,
                "citations": [],
            }
        },
    )
    assert result.status == STATUS_FAILED
    assert result.error.kind == FAIL_INCOMPLETE
    assert "PENDING" in result.error.message or "pending" in result.error.message


def test_run_contradiction_is_downgraded_not_failed() -> None:
    evidence = evidence_with_statuses({_NON_FOUND: "NOT_FOUND"})
    result = _run(
        evidence=evidence,
        overrides={
            "testing.integration_testing": {
                "status": "FOUND",
                "score": 4,
                "citations": [_NON_FOUND],
            }
        },
    )
    assert result.status == STATUS_SUCCEEDED
    row = next(
        r
        for r in result.assessment["criteria"]
        if r["criterion_id"] == "testing.integration_testing"
    )
    assert row["status"] == "UNCERTAIN"
    assert row["score"] == 0
    assert row["unsupported"] is True
    assert any(
        f["criterion_id"] == "testing.integration_testing"
        for f in result.process.cross_check["findings"]
    )


def test_run_is_deterministic_across_runs() -> None:
    from evaluation.repoguard.serialize import result_identity, semantic_payload

    evidence = make_evidence()
    a = _run(evidence=evidence)
    b = _run(evidence=evidence, requested_at="2026-09-01T00:00:00+00:00")
    assert semantic_payload(a) == semantic_payload(b)
    assert result_identity(a) == result_identity(b)


def test_result_identity_excludes_runtime() -> None:
    from evaluation.repoguard.serialize import result_identity

    evidence = make_evidence()
    early = _run(evidence=evidence, requested_at="2026-08-01T00:00:00+00:00")
    late = _run(evidence=evidence, requested_at="2026-09-01T00:00:00+00:00")
    assert result_identity(early) == result_identity(late)
    assert early.runtime.requested_at != late.runtime.requested_at


def test_failed_runs_keep_model_response_for_audit() -> None:
    result = _run(text="not json at all")
    assert result.model_response == "not json at all"
    assert result.process.stages[-1]["status"] == "failed"
