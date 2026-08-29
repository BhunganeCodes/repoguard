"""Metrics report: composition, secondary metrics, validation, identity."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from metrics_helpers import (
    CaseSpec,
    OutSpec,
    ground_truth_artifact,
    materialize_run,
    write_ground_truth,
)
from scoring_helpers import make_evidence

from evaluation.benchmark.manifest import validate_run
from evaluation.ground_truth.serialize import ground_truth_identity
from evaluation.metrics import calculate_report, compare_report
from evaluation.metrics.errors import MetricsInputError
from evaluation.metrics.report import ReportOptions
from evaluation.metrics.serialize import recompute_identity, write_report
from evaluation.metrics.validate import validate_report


def _run(tmp_path: Path, specs: list[CaseSpec], **kwargs) -> Path:
    return materialize_run(tmp_path, specs, **kwargs)


def _gt_for_dir(tmp_path: Path, cases: list[tuple[str, int]], *, status: str = "consensus") -> Path:
    directory = tmp_path / "gt"
    write_ground_truth(
        directory,
        [
            ground_truth_artifact(make_evidence(case_id), score=score, status=status)
            for case_id, score in cases
        ],
    )
    return directory


def test_primary_metric_perfect_agreement(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [
            CaseSpec("C001", baseline=OutSpec(score=1), repoguard=OutSpec(score=1)),
            CaseSpec("C002", baseline=OutSpec(score=2), repoguard=OutSpec(score=2)),
            CaseSpec("C003", baseline=OutSpec(score=3), repoguard=OutSpec(score=3)),
        ],
    )
    report = calculate_report(run, _gt_for_dir(tmp_path, [("C001", 1), ("C002", 2), ("C003", 3)]))
    for system in ("baseline", "repoguard"):
        primary = report["primary_metric"][system]
        assert primary["state"] == "available"
        assert primary["rho"] == pytest.approx(1.0)
        assert primary["n"] == 3
    assert report["schema_version"] == 1
    assert report["system"] == "metrics"


def test_primary_metric_unavailable_without_ground_truth(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(score=2))])
    report = calculate_report(run, None)
    primary = report["primary_metric"]["baseline"]
    assert primary["state"] == "unavailable"
    assert "no ground-truth consensus artifacts were supplied" in primary["note"]
    # Rankings are still produced.
    assert primary["ranking"] == [{"case_id": "C001", "score": 50.0, "rank": 1.0}]


def test_failed_case_no_fabricated_score(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [
            CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec()),
            CaseSpec("C002", baseline=OutSpec(status="failed"), repoguard=OutSpec(score=4)),
        ],
    )
    report = calculate_report(run, None)
    rows = {row["case_id"]: row for row in report["cases"]}
    assert rows["C002"]["baseline"]["status"] == "failed"
    assert rows["C002"]["baseline"]["score"] is None
    assert rows["C002"]["baseline"]["error_kind"] == "provider_error"
    assert rows["C002"]["score_delta"] is None
    # The failed baseline case never enters the comparison scores.
    assert report["compare_summary"]["repoguard_scored_only"] == 1
    # Failed cases are absent from the system scores used for ranking.
    assert report["primary_metric"]["baseline"]["ranking"] == [
        {"case_id": "C001", "score": 50.0, "rank": 1.0}
    ]
    assert {entry["case_id"] for entry in report["primary_metric"]["repoguard"]["ranking"]} == {
        "C001",
        "C002",
    }


def test_missing_ground_truth_is_exclusion(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [
            CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2)),
            CaseSpec("C002", baseline=OutSpec(score=4), repoguard=OutSpec(score=4)),
        ],
    )
    # Only C001 has ground truth: agreement is undefined (n=1), exclusion recorded.
    report = calculate_report(run, _gt_for_dir(tmp_path, [("C001", 2)]))
    primary = report["primary_metric"]["baseline"]
    assert primary["n"] == 1
    reasons = {entry["case_id"]: entry["reason"] for entry in primary["excluded"]}
    assert "no ground-truth consensus for the case" in reasons["C002"]


def test_compare_without_ground_truth(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [
            CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=3)),
            CaseSpec("C002", baseline=OutSpec(score=4), repoguard=OutSpec(score=4)),
        ],
    )
    result = compare_report(run)
    summary = result["summary"]
    assert summary["paired_cases"] == 2
    assert summary["both_scored"] == 2
    deltas = {entry["case_id"]: entry["score_delta"] for entry in result["paired_cases"]}
    assert deltas["C001"] == 25.0
    assert deltas["C002"] == 0.0


def test_runtime_and_cost_metrics(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [
            CaseSpec(
                "C001",
                baseline=OutSpec(
                    score=2,
                    latency_ms=120.0,
                    input_tokens=30,
                    output_tokens=60,
                    estimated_cost=0.0042,
                ),
                repoguard=OutSpec(score=2),
            )
        ],
    )
    report = calculate_report(run, None)
    baseline_metrics = report["secondary_metrics"]["baseline"]
    repoguard_metrics = report["secondary_metrics"]["repoguard"]

    assert baseline_metrics["runtime"]["input_tokens"]["value"] == 30
    assert baseline_metrics["runtime"]["output_tokens"]["value"] == 60
    assert baseline_metrics["cost"]["value"] == pytest.approx(0.0042)
    assert baseline_metrics["assessment_time"]["model_latency"]["value"] == pytest.approx(120.0)
    assert baseline_metrics["assessment_time"]["system"]["state"] == "unavailable"

    # RepoGuard recorded nothing: runtime/cost stay unavailable, not zero.
    assert repoguard_metrics["runtime"]["input_tokens"]["state"] == "unavailable"
    assert repoguard_metrics["cost"]["state"] == "unavailable"
    assert repoguard_metrics["assessment_time"]["model_latency"]["state"] == "unavailable"


def test_evidence_accuracy_with_and_without_evidence_store(tmp_path: Path) -> None:
    store = tmp_path / "store"
    run = _run(
        tmp_path,
        [
            CaseSpec(
                "C001",
                baseline=OutSpec(score=2, extra_citations=("fabricated.id",)),
                repoguard=OutSpec(score=2),
            ),
        ],
        evidence_store=store,
    )
    # Without evidence input the metric is unavailable, never estimated.
    no_evidence = calculate_report(run, None)
    assert (
        no_evidence["secondary_metrics"]["baseline"]["evidence_accuracy"]["state"] == "unavailable"
    )

    with_evidence = calculate_report(run, None, ReportOptions(evidence_dir=store))
    assert (
        with_evidence["secondary_metrics"]["repoguard"]["evidence_accuracy"]["state"] == "available"
    )
    assert with_evidence["secondary_metrics"]["repoguard"]["evidence_accuracy"][
        "value"
    ] == pytest.approx(1.0)
    # The fabricated citation is unverifiable and lowers accuracy.
    baseline_accuracy = with_evidence["secondary_metrics"]["baseline"]["evidence_accuracy"]
    assert baseline_accuracy["state"] == "available"
    assert baseline_accuracy["value"] < 1.0
    assert baseline_accuracy["covered"] > 0


def test_finding_metrics_pending_by_default(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec())])
    report = calculate_report(run, None)
    for system in ("baseline", "repoguard"):
        assert report["secondary_metrics"][system]["critical_finding_recall"]["state"] == "pending"
        assert report["secondary_metrics"][system]["false_positive_rate"]["state"] == "pending"


def test_finding_metrics_with_inputs(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2))],
        evidence_store=tmp_path / "store",
    )
    gt_path = tmp_path / "gt-findings.yaml"
    gt_path.write_text(
        yaml.safe_dump(
            {
                "C001": [
                    {"claim": "missing tests", "citations": ["testing.test_files"]},
                    {"claim": "missing locking", "citations": ["dependencies.lockfiles"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    base_path = tmp_path / "baseline-findings.yaml"
    base_path.write_text(
        yaml.safe_dump(
            {"C001": [{"claim": "missing locking", "citations": ["dependencies.lockfiles"]}]}
        ),
        encoding="utf-8",
    )
    repoguard_path = tmp_path / "repoguard-findings.yaml"
    repoguard_path.write_text(
        yaml.safe_dump({"C001": [{"claim": "unrelated", "citations": ["fabricated.id"]}]}),
        encoding="utf-8",
    )

    report = calculate_report(
        run,
        None,
        ReportOptions(
            evidence_dir=tmp_path / "store",
            ground_truth_findings=gt_path,
            baseline_findings=base_path,
            repoguard_findings=repoguard_path,
        ),
    )
    baseline_recall = report["secondary_metrics"]["baseline"]["critical_finding_recall"]
    assert baseline_recall["state"] == "available"
    assert baseline_recall["value"] == pytest.approx(0.5)
    # RepoGuard recalled none of the human-flagged findings.
    assert report["secondary_metrics"]["repoguard"]["critical_finding_recall"][
        "value"
    ] == pytest.approx(0.0)

    baseline_fpr = report["secondary_metrics"]["baseline"]["false_positive_rate"]
    assert baseline_fpr["value"] == pytest.approx(0.0)  # supported by evidence
    repoguard_fpr = report["secondary_metrics"]["repoguard"]["false_positive_rate"]
    assert repoguard_fpr["value"] == pytest.approx(1.0)  # unsupported/unmatched


def test_findings_input_fails_closed_when_missing(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec())])
    with pytest.raises(MetricsInputError, match="--gt-findings input not found"):
        calculate_report(run, None, ReportOptions(ground_truth_findings=tmp_path / "nope.yaml"))
    with pytest.raises(MetricsInputError, match="--gt-findings input .* unusable"):
        broken = tmp_path / "broken.yaml"
        broken.write_text("not: [valid", encoding="utf-8")
        calculate_report(run, None, ReportOptions(ground_truth_findings=broken))


def test_review_times_only_from_explicit_input(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec())])
    report = calculate_report(run, None)
    for system in ("baseline", "repoguard"):
        assert (
            report["secondary_metrics"][system]["assessment_time"]["human_review_time"]["state"]
            == "unavailable"
        )

    times = tmp_path / "review-times.yaml"
    times.write_text(yaml.safe_dump({"C001": 32.0}), encoding="utf-8")
    report = calculate_report(run, None, ReportOptions(review_times=times))
    for system in ("baseline", "repoguard"):
        value = report["secondary_metrics"][system]["assessment_time"]["human_review_time"]
        assert value["state"] == "available"
        assert value["value"] == pytest.approx(32.0)


def test_validation_fail_closed_unknown_ground_truth_case(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec())])
    gt = _gt_for_dir(tmp_path, [("C099", 2)])
    with pytest.raises(MetricsInputError, match="unknown case"):
        calculate_report(run, gt)


def test_validation_fail_closed_duplicate_ground_truth(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec())])
    artifact = ground_truth_artifact(make_evidence("C001"), score=2)
    directory = tmp_path / "gt"
    directory.mkdir()
    (directory / "a-ground-truth.yaml").write_text(
        yaml.safe_dump(artifact, sort_keys=False), encoding="utf-8"
    )
    (directory / "b-ground-truth.yaml").write_text(
        yaml.safe_dump(artifact, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(MetricsInputError, match="duplicate ground truth"):
        calculate_report(run, directory)


def test_validation_fail_closed_impossible_ground_truth_score(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec())])
    artifact = ground_truth_artifact(make_evidence("C001"), score=2)
    artifact["assessment"]["summary"]["score"] = 150.0
    artifact["ground_truth_identity"] = ground_truth_identity(artifact)
    directory = tmp_path / "gt"
    write_ground_truth(directory, [artifact])
    with pytest.raises(MetricsInputError, match="impossible ground truth score"):
        calculate_report(run, directory)


def test_validation_fail_closed_tampered_result(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2))])
    result_path = run / "baseline" / "C001" / "result.yaml"
    raw = yaml.safe_load(result_path.read_text("utf-8"))
    raw["scoring"]["score"] = 99.0
    result_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(MetricsInputError, match="failed validation"):
        calculate_report(run, None)
    with pytest.raises(MetricsInputError, match="failed validation"):
        compare_report(run)


def test_materialized_runs_pass_benchmark_validation(tmp_path: Path) -> None:
    run = _run(
        tmp_path,
        [
            CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=3)),
            CaseSpec("C002", baseline=OutSpec(status="failed"), repoguard=OutSpec(score=1)),
            CaseSpec("C003", setup_failure="snapshot_missing"),
        ],
    )
    assert validate_run(run) == []


def test_finding_input_rejects_unknown_case(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(), repoguard=OutSpec())])
    path = tmp_path / "findings.yaml"
    path.write_text(
        yaml.safe_dump({"C999": [{"claim": "x", "citations": ["a.b"]}]}), encoding="utf-8"
    )
    with pytest.raises(MetricsInputError, match="references cases not in the run"):
        calculate_report(run, None, ReportOptions(ground_truth_findings=path))


def test_report_identity_is_deterministic_and_semantic(tmp_path: Path) -> None:
    one = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2))])
    two = _run(
        tmp_path / "again",
        [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2))],
    )
    report_one = calculate_report(one, None)
    report_two = calculate_report(two, None)
    assert report_one["metrics_identity"] == report_two["metrics_identity"]
    assert validate_report(report_one) == []
    # Timestamps never affect the identity.
    report_one["generated_at"] = "different"
    assert recompute_identity(report_one) == report_one["metrics_identity"]


def test_validation_fail_closed_report_identity(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2))])
    report = calculate_report(run, None)
    report["primary_metric"]["baseline"]["rho"] = 0.99
    assert validate_report(report) != []


def test_secondary_metric_selection(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2))])
    report = calculate_report(run, None, ReportOptions(metrics=("cost",)))
    baseline_metrics = report["secondary_metrics"]["baseline"]
    assert list(baseline_metrics) == ["cost"]
    assert report["metrics_config"]["metrics"] == ["cost"]


def test_write_and_read_report_roundtrip(tmp_path: Path) -> None:
    run = _run(tmp_path, [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=2))])
    report = calculate_report(run, None)
    path = tmp_path / "report.yaml"
    write_report(path, report)
    from evaluation.metrics.serialize import read_report

    loaded = read_report(path)
    assert loaded == report
    assert validate_report(loaded) == []
