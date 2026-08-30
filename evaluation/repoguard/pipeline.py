"""The RepoGuard orchestration: one structured model response, five stages.

``run_case`` drives the explicit LOAD -> PLAN -> ASSESS -> CROSS-CHECK ->
FINALIZE workflow (docs/repoguard.md, "Workflow"). The model receives a
single staged prompt whose response carries the PLAN, criteria, and
CROSS-CHECK sections; RepoGuard then treats each section as a separate,
explicitly validated stage and never trusts any of it until the evidence has
been re-checked by the deterministic cross-check.

Failures are recorded, never converted into scores:

* input problems (``invalid_evidence``)
* provider failures (``provider_error``)
* a response that does not parse to the staged mapping
  (``malformed_response``)
* a structurally unusable PLAN or CROSS-CHECK section
  (``invalid_plan`` / ``invalid_cross_check``)
* criteria that fail the scoring engine's fail-closed validation
  (``invalid_assessment``)
* a valid-but-incomplete assessment with PENDING criteria
  (``incomplete_assessment``)

The workflow never touches a repository, the benchmark ground truth, or the
frozen dataset.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from evaluation.baseline.errors import BaselineError, MalformedResponse
from evaluation.baseline.pipeline import EvaluatorConfig, parse_assessment, validate_evidence
from evaluation.baseline.provider import LLMProvider, LLMRequest
from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard import assess, crosscheck, plan
from evaluation.repoguard._version import __version__
from evaluation.repoguard.models import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    ErrorRecord,
    ProcessRecord,
    RepoResult,
    RuntimeMetadata,
)
from evaluation.repoguard.prompts import PROMPT_VERSION, build_prompt
from evaluation.repoguard.state import RunState
from evaluation.scoring.errors import ScoringError
from evaluation.scoring.serialize import compose_assessment, require_complete
from evaluation.scoring.validate import validate_assessment

# Failure kinds recorded by the orchestrator (stable and documented in
# docs/repoguard.md "Validation").
FAIL_PROVIDER = "provider_error"
FAIL_MALFORMED = "malformed_response"
FAIL_PLAN = "invalid_plan"
FAIL_CROSS_CHECK = "invalid_cross_check"
FAIL_ASSESSMENT = "invalid_assessment"
FAIL_INCOMPLETE = "incomplete_assessment"
FAIL_EVIDENCE = "invalid_evidence"

# Required sections of the staged model response.
_REQUIRED_SECTIONS = frozenset({"plan", "criteria"})


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _model_config(config: EvaluatorConfig, provider: LLMProvider) -> dict[str, Any]:
    recorded: dict[str, Any] = {
        "mode": provider.name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout_s": config.timeout_s,
    }
    recorded.update(provider.public_config())
    recorded.update(config.extra)
    return recorded


def _scoring_summary(assessment: dict[str, Any]) -> dict[str, Any]:
    summary = assessment["summary"]
    return {
        key: summary.get(key)
        for key in (
            "complete",
            "earned",
            "possible",
            "score",
            "not_applicable",
            "uncertain",
            "pending",
        )
    }


def run_case(
    evidence: EvidenceArtifact,
    provider: LLMProvider,
    *,
    config: EvaluatorConfig | None = None,
    requested_at: str | None = None,
) -> RepoResult:
    """Run RepoGuard for one case. Never touches a repository or ground truth."""
    config = config or EvaluatorConfig()
    state = RunState()
    model_config = _model_config(config, provider)
    timestamp = requested_at or _now_utc()

    # ---- LOAD ----
    try:
        validate_evidence(evidence)
    except BaselineError as exc:
        return _fail(
            state=state,
            stage="load",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_EVIDENCE,
            message=str(exc),
            details=[],
            latency_ms=0.0,
        )
    state.advance("load", "ok", notes={"items": len(evidence.items), "name": evidence.name})

    # ---- PLAN ----
    system, user = build_prompt(evidence)
    request = LLMRequest(
        system=system,
        prompt=user,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    started = time.perf_counter()
    try:
        response = provider.generate(request)
    except Exception as exc:  # noqa: BLE001 - provider failures are recorded
        latency_ms = (time.perf_counter() - started) * 1000.0
        return _fail(
            state=state,
            stage="plan",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_PROVIDER,
            message=f"provider failed: {exc}",
            details=[],
            latency_ms=latency_ms,
        )
    latency_ms = (time.perf_counter() - started) * 1000.0
    try:
        staged = parse_assessment(response.text)
    except MalformedResponse as exc:
        return _fail(
            state=state,
            stage="plan",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_MALFORMED,
            message=str(exc),
            details=[],
            latency_ms=latency_ms,
            model_response=response.text,
        )
    if not isinstance(staged, dict) or not _REQUIRED_SECTIONS <= set(staged):
        return _fail(
            state=state,
            stage="plan",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_MALFORMED,
            message="response parsed but is missing the plan and/or criteria sections",
            details=[],
            latency_ms=latency_ms,
            model_response=response.text,
        )
    try:
        model_plan = plan.plan_from_model(staged.get("plan"), evidence)
    except plan.PlanProblem as exc:
        return _fail(
            state=state,
            stage="plan",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_PLAN,
            message=str(exc),
            details=[],
            latency_ms=latency_ms,
            model_response=response.text,
        )
    state.plan_record = plan.make_plan_record(evidence, model_plan)
    state.advance("plan", "ok", notes={"criteria_planned": len(model_plan)})

    # ---- ASSESS ----
    try:
        authored = assess.build_authored(staged.get("criteria"), evidence)
    except assess.AssessmentProblem as exc:
        return _fail(
            state=state,
            stage="assess",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_ASSESSMENT,
            message=str(exc),
            details=[],
            latency_ms=latency_ms,
            model_response=response.text,
        )
    problems = validate_assessment(authored, evidence)
    if problems:
        return _fail(
            state=state,
            stage="assess",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_ASSESSMENT,
            message="model criteria failed scoring validation",
            details=list(problems),
            latency_ms=latency_ms,
            model_response=response.text,
        )
    state.authored = authored
    state.advance("assess", "ok", notes={"criteria": len(authored["criteria"])})

    # ---- CROSS-CHECK ----
    try:
        model_cross_check = crosscheck.canonicalize_model_cross_check(
            staged.get("cross_check"), evidence
        )
    except crosscheck.CrossCheckError as exc:
        return _fail(
            state=state,
            stage="cross_check",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_CROSS_CHECK,
            message=str(exc),
            details=[],
            latency_ms=latency_ms,
            model_response=response.text,
        )
    state.model_reported = model_cross_check
    findings = crosscheck.detect(authored["criteria"], evidence)
    state.findings = [finding.to_dict() for finding in findings]
    state.final_rows = crosscheck.apply_corrections(authored["criteria"], findings)
    state.advance(
        "cross_check",
        "ok",
        notes={"downgraded_to_uncertain": sum(1 for f in findings if f.resolution is not None)},
    )

    # ---- FINALIZE ----
    authored["criteria"] = list(state.final_rows)
    problems = validate_assessment(authored, evidence)
    if problems:
        return _fail(
            state=state,
            stage="finalize",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_ASSESSMENT,
            message="corrected criteria failed scoring validation",
            details=list(problems),
            latency_ms=latency_ms,
            model_response=response.text,
        )
    try:
        artifact = compose_assessment(authored, evidence)
    except ScoringError as exc:
        return _fail(
            state=state,
            stage="finalize",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_ASSESSMENT,
            message=f"assessment could not be composed: {exc}",
            details=[],
            latency_ms=latency_ms,
            model_response=response.text,
        )
    try:
        require_complete(artifact)
    except ScoringError as exc:
        return _fail(
            state=state,
            stage="finalize",
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            kind=FAIL_INCOMPLETE,
            message=str(exc),
            details=[],
            latency_ms=latency_ms,
            model_response=response.text,
        )
    state.assessment = artifact
    summary = artifact["summary"]
    state.advance(
        "finalize",
        "ok",
        notes={"earned": summary.get("earned"), "score": summary.get("score")},
    )

    return RepoResult(
        repoguard_version=__version__,
        prompt_version=PROMPT_VERSION,
        rubric_version=str(artifact["rubric_version"]),
        case_id=evidence.case_id,
        name=evidence.name,
        evidence_identity=evidence.evidence_identity,
        status=STATUS_SUCCEEDED,
        provider_name=provider.name,
        provider_model=response.model or config.model,
        model_config=model_config,
        process=_process_record(state),
        assessment=artifact,
        scoring=_scoring_summary(artifact),
        error=None,
        model_response=None,
        runtime=RuntimeMetadata(
            requested_at=timestamp,
            latency_ms=latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost=response.estimated_cost,
            response_metadata=dict(response.metadata),
        ),
    )


def _process_record(state: RunState) -> ProcessRecord:
    return ProcessRecord(
        stages=state.trace(),
        plan=[dict(entry) for entry in state.plan_record],
        cross_check={
            "findings": [dict(finding) for finding in state.findings],
            "model_reported": [dict(finding) for finding in state.model_reported],
        },
    )


def _fail(
    *,
    state: RunState,
    stage: str,
    evidence: EvidenceArtifact,
    config: EvaluatorConfig,
    model_config: dict[str, Any],
    provider: LLMProvider,
    requested_at: str,
    kind: str,
    message: str,
    details: list[str],
    latency_ms: float,
    model_response: str | None = None,
) -> RepoResult:
    state.advance(stage, "failed", notes={"kind": kind})
    return RepoResult(
        repoguard_version=__version__,
        prompt_version=PROMPT_VERSION,
        rubric_version="1.0",
        case_id=evidence.case_id,
        name=evidence.name,
        evidence_identity=evidence.evidence_identity,
        status=STATUS_FAILED,
        provider_name=provider.name,
        provider_model=config.model,
        model_config=model_config,
        process=_process_record(state),
        assessment=None,
        scoring=None,
        error=ErrorRecord(kind=kind, message=message, details=details),
        model_response=model_response,
        runtime=RuntimeMetadata(
            requested_at=requested_at,
            latency_ms=latency_ms,
            input_tokens=None,
            output_tokens=None,
            estimated_cost=None,
            response_metadata={},
        ),
    )
