"""The baseline pipeline: evidence -> prompt -> LLM -> assessment -> score.

``run_case`` performs exactly one LLM call per assessment (docs/baseline.md,
"Architecture"). It never retries, never self-corrects, and never repairs an
invalid model response: anything the model returns is validated against the
scoring engine, and every failure is recorded in the result rather than
silently turned into a score.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import yaml

from evaluation.baseline._version import __version__
from evaluation.baseline.errors import BaselineError, MalformedResponse
from evaluation.baseline.models import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    BaselineResult,
    ErrorRecord,
    RuntimeMetadata,
)
from evaluation.baseline.prompt import PROMPT_VERSION, build_prompt
from evaluation.baseline.provider import LLMProvider, LLMRequest
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import recompute_identity
from evaluation.evidence.validate import validate_artifact
from evaluation.scoring.serialize import compose_assessment
from evaluation.scoring.validate import validate_assessment


@dataclass(slots=True)
class EvaluatorConfig:
    """Non-secret model/provider configuration recorded with the run."""

    provider_name: str = "mock"
    model: str = "mock"
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout_s: float = 60.0
    extra: dict[str, Any] = field(default_factory=dict)


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def validate_evidence(evidence: EvidenceArtifact) -> None:
    """Fail closed on unusable or tampered evidence input."""
    problems = validate_artifact(evidence)
    if problems:
        raise BaselineError("invalid evidence artifact: " + "; ".join(problems))
    if recompute_identity(evidence) != evidence.evidence_identity:
        raise BaselineError("evidence identity does not match its content")


def parse_assessment(text: str) -> dict[str, Any]:
    """Deterministically parse a model response into an assessment mapping.

    Accepted, documented normalization:
    * optional markdown code fences around the content are stripped;
    * the content is parsed with a single ``yaml.safe_load`` (JSON is a YAML
      subset, so both JSON and YAML responses work identically).

    Anything else fails closed with :class:`MalformedResponse`; values are
    never repaired or invented.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].lstrip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        data = yaml.safe_load(stripped)
    except yaml.YAMLError as exc:
        raise MalformedResponse(f"response could not be parsed: {exc}") from exc
    if not isinstance(data, dict):
        raise MalformedResponse("response did not parse to a structured assessment mapping")
    return data


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


def run_case(
    evidence: EvidenceArtifact,
    provider: LLMProvider,
    *,
    config: EvaluatorConfig | None = None,
    requested_at: str | None = None,
) -> BaselineResult:
    """Run the baseline for one case. Never touches a repository or the
    benchmark ground truth; the snapshot/evidence already exist."""
    config = config or EvaluatorConfig()
    validate_evidence(evidence)
    system, user = build_prompt(evidence)
    request = LLMRequest(
        system=system,
        prompt=user,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    timestamp = requested_at or _now_utc()
    model_config = _model_config(config, provider)

    started = time.perf_counter()
    try:
        response = provider.generate(request)
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return _failure(
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            latency_ms=latency_ms,
            kind="provider_error",
            message=f"provider failed: {exc}",
            details=[],
            model_response=None,
            response=None,
        )
    latency_ms = (time.perf_counter() - started) * 1000.0

    try:
        assessment = parse_assessment(response.text)
    except MalformedResponse as exc:
        return _failure(
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            latency_ms=latency_ms,
            kind="malformed_response",
            message=str(exc),
            details=[],
            model_response=response.text,
            response=response,
        )

    problems = validate_assessment(assessment, evidence)
    if problems:
        return _failure(
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            latency_ms=latency_ms,
            kind="invalid_assessment",
            message="model assessment failed validation",
            details=list(problems),
            model_response=response.text,
            response=response,
        )

    artifact = compose_assessment(assessment, evidence)
    summary = artifact.get("summary")
    if not isinstance(summary, dict) or summary.get("complete") is not True:
        pending = list(summary.get("pending") or []) if isinstance(summary, dict) else []
        return _failure(
            evidence=evidence,
            config=config,
            model_config=model_config,
            provider=provider,
            requested_at=timestamp,
            latency_ms=latency_ms,
            kind="incomplete_assessment",
            message="model assessment contains PENDING criteria",
            details=pending,
            model_response=response.text,
            response=response,
        )
    # Validation guarantees the rubric version is present and a string.
    rubric_version = str(artifact["rubric_version"])

    scoring = {
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

    return BaselineResult(
        baseline_version=__version__,
        prompt_version=PROMPT_VERSION,
        rubric_version=rubric_version,
        case_id=evidence.case_id,
        name=evidence.name,
        evidence_identity=evidence.evidence_identity,
        status=STATUS_SUCCEEDED,
        provider_name=provider.name,
        provider_model=response.model or config.model,
        model_config=model_config,
        assessment=artifact,
        scoring=scoring,
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


def _failure(
    *,
    evidence: EvidenceArtifact,
    config: EvaluatorConfig,
    model_config: dict[str, Any],
    provider: LLMProvider,
    requested_at: str,
    latency_ms: float,
    kind: str,
    message: str,
    details: list[str],
    model_response: str | None,
    response: Any,
) -> BaselineResult:
    input_tokens = None
    output_tokens = None
    estimated_cost = None
    response_metadata: dict[str, Any] = {}
    model = config.model
    if response is not None:
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens
        estimated_cost = response.estimated_cost
        response_metadata = dict(response.metadata)
        model = response.model or config.model
    return BaselineResult(
        baseline_version=__version__,
        prompt_version=PROMPT_VERSION,
        rubric_version="1.0",
        case_id=evidence.case_id,
        name=evidence.name,
        evidence_identity=evidence.evidence_identity,
        status=STATUS_FAILED,
        provider_name=provider.name,
        provider_model=model,
        model_config=model_config,
        assessment=None,
        scoring=None,
        error=ErrorRecord(kind=kind, message=message, details=details),
        model_response=model_response,
        runtime=RuntimeMetadata(
            requested_at=requested_at,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            response_metadata=response_metadata,
        ),
    )
