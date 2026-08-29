"""Metrics report composition.

Turns a validated benchmark run (plus optional ground-truth and evidence
inputs) into a metrics report. The composition is read-only: benchmark
results, evidence artifacts, and ground truth are consumed but never
modified. Any fail-closed validation problem raises ``MetricsInputError``
before a report can be produced, so a report is never missing a needed
binding.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evaluation.benchmark.manifest import load_run_manifest, validate_run
from evaluation.metrics import (
    agreement,
    compare,
    cost,
    findings,
    ranking,
    timing,
)
from evaluation.metrics import (
    evidence as evidence_metric,
)
from evaluation.metrics import (
    runtime as runtime_metric,
)
from evaluation.metrics._version import METRICS_SCHEMA_VERSION, SYSTEM_ID, __version__
from evaluation.metrics.errors import MetricsInputError
from evaluation.metrics.models import (
    STATUS_FAILED,
    STATUS_NOT_PRESENT,
    STATUS_SUCCEEDED,
    SystemCaseRecord,
)
from evaluation.metrics.serialize import (
    compose_report,
    ground_truth_identities_identity,
)
from evaluation.metrics.validate import validate_ground_truth_artifact

_ALL_SECONDARY_METRICS = (
    "evidence_accuracy",
    "critical_finding_recall",
    "false_positive_rate",
    "assessment_time",
    "runtime",
    "cost",
)

ALL_METRIC_NAMES = _ALL_SECONDARY_METRICS


@dataclass(slots=True)
class ReportOptions:
    contested: str = "exclude"
    metrics: tuple[str, ...] = _ALL_SECONDARY_METRICS
    evidence_dir: Path | None = None
    ground_truth_findings: Path | None = None
    baseline_findings: Path | None = None
    repoguard_findings: Path | None = None
    review_times: Path | None = None


def _float_or_none(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricsInputError(f"{label}: invalid number {value!r}")
    return float(value)


def _int_or_none(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetricsInputError(f"{label}: invalid integer {value!r}")
    return int(value)


def _citations_from(raw: dict[str, Any]) -> list[str]:
    assessment = raw.get("assessment")
    if not isinstance(assessment, dict):
        return []
    criteria = assessment.get("criteria")
    if not isinstance(criteria, list):
        return []
    citations: list[str] = []
    for row in criteria:
        if not isinstance(row, dict):
            continue
        row_citations = row.get("citations")
        if isinstance(row_citations, list):
            citations.extend(str(item) for item in row_citations if isinstance(item, str))
    return sorted(set(citations))


def _read_result(
    run_dir: Path,
    case_id: str,
    system: str,
    outcome: dict[str, Any],
) -> SystemCaseRecord:
    result_path = outcome.get("result_path")
    if not isinstance(result_path, str):
        raise MetricsInputError(f"{system} result for {case_id}: no result_path recorded")
    path = run_dir / result_path
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MetricsInputError(f"{system} result for {case_id} unreadable: {exc}") from exc
    if not isinstance(loaded, dict):
        raise MetricsInputError(f"{system} result for {case_id} is not a mapping")

    raw = loaded
    status = raw.get("status")
    if status not in (STATUS_SUCCEEDED, STATUS_FAILED):
        raise MetricsInputError(f"{system} result for {case_id}: invalid status {status!r}")

    score: float | None = None
    if status == STATUS_SUCCEEDED:
        scoring = raw.get("scoring")
        if not isinstance(scoring, dict):
            raise MetricsInputError(
                f"{system} result for {case_id}: succeeded without a scoring summary"
            )
        score_value = scoring.get("score")
        if not isinstance(score_value, (int, float)) or isinstance(score_value, bool):
            raise MetricsInputError(f"{system} result for {case_id}: missing score")
        if not (0 <= score_value <= 100):
            raise MetricsInputError(
                f"{system} result for {case_id}: impossible score {score_value!r}"
            )
        score = float(score_value)

    runtime = raw.get("runtime")
    rt = runtime if isinstance(runtime, dict) else {}
    error = raw.get("error")
    error_kind = error.get("kind") if isinstance(error, dict) else None
    result_identity = raw.get("result_identity")
    return SystemCaseRecord(
        case_id=case_id,
        status=str(status),
        score=score,
        result_identity=str(result_identity) if isinstance(result_identity, str) else None,
        error_kind=error_kind if isinstance(error_kind, str) else None,
        latency_ms=_float_or_none(rt.get("latency_ms"), f"{system} result {case_id}"),
        input_tokens=_int_or_none(rt.get("input_tokens"), f"{system} result {case_id}"),
        output_tokens=_int_or_none(rt.get("output_tokens"), f"{system} result {case_id}"),
        estimated_cost=_float_or_none(rt.get("estimated_cost"), f"{system} result {case_id}"),
        citations=_citations_from(raw),
    )


def _build_records(
    manifest: dict[str, Any],
    run_dir: Path,
) -> tuple[dict[str, SystemCaseRecord], dict[str, SystemCaseRecord]]:
    baseline: dict[str, SystemCaseRecord] = {}
    repoguard: dict[str, SystemCaseRecord] = {}
    results = manifest["results"]
    evidence = manifest["evidence"]
    for case_id in manifest["cases"]:
        entry = results.get(case_id)
        if not isinstance(entry, dict):
            raise MetricsInputError(f"case {case_id}: no outcome recorded in the manifest")
        if case_id not in evidence:
            error = entry.get("error")
            if isinstance(error, dict) and isinstance(error.get("kind"), str):
                kind = error["kind"]
            else:
                kind = "setup_failure"
            for store in (baseline, repoguard):
                store[case_id] = SystemCaseRecord(
                    case_id=case_id,
                    status=STATUS_NOT_PRESENT,
                    score=None,
                    result_identity=None,
                    error_kind=kind,
                )
            continue
        for system, store in (("baseline", baseline), ("repoguard", repoguard)):
            outcome = entry.get(system)
            if not isinstance(outcome, dict):
                store[case_id] = SystemCaseRecord(
                    case_id=case_id,
                    status=STATUS_NOT_PRESENT,
                    score=None,
                    result_identity=None,
                    error_kind=None,
                )
                continue
            store[case_id] = _read_result(run_dir, case_id, system, outcome)
    return baseline, repoguard


def _load_ground_truth_artifacts(
    ground_truth_path: Path,
    manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Consensus artifacts by case id, fully validated against the run."""
    candidates: list[Path] = []
    if ground_truth_path.is_dir():
        candidates = sorted(p for p in ground_truth_path.glob("*-ground-truth.yaml"))
    else:
        candidates = [ground_truth_path]

    problems: list[str] = []
    artifacts: dict[str, dict[str, Any]] = {}
    for path in candidates:
        loaded: object
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            problems.append(f"ground truth {path} unreadable: {exc}")
            continue
        if not isinstance(loaded, dict):
            problems.append(f"ground truth {path} is not a mapping")
            continue
        case_id = loaded.get("case_id")
        if isinstance(case_id, str):
            if case_id in artifacts:
                problems.append(f"duplicate ground truth for case {case_id}")
                continue
        validation = validate_ground_truth_artifact(
            loaded,
            dataset_version=str(manifest["dataset"]["version"]),
            rubric_version=str(manifest["rubric_version"]),
            evidence_identity=(
                manifest["evidence"].get(case_id) if isinstance(case_id, str) else None
            ),
            run_case_ids={str(item) for item in manifest["cases"]},
        )
        problems += validation
        if not validation and isinstance(case_id, str):
            artifacts[case_id] = loaded
    if not ground_truth_path.is_dir() and not candidates[0].is_file():
        problems.append(f"ground truth path not found: {ground_truth_path}")
    return artifacts, problems


def _load_evidence_ids(evidence_dir: Path, run_case_ids: set[str]) -> dict[str, set[str]]:
    if not evidence_dir.is_dir():
        raise MetricsInputError(f"evidence directory not found: {evidence_dir}")
    result: dict[str, set[str]] = {}
    for case_id in run_case_ids:
        primary = evidence_dir / case_id / "evidence.yaml"
        alternative = evidence_dir / f"{case_id}-evidence.yaml"
        path = primary if primary.is_file() else alternative
        if not path.is_file():
            continue
        loaded: object
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise MetricsInputError(f"evidence artifact {path} unreadable: {exc}") from exc
        if not isinstance(loaded, dict):
            raise MetricsInputError(f"evidence artifact {path} is not a mapping")
        items = loaded.get("items")
        if not isinstance(items, list):
            raise MetricsInputError(f"evidence artifact {path} has no items")
        ids = {
            str(item["evidence_id"])
            for item in items
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        }
        result[case_id] = ids
    return result


def _load_mapping(path: Path, kind: str) -> dict[str, Any]:
    if path is None or not path.is_file():
        raise MetricsInputError(f"{kind} input not found: {path}")
    loaded: object
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MetricsInputError(f"{kind} input {path} unreadable: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise MetricsInputError(f"{kind} input {path} must be a mapping")
    return dict(loaded)


def _findings_or_raise(path: Path, label: str) -> dict[str, list[findings.Finding]]:
    if path is None or not path.is_file():
        raise MetricsInputError(f"{label} input not found: {path}")
    try:
        loaded = findings.load_findings(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise MetricsInputError(f"{label} input {path} unusable: {exc}") from exc
    return loaded


def _review_minutes_of(path: Path) -> dict[str, float]:
    raw = _load_mapping(path, "--review-times")
    minutes: dict[str, float] = {}
    for case_id, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MetricsInputError(f"--review-times: invalid value for {case_id!r}")
        minutes[str(case_id)] = float(value)
    return minutes


def _primary_metric(
    system_records: dict[str, SystemCaseRecord],
    ground_truth: dict[str, dict[str, Any]] | None,
    contested: str,
) -> dict[str, Any]:
    system_scores = {
        case_id: record.score
        for case_id, record in system_records.items()
        if record.status == STATUS_SUCCEEDED and record.score is not None
    }
    entry: dict[str, Any] = {"ranking": ranking.rank_scores(system_scores)}
    if not ground_truth:
        entry.update(
            {
                "state": "unavailable",
                "rho": None,
                "n": 0,
                "note": "no ground-truth consensus artifacts were supplied",
            }
        )
        return entry
    gt_scores: dict[str, float] = {}
    for case_id, artifact in ground_truth.items():
        assessment = artifact.get("assessment")
        if not isinstance(assessment, dict):
            continue
        summary = assessment.get("summary")
        if not isinstance(summary, dict):
            continue
        score = summary.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            gt_scores[case_id] = float(score)
    contested_ids = {
        case_id
        for case_id, artifact in ground_truth.items()
        if artifact.get("status") == "contested"
    }
    entry.update(
        agreement.agreement(
            run_case_ids=list(system_records),
            system_scores=system_scores,
            gt_scores=gt_scores,
            contested_case_ids=sorted(contested_ids),
            include_contested=contested == "include",
        )
    )
    return entry


def _secondary_metrics(
    system_key: str,
    system_records: dict[str, SystemCaseRecord],
    options: ReportOptions,
    evidence_by_case: dict[str, set[str]],
    gt_findings: dict[str, list[findings.Finding]] | None,
    baseline_findings: dict[str, list[findings.Finding]] | None,
    repoguard_findings: dict[str, list[findings.Finding]] | None,
    review_minutes: dict[str, float] | None,
) -> dict[str, Any]:
    selected = set(options.metrics)
    succeeded = [record for record in system_records.values() if record.status == STATUS_SUCCEEDED]
    out: dict[str, Any] = {}
    evidence_input = evidence_by_case if evidence_by_case else None

    if "evidence_accuracy" in selected:
        out["evidence_accuracy"] = evidence_metric.system_evidence_accuracy(
            succeeded, evidence_input
        ).to_dict()

    if "critical_finding_recall" in selected or "false_positive_rate" in selected:
        system_findings = baseline_findings if system_key == "baseline" else repoguard_findings
        if "critical_finding_recall" in selected:
            out["critical_finding_recall"] = findings.critical_finding_recall(
                gt_findings, system_findings
            ).to_dict()
        if "false_positive_rate" in selected:
            out["false_positive_rate"] = findings.false_positive_rate_system(
                system_findings,
                evidence_input,
            ).to_dict()

    if "assessment_time" in selected:
        out["assessment_time"] = {
            "system": timing.system_assessment_time(succeeded).to_dict(),
            "model_latency": timing.model_latency(succeeded).to_dict(),
            "human_review_time": timing.human_review_time(review_minutes).to_dict(),
        }

    if "runtime" in selected:
        out["runtime"] = {
            "input_tokens": runtime_metric.input_tokens(succeeded).to_dict(),
            "output_tokens": runtime_metric.output_tokens(succeeded).to_dict(),
        }

    if "cost" in selected:
        out["cost"] = cost.approximate_cost(succeeded).to_dict()
    return out


def _case_rows(
    baseline: dict[str, SystemCaseRecord],
    repoguard: dict[str, SystemCaseRecord],
    ground_truth: dict[str, dict[str, Any]] | None,
    evidence_by_case: dict[str, set[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_id in sorted(set(baseline) | set(repoguard)):
        baseline_record = baseline.get(case_id)
        repoguard_record = repoguard.get(case_id)
        gt = ground_truth.get(case_id) if ground_truth else None
        row: dict[str, Any] = {"case_id": case_id}
        if baseline_record is not None:
            row["baseline"] = baseline_record.to_dict()
            row["baseline"]["evidence"] = evidence_metric.evidence_accuracy(
                baseline_record.citations, evidence_by_case.get(case_id)
            ).to_dict()
        if repoguard_record is not None:
            row["repoguard"] = repoguard_record.to_dict()
            row["repoguard"]["evidence"] = evidence_metric.evidence_accuracy(
                repoguard_record.citations, evidence_by_case.get(case_id)
            ).to_dict()
        if gt is not None:
            score = (
                gt["assessment"]["summary"]["score"]
                if isinstance(gt.get("assessment"), dict)
                and isinstance(gt["assessment"].get("summary"), dict)
                else None
            )
            row["ground_truth"] = {
                "status": gt.get("status"),
                "score": score,
                "identity": gt.get("ground_truth_identity"),
            }
        delta: float | None = None
        if (
            baseline_record is not None
            and baseline_record.score is not None
            and repoguard_record is not None
            and repoguard_record.score is not None
        ):
            delta = round(repoguard_record.score - baseline_record.score, 4)
        row["score_delta"] = delta
        rows.append(row)
    return rows


def calculate_report(
    run_dir: Path,
    ground_truth_path: Path | None,
    options: ReportOptions | None = None,
) -> dict[str, Any]:
    options = options or ReportOptions()
    if not run_dir.is_dir():
        raise MetricsInputError(f"run directory not found: {run_dir}")
    problems = validate_run(run_dir)
    if problems:
        raise MetricsInputError("benchmark run failed validation:\n" + "\n".join(problems))
    manifest, error = load_run_manifest(run_dir)
    if manifest is None or error:
        raise MetricsInputError(f"run manifest unavailable: {error}")

    baseline, repoguard = _build_records(manifest, run_dir)
    run_case_ids = {str(item) for item in manifest["cases"]}

    ground_truth_artifacts: dict[str, dict[str, Any]] | None = None
    ground_truth_problems: list[str] = []
    if ground_truth_path is not None:
        ground_truth_artifacts, ground_truth_problems = _load_ground_truth_artifacts(
            ground_truth_path, manifest
        )
        if ground_truth_problems:
            raise MetricsInputError(
                "ground-truth inputs failed validation:\n" + "\n".join(ground_truth_problems)
            )

    evidence_by_case = (
        _load_evidence_ids(options.evidence_dir, run_case_ids)
        if options.evidence_dir is not None
        else {}
    )

    review_minutes = (
        _review_minutes_of(options.review_times) if options.review_times is not None else None
    )
    if review_minutes and not set(review_minutes).issubset(run_case_ids):
        unknown = sorted(set(review_minutes) - run_case_ids)
        raise MetricsInputError(
            f"--review-times references cases not in the run: {', '.join(unknown)}"
        )

    gt_findings = (
        _findings_or_raise(options.ground_truth_findings, "--gt-findings")
        if options.ground_truth_findings is not None
        else None
    )
    baseline_findings = (
        _findings_or_raise(options.baseline_findings, "--baseline-findings")
        if options.baseline_findings is not None
        else None
    )
    repoguard_findings = (
        _findings_or_raise(options.repoguard_findings, "--repoguard-findings")
        if options.repoguard_findings is not None
        else None
    )
    if gt_findings and not set(gt_findings).issubset(run_case_ids):
        raise MetricsInputError(
            "--gt-findings references cases not in the run: "
            + ", ".join(sorted(set(gt_findings) - run_case_ids))
        )
    for label, mapping in (
        ("--baseline-findings", baseline_findings),
        ("--repoguard-findings", repoguard_findings),
    ):
        if mapping and not set(mapping).issubset(run_case_ids):
            raise MetricsInputError(
                f"{label} references cases not in the run: "
                + ", ".join(sorted(set(mapping) - run_case_ids))
            )

    paired = compare.pair_cases(baseline, repoguard, sorted(run_case_ids))
    gt_identities = {
        case_id: artifact["ground_truth_identity"]
        for case_id, artifact in sorted((ground_truth_artifacts or {}).items())
        if isinstance(artifact.get("ground_truth_identity"), str)
    }

    payload: dict[str, Any] = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "system": SYSTEM_ID,
        "metrics_version": __version__,
        "metrics_config": {
            "contested": options.contested,
            "metrics": list(options.metrics),
        },
        "inputs": {
            "run_identity": manifest.get("run_identity"),
            "dataset": manifest.get("dataset"),
            "rubric_version": manifest.get("rubric_version"),
            "ground_truth": (
                {
                    "case_count": len(ground_truth_artifacts or {}),
                    "contested_cases": sorted(
                        case_id
                        for case_id, artifact in (ground_truth_artifacts or {}).items()
                        if artifact.get("status") == "contested"
                    ),
                    "identities": gt_identities,
                    "aggregate_identity": ground_truth_identities_identity(gt_identities),
                }
                if ground_truth_artifacts is not None
                else None
            ),
        },
        "primary_metric": {
            "statistic": "spearman-rank-correlation",
            "tie_method": "average-rank",
            "decision_record": "docs/decisions/0002-ranking-agreement.md",
            "baseline": _primary_metric(baseline, ground_truth_artifacts, options.contested),
            "repoguard": _primary_metric(repoguard, ground_truth_artifacts, options.contested),
        },
        "secondary_metrics": {
            "baseline": _secondary_metrics(
                "baseline",
                baseline,
                options,
                evidence_by_case,
                gt_findings,
                baseline_findings,
                repoguard_findings,
                review_minutes,
            ),
            "repoguard": _secondary_metrics(
                "repoguard",
                repoguard,
                options,
                evidence_by_case,
                gt_findings,
                baseline_findings,
                repoguard_findings,
                review_minutes,
            ),
        },
        "cases": _case_rows(baseline, repoguard, ground_truth_artifacts, evidence_by_case),
        "compare_summary": compare.compare_summary(paired),
    }
    report = compose_report(payload)
    report["generated_at"] = datetime.now(UTC).isoformat()
    return report


def compare_report(run_dir: Path) -> dict[str, Any]:
    """System-vs-system comparison; no ground truth required."""
    if not run_dir.is_dir():
        raise MetricsInputError(f"run directory not found: {run_dir}")
    problems = validate_run(run_dir)
    if problems:
        raise MetricsInputError("benchmark run failed validation:\n" + "\n".join(problems))
    manifest, error = load_run_manifest(run_dir)
    if manifest is None or error:
        raise MetricsInputError(f"run manifest unavailable: {error}")

    baseline, repoguard = _build_records(manifest, run_dir)
    run_case_ids = sorted({str(item) for item in manifest["cases"]})
    paired = compare.pair_cases(baseline, repoguard, run_case_ids)
    return {
        "system": SYSTEM_ID,
        "metrics_version": __version__,
        "inputs": {
            "run_identity": manifest.get("run_identity"),
            "dataset": manifest.get("dataset"),
            "rubric_version": manifest.get("rubric_version"),
        },
        "paired_cases": [entry.to_dict() for entry in paired],
        "summary": compare.compare_summary(paired),
    }
