"""Run manifest composition and full-run validation."""

from __future__ import annotations

import yaml
from benchmark_helpers import case_dict, make_case, mock_config, write_dataset, write_snapshot_store
from test_benchmark_runner import make_fixture

from evaluation.benchmark._version import __version__
from evaluation.benchmark.cases import dataset_identity
from evaluation.benchmark.manifest import run_identity, validate_run
from evaluation.benchmark.paths import run_dir
from evaluation.benchmark.runner import ALL_EVALUATORS, build_run_input, execute_run
from evaluation.snapshot.manifest import load_manifest


def _manifest(fixture) -> dict:
    path = fixture.run_path / "run-manifest.yaml"
    return yaml.safe_load(path.read_text("utf-8"))


def test_manifest_records_reproduction_facts(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    manifest = _manifest(fixture)
    assert manifest["schema_version"] == 1
    assert manifest["system"] == "benchmark"
    assert manifest["benchmark_version"] == __version__
    assert manifest["run_id"] == "run-x"
    assert manifest["dataset"]["name"] == "repoguard-evaluation-dataset"
    assert manifest["dataset"]["version"] == "1.0.0"
    assert manifest["dataset"]["status"] == "frozen"
    assert manifest["dataset"]["identity"].startswith("repoguard-dataset-v1:")
    assert manifest["rubric_version"] == "1.0"
    assert manifest["cases"] == ["C001"]
    assert manifest["evidence"]["C001"] == fixture.evidence["C001"].evidence_identity
    assert manifest["evaluators"]["baseline"]["enabled"] is True
    assert manifest["evaluators"]["repoguard"]["enabled"] is True
    assert "baseline_version" in manifest["evaluators"]["baseline"]
    assert "prompt_version" in manifest["evaluators"]["baseline"]
    assert "repoguard_version" in manifest["evaluators"]["repoguard"]
    assert manifest["provider"]["provider_name"] == "mock"
    assert "created_at" in manifest
    assert "environment" in manifest
    assert manifest["results"]["C001"]["status"] == "succeeded"
    assert manifest["results"]["C001"]["baseline"]["score"] == 50.0
    assert manifest["results"]["C001"]["repoguard"]["score"] == 50.0
    assert manifest["results"]["C001"]["delta"] == 0.0
    assert manifest["results"]["C001"]["baseline"]["result_path"] == "baseline/C001/result.yaml"
    assert manifest["results"]["C001"]["repoguard"]["result_path"] == "repoguard/C001/result.yaml"


def test_run_identity_is_stable_under_runtime_variation(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    manifest = _manifest(fixture)
    mutated = dict(manifest)
    mutated["run_id"] = "a-different-label"
    mutated["created_at"] = "9999-01-01T00:00:00+00:00"
    mutated["environment"] = {"python": "3.13", "platform": "another-machine"}
    assert run_identity(mutated) == manifest["run_identity"]


def test_run_identity_changes_with_semantics(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    manifest = _manifest(fixture)
    mutated = dict(manifest)
    mutated["dataset"] = dict(manifest["dataset"], identity="repoguard-dataset-v1:different")
    assert run_identity(mutated) != manifest["run_identity"]


def test_validate_accepts_a_complete_run(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    assert validate_run(fixture.run_path) == []


def test_validate_detects_tampered_result_identity(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    result_path = fixture.run_path / "repoguard" / "C001" / "result.yaml"
    raw = yaml.safe_load(result_path.read_text("utf-8"))
    raw["result_identity"] = "repoguard-v1:" + "f" * 64
    result_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    problems = validate_run(fixture.run_path)
    assert any("identity" in problem for problem in problems)


def test_validate_detects_tampered_score(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    result_path = fixture.run_path / "baseline" / "C001" / "result.yaml"
    raw = yaml.safe_load(result_path.read_text("utf-8"))
    raw["scoring"]["score"] = 99.0
    result_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    assert any("score" in problem for problem in validate_run(fixture.run_path))


def test_validate_detects_missing_result_file(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    (fixture.run_path / "repoguard" / "C001" / "result.yaml").unlink()
    problems = validate_run(fixture.run_path)
    assert any("result missing" in problem for problem in problems)


def test_validate_reports_secret_keys(tmp_path) -> None:
    fixture = make_fixture(tmp_path)
    injected = fixture.run_path / "cases" / "C001.yaml"
    raw = yaml.safe_load(injected.read_text("utf-8"))
    raw["credentials"] = {"api_key": "sk-super-secret-value"}
    injected.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    problems = validate_run(fixture.run_path)
    assert any("secret" in problem for problem in problems)
    assert any("C001.yaml" in problem for problem in problems)


def test_validate_accepts_setup_failure_case(tmp_path) -> None:
    """A run whose case fails before evidence loads must still validate."""
    case = make_case("C001")
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    dataset = load_manifest(dataset_path)
    store = tmp_path / "store"
    write_snapshot_store(store, case)  # snapshot present, evidence missing

    from evaluation.benchmark.runner import default_secrets

    provider = type(
        "Empty",
        (),
        {
            "name": "mock",
            "generate": lambda self, request: (_ for _ in ()).throw(AssertionError("unused")),
            "public_config": lambda self: {"mode": "mock"},
        },
    )()
    run = build_run_input(
        dataset=dataset,
        dataset_identity=dataset_identity(dataset_path),
        cases=[case],
        store=store,
        provider=provider,
        config=mock_config(),
        evaluators=ALL_EVALUATORS,
        results_dir=tmp_path / "out",
        run_id="run-x",
        secrets=default_secrets(),
    )
    executed = execute_run(run)
    assert executed[0].status == "failed"
    assert executed[0].error is not None and executed[0].error.kind == "evidence_missing"
    assert validate_run(run_dir(run.results_dir, run.run_id)) == []
