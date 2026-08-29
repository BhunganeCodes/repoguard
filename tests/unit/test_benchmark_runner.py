"""Benchmark runner: orchestration, isolation, failures, and determinism."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from benchmark_helpers import (
    case_dict,
    failing_provider_for,
    make_case,
    mock_config,
    paired_providers,
    write_dataset,
    write_evidence,
    write_snapshot_store,
)

from evaluation.benchmark.cases import dataset_identity, load_dataset
from evaluation.benchmark.errors import RunExistsError
from evaluation.benchmark.manifest import validate_run
from evaluation.benchmark.models import STATUS_FAILED, STATUS_SUCCEEDED, ExecutedCase
from evaluation.benchmark.paths import run_dir
from evaluation.benchmark.runner import (
    ALL_EVALUATORS,
    RunInput,
    build_run_input,
    execute_run,
)
from evaluation.evidence.models import EvidenceArtifact
from evaluation.scoring.rubric import RUBRIC_VERSION
from evaluation.snapshot.manifest import load_manifest


@dataclass
class RunFixture:
    run: RunInput
    executed: list[ExecutedCase]
    evidence: dict[str, EvidenceArtifact]

    @property
    def run_path(self) -> Path:
        return run_dir(self.run.results_dir, self.run.run_id)


def make_fixture(
    tmp_path: Path,
    *,
    case_ids: list[str] | tuple[str, ...] = ("C001",),
    evaluators: frozenset[str] = ALL_EVALUATORS,
    run_id: str = "run-x",
) -> RunFixture:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cases = [make_case(case_id) for case_id in case_ids]
    dataset_path = write_dataset(
        tmp_path / "dataset.yaml", [case_dict(case_id) for case_id in case_ids]
    )
    dataset = load_manifest(dataset_path)
    store = tmp_path / "store"
    evidence: dict[str, EvidenceArtifact] = {}
    for case in cases:
        snapshot_root = write_snapshot_store(store, case)
        evidence[case.candidate_id] = write_evidence(snapshot_root, case)
    provider = paired_providers(evidence[case_ids[0]])
    run = build_run_input(
        dataset=dataset,
        dataset_identity=dataset_identity(dataset_path),
        cases=cases,
        store=store,
        provider=provider,
        config=mock_config(),
        evaluators=evaluators,
        results_dir=tmp_path / "out",
        run_id=run_id,
    )
    executed = execute_run(run)
    return RunFixture(run=run, executed=executed, evidence=evidence)


def test_end_to_end_paired_benchmark_run(tmp_path: Path) -> None:
    """Integration: dataset -> snapshot -> evidence -> baseline+RepoGuard -> scores."""
    fixture = make_fixture(tmp_path)
    (case,) = fixture.executed
    assert case.case_id == "C001"
    assert case.status == STATUS_SUCCEEDED
    assert case.baseline is not None and case.baseline.status == STATUS_SUCCEEDED
    assert case.repoguard is not None and case.repoguard.status == STATUS_SUCCEEDED
    assert case.baseline.score == 50.0
    assert case.repoguard.score == 50.0
    assert case.delta == 0.0
    assert case.error is None

    # Both systems were scored by the shared scorer for a shared evidence set.
    assert case.evidence_identity == fixture.evidence["C001"].evidence_identity
    assert fixture.run_path.is_dir()
    manifest = yaml.safe_load((fixture.run_path / "run-manifest.yaml").read_text("utf-8"))
    assert manifest["run_identity"].startswith("repoguard-benchmark-v1:")
    assert validate_run(fixture.run_path) == []


def _load_result(run_path: Path, system: str, case_id: str) -> dict:
    return yaml.safe_load((run_path / system / case_id / "result.yaml").read_text("utf-8"))


def test_shared_evidence_identity_across_systems(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    baseline = _load_result(fixture.run_path, "baseline", "C001")
    repoguard = _load_result(fixture.run_path, "repoguard", "C001")
    assert baseline["evidence_identity"] == repoguard["evidence_identity"]
    assert baseline["evidence_identity"] == fixture.evidence["C001"].evidence_identity


def test_shared_scorer_enforced(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    baseline = _load_result(fixture.run_path, "baseline", "C001")
    repoguard = _load_result(fixture.run_path, "repoguard", "C001")
    assert baseline["rubric_version"] == RUBRIC_VERSION
    assert repoguard["rubric_version"] == RUBRIC_VERSION
    assert baseline["scoring"]["score"] == repoguard["scoring"]["score"] == 50.0


def test_deterministic_run_identity_across_runs(tmp_path: Path) -> None:
    one = make_fixture(tmp_path, run_id="run-one")
    two = make_fixture(tmp_path / "again", run_id="run-two")
    first_manifest = yaml.safe_load((one.run_path / "run-manifest.yaml").read_text("utf-8"))
    second_manifest = yaml.safe_load((two.run_path / "run-manifest.yaml").read_text("utf-8"))
    assert first_manifest["run_identity"] == second_manifest["run_identity"]
    assert first_manifest["results"] == second_manifest["results"]

    def _without_runtime(path: Path) -> dict:
        data = yaml.safe_load(path.read_text("utf-8"))
        data.pop("runtime", None)
        return data

    # Semantic content is byte-identical; only runtime metadata may vary.
    first_result = _without_runtime(one.run_path / "repoguard" / "C001" / "result.yaml")
    second_result = _without_runtime(two.run_path / "repoguard" / "C001" / "result.yaml")
    assert first_result == second_result
    assert first_result["result_identity"] == second_result["result_identity"]


def test_baseline_failure_recorded_without_score(tmp_path: Path) -> None:
    cases = [make_case("C001")]
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    dataset = load_manifest(dataset_path)
    store = tmp_path / "store"
    snapshot_root = write_snapshot_store(store, cases[0])
    evidence = write_evidence(snapshot_root, cases[0])
    run = build_run_input(
        dataset=dataset,
        dataset_identity=dataset_identity(dataset_path),
        cases=cases,
        store=store,
        provider=failing_provider_for(evidence, "baseline"),
        config=mock_config(),
        evaluators=ALL_EVALUATORS,
        results_dir=tmp_path / "out",
        run_id="run-x",
    )
    (case,) = execute_run(run)
    assert case.status == STATUS_FAILED
    assert case.baseline is not None and case.baseline.status == STATUS_FAILED
    assert case.baseline.score is None
    assert case.repoguard is not None and case.repoguard.status == STATUS_SUCCEEDED
    assert case.repoguard.score == 50.0
    assert case.delta is None
    assert case.error is not None and case.error.kind == "provider_error"


def test_repoguard_failure_recorded_without_score(tmp_path: Path) -> None:
    cases = [make_case("C001")]
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    dataset = load_manifest(dataset_path)
    store = tmp_path / "store"
    snapshot_root = write_snapshot_store(store, cases[0])
    evidence = write_evidence(snapshot_root, cases[0])
    run = build_run_input(
        dataset=dataset,
        dataset_identity=dataset_identity(dataset_path),
        cases=cases,
        store=store,
        provider=failing_provider_for(evidence, "repoguard"),
        config=mock_config(),
        evaluators=ALL_EVALUATORS,
        results_dir=tmp_path / "out",
        run_id="run-x",
    )
    (case,) = execute_run(run)
    assert case.status == STATUS_FAILED
    assert case.baseline is not None and case.baseline.status == STATUS_SUCCEEDED
    assert case.repoguard is not None and case.repoguard.status == STATUS_FAILED
    assert case.repoguard.score is None
    assert case.error is not None and case.error.kind == "provider_error"


def test_both_failures_never_fabricate_scores(tmp_path: Path) -> None:
    cases = [make_case("C001")]
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    dataset = load_manifest(dataset_path)
    store = tmp_path / "store"
    snapshot_root = write_snapshot_store(store, cases[0])
    write_evidence(snapshot_root, cases[0])
    both_fail = type(
        "BothFail",
        (),
        {
            "name": "mock",
            "generate": lambda self, request: (_ for _ in ()).throw(RuntimeError("boom")),
            "public_config": lambda self: {"mode": "mock"},
        },
    )()
    run = build_run_input(
        dataset=dataset,
        dataset_identity=dataset_identity(dataset_path),
        cases=cases,
        store=store,
        provider=both_fail,
        config=mock_config(),
        evaluators=ALL_EVALUATORS,
        results_dir=tmp_path / "out",
        run_id="run-x",
    )
    (case,) = execute_run(run)
    assert case.status == STATUS_FAILED
    assert case.baseline is not None and case.baseline.score is None
    assert case.repoguard is not None and case.repoguard.score is None
    assert case.error is not None and case.error.kind == "provider_error"


def test_run_never_overwrites_previous_run(tmp_path: Path) -> None:
    one = make_fixture(tmp_path, run_id="fixed")
    manifest_path = one.run_path / "run-manifest.yaml"
    original = manifest_path.read_text("utf-8")
    with pytest.raises(RunExistsError):
        make_fixture(tmp_path, run_id="fixed")
    assert manifest_path.read_text("utf-8") == original
    assert one.run_path.is_dir()


def test_evaluator_selection_only_baseline(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path, evaluators=frozenset({"baseline"}))
    (case,) = fixture.executed
    assert case.repoguard is None
    assert not (fixture.run_path / "repoguard").exists()
    assert (fixture.run_path / "baseline" / "C001" / "result.yaml").is_file()
    manifest_path = fixture.run_path / "run-manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text("utf-8"))
    assert manifest["evaluators"]["baseline"]["enabled"] is True
    assert manifest["evaluators"]["repoguard"]["enabled"] is False


def test_missing_snapshot_fails_case_but_run_continues(tmp_path: Path) -> None:
    cases = [make_case("C001"), make_case("C002")]
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001"), case_dict("C002")])
    dataset = load_dataset(dataset_path)
    store = tmp_path / "store"
    # Only C002 gets a snapshot; C001 stays missing.
    snapshot_root = write_snapshot_store(store, cases[1])
    evidence = write_evidence(snapshot_root, cases[1])
    provider = paired_providers(evidence)
    run = build_run_input(
        dataset=dataset,
        dataset_identity=dataset_identity(dataset_path),
        cases=cases,
        store=store,
        provider=provider,
        config=mock_config(),
        evaluators=ALL_EVALUATORS,
        results_dir=tmp_path / "out",
        run_id="run-x",
    )
    executed = execute_run(run)
    by_id = {case.case_id: case for case in executed}
    assert by_id["C001"].status == STATUS_FAILED
    assert by_id["C001"].error is not None and by_id["C001"].error.kind == "snapshot_missing"
    assert by_id["C001"].baseline is None and by_id["C001"].repoguard is None
    assert by_id["C002"].status == STATUS_SUCCEEDED
    run_path = run_dir(run.results_dir, run.run_id)
    manifest = yaml.safe_load((run_path / "run-manifest.yaml").read_text("utf-8"))
    assert manifest["results"]["C001"]["status"] == STATUS_FAILED
    assert validate_run(run_path) == []
