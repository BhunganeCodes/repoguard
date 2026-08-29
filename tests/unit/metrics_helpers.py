"""Synthetic fixtures for the metrics subsystem tests.

These helpers materialize benchmark run directories that pass the benchmark
runner's own ``validate_run`` checks, using the real artifact composers and
scoring engine, so metrics tests exercise honest, identity-consistent inputs
with full control over scores, failures, runtime facts, citations, and
ground-truth statuses. They also build structurally valid ground-truth
consensus artifacts for the tests only: never the official dataset, never
the real 11-case benchmark, and never evaluation results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from scoring_helpers import DEFAULT_CITATION, make_evidence

from evaluation.baseline._version import __version__ as BASELINE_VERSION
from evaluation.baseline.models import (
    BaselineResult,
)
from evaluation.baseline.models import (
    ErrorRecord as BaselineErrorRecord,
)
from evaluation.baseline.models import (
    RuntimeMetadata as BaselineRuntimeMetadata,
)
from evaluation.baseline.prompt import PROMPT_VERSION as BASELINE_PROMPT_VERSION
from evaluation.baseline.serialize import (
    result_identity as baseline_result_identity,
)
from evaluation.baseline.serialize import (
    write_result as write_baseline_result,
)
from evaluation.benchmark._version import __version__ as BENCHMARK_VERSION
from evaluation.benchmark.cases import dataset_identity
from evaluation.benchmark.manifest import run_identity, write_run_manifest
from evaluation.benchmark.models import STATUS_FAILED, STATUS_SUCCEEDED
from evaluation.benchmark.paths import run_dir
from evaluation.evidence.models import EvidenceArtifact
from evaluation.ground_truth._version import DATASET_VERSION, GROUND_TRUTH_SCHEMA_VERSION
from evaluation.ground_truth.serialize import ground_truth_identity
from evaluation.repoguard._version import __version__ as REPOGUARD_VERSION
from evaluation.repoguard.models import (
    ProcessRecord,
    RepoResult,
)
from evaluation.repoguard.models import (
    RuntimeMetadata as RepoRuntimeMetadata,
)
from evaluation.repoguard.prompts import PROMPT_VERSION as REPOGUARD_PROMPT_VERSION
from evaluation.repoguard.serialize import (
    result_identity as repoguard_result_identity,
)
from evaluation.repoguard.serialize import (
    write_result as write_repoguard_result,
)
from evaluation.scoring.rubric import CRITERIA, RUBRIC_VERSION
from evaluation.scoring.serialize import compose_assessment

DATASET_NAME = "repoguard-evaluation-dataset"

DIMENSIONS = {definition["dimension"] for definition in CRITERIA.values()}


@dataclass(slots=True)
class OutSpec:
    """One system's outcome for one case in a synthetic run."""

    status: str = STATUS_SUCCEEDED
    score: int = 2
    scores: dict[str, int] | None = None
    error_kind: str = "provider_error"
    extra_citations: tuple[str, ...] = ()
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None


@dataclass(slots=True)
class CaseSpec:
    """One case in a synthetic run."""

    case_id: str
    baseline: OutSpec | None = None
    repoguard: OutSpec | None = None
    setup_failure: str | None = None


def typed_rows(
    evidence: EvidenceArtifact,
    out: OutSpec,
) -> list[dict[str, Any]]:
    """25 canonical FOUND rows; every criterion scores ``score`` unless
    overridden, with the case's default citations plus any extra ones."""
    rows: list[dict[str, Any]] = []
    for criterion_id in CRITERIA:
        score = (out.scores or {}).get(criterion_id, out.score)
        citations = list(DEFAULT_CITATION[criterion_id])
        if out.extra_citations:
            citations = citations + list(out.extra_citations)
        rows.append(
            {
                "criterion_id": criterion_id,
                "dimension": CRITERIA[criterion_id]["dimension"],
                "status": "FOUND",
                "score": int(score),
                "citations": citations,
            }
        )
    return rows


def composed_assessment(evidence: EvidenceArtifact, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return compose_assessment(
        {
            "schema_version": 1,
            "case_id": evidence.case_id,
            "name": evidence.name,
            "rubric_version": RUBRIC_VERSION,
            "evidence_identity": evidence.evidence_identity,
            "criteria": rows,
        },
        evidence,
    )


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


def _outcome_dict(
    *,
    status: str,
    result_identity: str,
    score: float | None,
    result_path: str,
    error_kind: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "result_identity": result_identity,
        "score": score,
        "result_path": result_path,
        "error_kind": error_kind,
    }


def _runtime(
    latency_ms: float | None,
    input_tokens: int | None,
    output_tokens: int | None,
    estimated_cost: float | None,
) -> dict[str, Any]:
    return {
        "requested_at": datetime.now(UTC).isoformat(),
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimated_cost,
        "response_metadata": {},
    }


def _write_baseline(
    run_root: Path, case_id: str, evidence: EvidenceArtifact, out: OutSpec
) -> dict[str, Any]:
    relative = f"baseline/{case_id}/result.yaml"
    runtime = BaselineRuntimeMetadata(
        **_runtime(out.latency_ms, out.input_tokens, out.output_tokens, out.estimated_cost)
    )
    if out.status == STATUS_SUCCEEDED:
        assessment = composed_assessment(evidence, typed_rows(evidence, out))
        result = BaselineResult(
            baseline_version=BASELINE_VERSION,
            prompt_version=BASELINE_PROMPT_VERSION,
            rubric_version=RUBRIC_VERSION,
            case_id=case_id,
            name=evidence.name,
            evidence_identity=evidence.evidence_identity,
            status=STATUS_SUCCEEDED,
            provider_name="mock",
            provider_model="mock",
            model_config={},
            assessment=assessment,
            scoring=_scoring_summary(assessment),
            error=None,
            model_response=None,
            runtime=runtime,
        )
        identity = baseline_result_identity(result)
        score: float | None = float(assessment["summary"]["score"])
    else:
        result = BaselineResult(
            baseline_version=BASELINE_VERSION,
            prompt_version=BASELINE_PROMPT_VERSION,
            rubric_version=RUBRIC_VERSION,
            case_id=case_id,
            name=evidence.name,
            evidence_identity=evidence.evidence_identity,
            status=STATUS_FAILED,
            provider_name="mock",
            provider_model="mock",
            model_config={},
            assessment=None,
            scoring=None,
            error=BaselineErrorRecord(out.error_kind, "synthetic failure", []),
            model_response="",
            runtime=runtime,
        )
        identity = baseline_result_identity(result)
        score = None
    write_baseline_result(run_root / relative, result)
    return _outcome_dict(
        status=out.status,
        result_identity=identity,
        score=score,
        result_path=relative,
        error_kind=out.error_kind if out.status == STATUS_FAILED else None,
    )


def _write_repoguard(
    run_root: Path, case_id: str, evidence: EvidenceArtifact, out: OutSpec
) -> dict[str, Any]:
    relative = f"repoguard/{case_id}/result.yaml"
    runtime = RepoRuntimeMetadata(
        **_runtime(out.latency_ms, out.input_tokens, out.output_tokens, out.estimated_cost)
    )
    if out.status == STATUS_SUCCEEDED:
        assessment = composed_assessment(evidence, typed_rows(evidence, out))
        result = RepoResult(
            repoguard_version=REPOGUARD_VERSION,
            prompt_version=REPOGUARD_PROMPT_VERSION,
            rubric_version=RUBRIC_VERSION,
            case_id=case_id,
            name=evidence.name,
            evidence_identity=evidence.evidence_identity,
            status=STATUS_SUCCEEDED,
            provider_name="mock",
            provider_model="mock",
            model_config={},
            process=ProcessRecord(
                stages=[{"stage": "finalize", "status": "ok"}],
                plan=[],
                cross_check={"findings": [], "model_reported": []},
            ),
            assessment=assessment,
            scoring=_scoring_summary(assessment),
            error=None,
            model_response=None,
            runtime=runtime,
        )
        identity = repoguard_result_identity(result)
        score: float | None = float(assessment["summary"]["score"])
    else:
        result = RepoResult(
            repoguard_version=REPOGUARD_VERSION,
            prompt_version=REPOGUARD_PROMPT_VERSION,
            rubric_version=RUBRIC_VERSION,
            case_id=case_id,
            name=evidence.name,
            evidence_identity=evidence.evidence_identity,
            status=STATUS_FAILED,
            provider_name="mock",
            provider_model="mock",
            model_config={},
            process=ProcessRecord(),
            assessment=None,
            scoring=None,
            error=BaselineErrorRecord(out.error_kind, "synthetic failure", []),
            model_response="",
            runtime=runtime,
        )
        identity = repoguard_result_identity(result)
        score = None
    write_repoguard_result(run_root / relative, result)
    return _outcome_dict(
        status=out.status,
        result_identity=identity,
        score=score,
        result_path=relative,
        error_kind=out.error_kind if out.status == STATUS_FAILED else None,
    )


def materialize_run(
    tmp_path: Path,
    specs: list[CaseSpec],
    *,
    run_id: str = "run-1",
    evidence_store: Path | None = None,
) -> Path:
    """Build a ``validate_run``-clean benchmark run directory; returns it."""
    root = run_dir(tmp_path / "out", run_id)
    (root / "baseline").mkdir(parents=True, exist_ok=True)
    (root / "repoguard").mkdir(parents=True, exist_ok=True)

    if evidence_store is not None:
        evidence_store.mkdir(parents=True, exist_ok=True)

    evidence_identities: dict[str, str] = {}
    results: dict[str, Any] = {}
    for spec in specs:
        case_evidence: EvidenceArtifact | None = None
        if spec.setup_failure is None:
            evidence = make_evidence(spec.case_id)
            evidence_identities[spec.case_id] = evidence.evidence_identity
            case_evidence = evidence
            if evidence_store is not None:
                target = evidence_store / spec.case_id / "evidence.yaml"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8"
                )

        if spec.setup_failure is not None:
            results[spec.case_id] = {
                "status": STATUS_FAILED,
                "delta": None,
                "error": {
                    "kind": spec.setup_failure,
                    "message": "synthetic",
                    "details": [],
                },
            }
            continue

        outcomes: dict[str, dict[str, Any]] = {}
        if spec.baseline is not None:
            outcomes["baseline"] = _write_baseline(root, spec.case_id, case_evidence, spec.baseline)
        if spec.repoguard is not None:
            outcomes["repoguard"] = _write_repoguard(
                root, spec.case_id, case_evidence, spec.repoguard
            )

        case_status = (
            STATUS_SUCCEEDED
            if outcomes
            and all(outcome["status"] == STATUS_SUCCEEDED for outcome in outcomes.values())
            else STATUS_FAILED
        )
        error = None
        if case_status == STATUS_FAILED:
            failed = next(
                outcome for outcome in outcomes.values() if outcome["status"] == STATUS_FAILED
            )
            error = {"kind": failed["error_kind"], "message": "synthetic", "details": []}
        delta: float | None = None
        baseline_score = outcomes.get("baseline", {}).get("score")
        repoguard_score = outcomes.get("repoguard", {}).get("score")
        if baseline_score is not None and repoguard_score is not None:
            delta = round(float(repoguard_score) - float(baseline_score), 4)
        entry: dict[str, Any] = {"status": case_status, "delta": delta, "error": error}
        if "baseline" in outcomes:
            entry["baseline"] = outcomes["baseline"]
        if "repoguard" in outcomes:
            entry["repoguard"] = outcomes["repoguard"]
        results[spec.case_id] = entry

    dataset_path = tmp_path / "dataset.yaml"
    dataset_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "dataset": {
                    "name": DATASET_NAME,
                    "version": DATASET_VERSION,
                    "creation_date": "2026-08-28",
                    "status": "frozen",
                },
                "source_registry": "synthetic",
                "protocol": "docs/evaluation.md",
                "freeze_decision": "synthetic fixture",
                "counts": {"included": len(specs), "confirmed": len(specs)},
                "candidates": [
                    {
                        "candidate_id": spec.case_id,
                        "name": "synthetic",
                        "dataset_status": "confirmed",
                        "dataset_decision": "include",
                    }
                    for spec in specs
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    enabled_baseline = any(
        spec.baseline is not None and spec.setup_failure is None for spec in specs
    )
    enabled_repoguard = any(
        spec.repoguard is not None and spec.setup_failure is None for spec in specs
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "system": "benchmark",
        "benchmark_version": BENCHMARK_VERSION,
        "run_id": run_id,
        "dataset": {
            "name": DATASET_NAME,
            "version": DATASET_VERSION,
            "status": "frozen",
            "identity": dataset_identity(dataset_path),
        },
        "rubric_version": RUBRIC_VERSION,
        "cases": [spec.case_id for spec in specs],
        "evidence": evidence_identities,
        "evaluators": {
            "baseline": {
                "enabled": enabled_baseline,
                "baseline_version": BASELINE_VERSION,
                "prompt_version": BASELINE_PROMPT_VERSION,
            },
            "repoguard": {
                "enabled": enabled_repoguard,
                "repoguard_version": REPOGUARD_VERSION,
                "prompt_version": REPOGUARD_PROMPT_VERSION,
            },
        },
        "provider": {
            "provider_name": "mock",
            "model": "mock",
            "temperature": 0.0,
            "max_tokens": 10,
            "timeout_s": 30,
            "description": "mock",
            "extra": {},
            "public": {"mode": "mock"},
        },
        "results": results,
        "created_at": datetime.now(UTC).isoformat(),
        "environment": {"python": "3", "platform": "synthetic"},
    }
    manifest["run_identity"] = run_identity(manifest)
    write_run_manifest(tmp_path / "out", run_id, manifest)
    return root


def ground_truth_artifact(
    evidence: EvidenceArtifact,
    *,
    score: int = 2,
    status: str = "consensus",
) -> dict[str, Any]:
    """A structurally valid consensus artifact for the given evidence."""
    assessment = composed_assessment(evidence, typed_rows(evidence, OutSpec(score=score)))
    artifact: dict[str, Any] = {
        "schema_version": GROUND_TRUTH_SCHEMA_VERSION,
        "ground_truth_identity": "",
        "dataset_version": DATASET_VERSION,
        "case_id": evidence.case_id,
        "name": evidence.name,
        "rubric_version": RUBRIC_VERSION,
        "evidence_identity": evidence.evidence_identity,
        "status": status,
        "reviewers": {"independent": [], "adjudicator": None},
        "adjudication_identity": None,
        "provenance": {},
        "assessment": assessment,
    }
    artifact["ground_truth_identity"] = ground_truth_identity(artifact)
    return artifact


def write_ground_truth(
    directory: Path,
    artifacts: list[dict[str, Any]],
    case_ids: list[str] | None = None,
) -> None:
    """Write consensus artifacts named ``<case_id>-ground-truth.yaml``."""
    directory.mkdir(parents=True, exist_ok=True)
    for index, artifact in enumerate(artifacts):
        case_id = case_ids[index] if case_ids else artifact["case_id"]
        (directory / f"{case_id}-ground-truth.yaml").write_text(
            yaml.safe_dump(artifact, sort_keys=False), encoding="utf-8"
        )
