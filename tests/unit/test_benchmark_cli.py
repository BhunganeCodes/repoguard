"""CLI behavior for the benchmark runner (mock providers only)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from benchmark_helpers import (
    case_dict,
    make_case,
    mock_config,
    paired_providers,
    write_dataset,
    write_evidence,
    write_snapshot_store,
)

from evaluation.benchmark.cli import main


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Dataset + snapshot + evidence for one confirmed case; provider patched."""
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    evidence = write_evidence(snapshot_root, case)
    provider = paired_providers(evidence)

    def fake_resolve(
        name=None,
        model=None,
        temperature=0.0,
        max_tokens=None,
        timeout_s=60.0,
    ):
        return provider, mock_config()

    monkeypatch.setattr("evaluation.benchmark.cli.resolve_provider", fake_resolve)
    return dataset_path, store


def test_version_flag(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "python -m evaluation.benchmark" in capsys.readouterr().out


def test_run_end_to_end_and_inspect_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    dataset_path, store = _seed(tmp_path, monkeypatch)
    out = tmp_path / "out"
    code = main(
        [
            "run",
            "--dataset",
            str(dataset_path),
            "--store",
            str(store),
            "--out",
            str(out),
            "--run-id",
            "run-cli",
        ]
    )
    summary = yaml.safe_load(capsys.readouterr().out)
    assert code == 0
    assert summary["run_id"] == "run-cli"
    assert summary["run_identity"].startswith("repoguard-benchmark-v1:")
    assert summary["cases"][0]["status"] == "succeeded"
    assert summary["cases"][0]["baseline_score"] == 50.0
    assert summary["cases"][0]["repoguard_score"] == 50.0

    run_path = out / "run-cli"
    assert (run_path / "run-manifest.yaml").is_file()
    assert (run_path / "baseline" / "C001" / "result.yaml").is_file()
    assert (run_path / "repoguard" / "C001" / "result.yaml").is_file()

    inspect = main(["inspect", "--run", str(run_path)])
    inspected = yaml.safe_load(capsys.readouterr().out)
    assert inspect == 0
    assert inspected["run_manifest"]["run_id"] == "run-cli"

    validate = main(["validate", "--run", str(run_path)])
    validation = yaml.safe_load(capsys.readouterr().out)
    assert validate == 0
    assert validation["valid"] is True


def test_run_reports_failed_cases_nonzero(tmp_path: Path, capsys) -> None:
    # Default mock provider returns an empty response: every run fails but is
    # still recorded and the exit code is non-zero.
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    store = tmp_path / "store"
    write_snapshot_store(store, make_case("C001"))
    write_evidence(store / "C001-synthetic", make_case("C001"))
    code = main(
        [
            "run",
            "--dataset",
            str(dataset_path),
            "--store",
            str(store),
            "--out",
            str(tmp_path / "out"),
            "--run-id",
            "run-fail",
        ]
    )
    summary = yaml.safe_load(capsys.readouterr().out)
    assert code == 1
    assert summary["cases"][0]["status"] == "failed"
    run_path = tmp_path / "out" / "run-fail"
    manifest = yaml.safe_load((run_path / "run-manifest.yaml").read_text("utf-8"))
    assert manifest["results"]["C001"]["status"] == "failed"
    # Failures were recorded, never converted into scores.
    assert manifest["results"]["C001"]["baseline"]["score"] is None
    assert manifest["results"]["C001"]["repoguard"]["score"] is None
    validation = main_output(capsys, ["validate", "--run", str(run_path)])
    assert validation["valid"] is True


def test_run_excluded_case_rejected(tmp_path: Path, capsys) -> None:
    dataset_path = write_dataset(
        tmp_path / "dataset.yaml",
        [case_dict("C007", status="excluded", decision="exclude")],
    )
    code = main(
        [
            "run",
            "--dataset",
            str(dataset_path),
            "--case",
            "C007",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 1
    assert "excluded" in capsys.readouterr().err


def test_run_unknown_provider(tmp_path: Path, capsys) -> None:
    dataset_path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    code = main(
        [
            "run",
            "--dataset",
            str(dataset_path),
            "--provider",
            "gpt-corner",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 1
    assert "unknown provider" in capsys.readouterr().err


def test_inspect_missing_run(tmp_path: Path, capsys) -> None:
    code = main(["inspect", "--run", str(tmp_path / "nope")])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def main_output(capsys, argv: list[str]):
    code = main(argv)
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 0
    return out
