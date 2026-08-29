"""Benchmark orchestration: datasets -> snapshots -> evidence -> both systems.

``execute_run`` builds an immutable run directory, verifies every bound
artifact, runs the requested evaluators over the *same* evidence object and
*same* provider configuration, and writes per-case outcomes and a run
manifest. It is orchestration only: scoring, evidence extraction, and ground
truth live in their own subsystems and are not reimplemented here.

Guarantees (docs/benchmark-runner.md):

* both systems receive the identical evidence artifact;
* both systems are scored by the identical scoring engine (shared rubric);
* failures are recorded per case and never converted into scores;
* one failing case never corrupts the others;
* no retries and no silent fallbacks change the experimental conditions;
* runs never overwrite earlier runs.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evaluation.baseline.models import BaselineResult
from evaluation.baseline.pipeline import EvaluatorConfig
from evaluation.baseline.pipeline import run_case as run_baseline
from evaluation.baseline.provider import (
    ENV_API_KEY,
    ENV_MODEL,
    HTTP_PROVIDER_IDS,
    MOCK_PROVIDER,
    LLMProvider,
    build_provider,
)
from evaluation.baseline.serialize import compose_result as compose_baseline
from evaluation.baseline.serialize import write_result as write_baseline
from evaluation.benchmark.cases import load_evidence, snapshot_artifacts, verify_snapshot
from evaluation.benchmark.errors import BenchmarkArtifactError, BenchmarkConfigError, RunExistsError
from evaluation.benchmark.manifest import build_run_manifest, write_run_manifest
from evaluation.benchmark.models import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    ErrorRecord,
    EvaluatorOutcome,
    ExecutedCase,
)
from evaluation.benchmark.paths import (
    baseline_result_file,
    repoguard_result_file,
    run_dir,
)
from evaluation.benchmark.results import write_case_record
from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard.models import RepoResult
from evaluation.repoguard.pipeline import run_case as run_repoguard
from evaluation.repoguard.serialize import compose_result as compose_repoguard
from evaluation.repoguard.serialize import write_result as write_repoguard
from evaluation.scoring.rubric import RUBRIC_VERSION
from evaluation.snapshot.models import DatasetManifest, ManifestCase

# Evaluator identifiers accepted by ``--evaluator`` and internal runner.
EVALUATOR_BASELINE = "baseline"
EVALUATOR_REPOGUARD = "repoguard"
ALL_EVALUATORS = frozenset({EVALUATOR_BASELINE, EVALUATOR_REPOGUARD})

_STATUS_OK = "succeeded"


@dataclass(slots=True)
class RunInput:
    """Everything a run needs, resolved by the CLI from user configuration."""

    dataset: DatasetManifest
    dataset_identity: str
    cases: list[ManifestCase]
    store: Path
    provider: LLMProvider
    config: EvaluatorConfig
    evaluators: frozenset[str]
    results_dir: Path
    run_id: str
    secrets: list[str] = field(default_factory=list)


def build_run_input(
    *,
    dataset: DatasetManifest,
    dataset_identity: str,
    cases: Sequence[ManifestCase],
    store: Path,
    provider: LLMProvider,
    config: EvaluatorConfig,
    evaluators: Iterable[str],
    results_dir: Path,
    run_id: str,
    secrets: Iterable[str] = (),
) -> RunInput:
    selected = frozenset(evaluators)
    unknown = selected - ALL_EVALUATORS
    if unknown or not selected:
        raise BenchmarkConfigError(
            f"invalid evaluator selection {sorted(selected)}; expected all/baseline/repoguard"
        )
    return RunInput(
        dataset=dataset,
        dataset_identity=dataset_identity,
        cases=list(cases),
        store=store,
        provider=provider,
        config=config,
        evaluators=selected,
        results_dir=results_dir,
        run_id=run_id,
        secrets=list(secrets),
    )


def resolve_provider(
    *,
    name: str | None,
    model: str | None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    timeout_s: float = 60.0,
) -> tuple[LLMProvider, EvaluatorConfig]:
    """Build the provider and non-secret configuration for a benchmark run.

    The default is always the deterministic mock provider. A real (HTTP)
    provider is used only when explicitly requested by name; it fails closed
    when its configuration is missing. A key in the environment alone never
    triggers a network call.
    """
    provider_name = (name or MOCK_PROVIDER).strip().lower()
    try:
        provider = build_provider(provider_name, model=model, timeout_s=timeout_s)
    except Exception as exc:
        raise BenchmarkConfigError(str(exc)) from exc
    config = EvaluatorConfig(
        provider_name=provider.name,
        model=_effective_model(provider_name, model),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return provider, config


def _effective_model(provider_name: str, model: str | None) -> str:
    if model:
        return model
    if provider_name in HTTP_PROVIDER_IDS:
        return os.environ.get(ENV_MODEL, "").strip() or MOCK_PROVIDER
    return MOCK_PROVIDER


def execute_run(run: RunInput) -> list[ExecutedCase]:
    """Execute a benchmark run into a fresh, immutable ``results_dir/run_id`` tree."""
    target = run_dir(run.results_dir, run.run_id)
    if target.exists():
        if (target / "run-manifest.yaml").is_file():
            raise RunExistsError(
                f"run '{run.run_id}' already exists at {target}; runs are immutable"
            )
        raise RunExistsError(f"run directory already exists: {target}")
    target.mkdir(parents=True)

    executed: list[ExecutedCase] = []
    for case in run.cases:
        executed.append(_execute_case(run, case))
        write_case_record(run.results_dir, run.run_id, executed[-1])

    manifest = build_run_manifest(run, executed)
    write_run_manifest(run.results_dir, run.run_id, manifest)
    return executed


def _execute_case(run: RunInput, case: ManifestCase) -> ExecutedCase:
    snapshot_root = snapshot_artifacts(case, run.store)
    try:
        snapshot = verify_snapshot(snapshot_root, case, run.dataset.name, run.dataset.version)
        evidence = load_evidence(snapshot_root, case, snapshot)
    except BenchmarkArtifactError as exc:
        return ExecutedCase(
            case_id=case.candidate_id,
            status=STATUS_FAILED,
            evidence_identity=None,
            baseline=None,
            repoguard=None,
            delta=None,
            error=ErrorRecord(kind=exc.kind, message=exc.message),
        )

    baseline: tuple[EvaluatorOutcome, dict[str, Any]] | None = None
    repoguard: tuple[EvaluatorOutcome, dict[str, Any]] | None = None
    if "baseline" in run.evaluators:
        baseline = _run_baseline(run, evidence)
    if "repoguard" in run.evaluators:
        repoguard = _run_repoguard(run, evidence)

    requested = [
        (EVALUATOR_BASELINE, baseline),
        (EVALUATOR_REPOGUARD, repoguard),
    ]
    requested = [(name, outcome) for name, outcome in requested if name in run.evaluators]

    error = _case_error(requested)
    shared = _verify_shared(baseline, repoguard, evidence)
    if shared is not None and error is None:
        error = shared
    status = (
        STATUS_SUCCEEDED
        if error is None
        and all(outcome is not None and outcome[0].status == _STATUS_OK for _, outcome in requested)
        else STATUS_FAILED
    )

    return ExecutedCase(
        case_id=case.candidate_id,
        status=status,
        evidence_identity=evidence.evidence_identity,
        baseline=baseline[0] if baseline else None,
        repoguard=repoguard[0] if repoguard else None,
        delta=_score_delta(baseline[0] if baseline else None, repoguard[0] if repoguard else None),
        error=error,
        baseline_artifact=baseline[1] if baseline else None,
        repoguard_artifact=repoguard[1] if repoguard else None,
    )


def _run_baseline(
    run: RunInput, evidence: EvidenceArtifact
) -> tuple[EvaluatorOutcome, dict[str, Any]]:
    out_path = baseline_result_file(run.results_dir, run.run_id, evidence.case_id)
    try:
        result: BaselineResult = run_baseline(evidence, run.provider, config=run.config)
    except Exception as exc:
        return _internal_outcome(f"baseline run failed unexpectedly: {exc}"), {}
    artifact = compose_baseline(result)
    write_baseline(out_path, result, run.secrets)
    return _outcome_from(result.status, result.scoring, artifact, out_path, result.error), artifact


def _run_repoguard(
    run: RunInput, evidence: EvidenceArtifact
) -> tuple[EvaluatorOutcome, dict[str, Any]]:
    out_path = repoguard_result_file(run.results_dir, run.run_id, evidence.case_id)
    try:
        result: RepoResult = run_repoguard(evidence, run.provider, config=run.config)
    except Exception as exc:
        return _internal_outcome(f"repoguard run failed unexpectedly: {exc}"), {}
    artifact = compose_repoguard(result)
    write_repoguard(out_path, result, run.secrets)
    return _outcome_from(result.status, result.scoring, artifact, out_path, result.error), artifact


def _outcome_from(
    status: str,
    scoring: Any,
    artifact: dict[str, Any],
    out_path: Path,
    error: Any,
) -> EvaluatorOutcome:
    score = _score_of(scoring) if status == _STATUS_OK else None
    identity = artifact.get("result_identity")
    error_kind = getattr(error, "kind", None) if status != _STATUS_OK else None
    return EvaluatorOutcome(
        status=status,
        result_identity=str(identity) if isinstance(identity, str) else "",
        score=score,
        result_path=str(out_path),
        error_kind=error_kind,
    )


def _internal_outcome(message: str) -> EvaluatorOutcome:
    return EvaluatorOutcome(
        status=STATUS_FAILED,
        result_identity="",
        score=None,
        result_path=None,
        error_kind="internal_error",
    )


def _score_of(scoring: Any) -> float | None:
    if not isinstance(scoring, dict):
        return None
    score = scoring.get("score")
    return score if isinstance(score, (int, float)) and not isinstance(score, bool) else None


def _score_delta(
    baseline: EvaluatorOutcome | None, repoguard: EvaluatorOutcome | None
) -> float | None:
    if baseline is None or repoguard is None:
        return None
    if baseline.score is None or repoguard.score is None:
        return None
    return round(repoguard.score - baseline.score, 12)


def _case_error(
    requested: list[tuple[str, tuple[EvaluatorOutcome, dict[str, Any]] | None]],
) -> ErrorRecord | None:
    for name, outcome in requested:
        if outcome is None:
            return ErrorRecord(kind="internal_error", message=f"{name} produced no result")
        if outcome[0].status != _STATUS_OK:
            kind = outcome[0].error_kind or "evaluation_failed"
            return ErrorRecord(kind=kind, message=f"{name} evaluation failed ({kind})")
    return None


def _verify_shared(
    baseline: tuple[EvaluatorOutcome, dict[str, Any]] | None,
    repoguard: tuple[EvaluatorOutcome, dict[str, Any]] | None,
    evidence: EvidenceArtifact,
) -> ErrorRecord | None:
    """Fail closed unless both systems bound to the same evidence and rubric."""

    def _problems(label: str, artifact: dict[str, Any]) -> list[str]:
        found: list[str] = []
        if artifact.get("evidence_identity") != evidence.evidence_identity:
            found.append(f"{label} did not consume the run's evidence artifact")
        if artifact.get("rubric_version") != RUBRIC_VERSION:
            found.append(
                f"{label} was scored with rubric {artifact.get('rubric_version')!r}, "
                f"not {RUBRIC_VERSION!r}"
            )
        return found

    problems: list[str] = []
    if baseline is not None:
        problems += _problems("baseline", baseline[1])
    if repoguard is not None:
        problems += _problems("repoguard", repoguard[1])
    if problems:
        return ErrorRecord(kind="shared_input_mismatch", message="; ".join(problems))
    return None


def default_secrets() -> list[str]:
    api_key = os.environ.get(ENV_API_KEY, "")
    return [api_key] if api_key else []
