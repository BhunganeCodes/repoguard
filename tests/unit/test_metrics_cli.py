"""CLI behaviour for ``metrics calculate / compare / inspect / validate``."""

from __future__ import annotations

from pathlib import Path

import pytest
from metrics_helpers import (
    CaseSpec,
    OutSpec,
    ground_truth_artifact,
    materialize_run,
    write_ground_truth,
)
from scoring_helpers import make_evidence

from evaluation.metrics.cli import main
from evaluation.metrics.serialize import read_report
from evaluation.metrics.validate import validate_report


def _run(tmp_path: Path, **kwargs) -> str:
    return str(
        materialize_run(
            tmp_path,
            [CaseSpec("C001", baseline=OutSpec(score=2), repoguard=OutSpec(score=3))],
            **kwargs,
        )
    )


def test_calculate_writes_report_and_exits_zero(tmp_path: Path, capsys) -> None:
    out = tmp_path / "report.yaml"
    code = main(["calculate", "--run", _run(tmp_path), "--out", str(out)])
    assert code == 0
    assert out.is_file()
    report = read_report(out)
    assert validate_report(report) == []
    assert "wrote metrics report" in capsys.readouterr().out


def test_compare_writes_comparison(tmp_path: Path, capsys) -> None:
    out = tmp_path / "compare.yaml"
    code = main(["compare", "--run", _run(tmp_path), "--out", str(out)])
    assert code == 0
    assert out.is_file()
    assert "paired cases: 1" in capsys.readouterr().out


def test_calculate_fails_closed_on_bad_run(tmp_path: Path) -> None:
    code = main(["compare", "--run", str(tmp_path / "missing"), "--out", str(tmp_path / "x.yaml")])
    assert code == 1


def test_calculate_rejects_unknown_metric(tmp_path: Path) -> None:
    code = main(
        [
            "calculate",
            "--run",
            _run(tmp_path),
            "--metric",
            "bogus",
            "--out",
            str(tmp_path / "x.yaml"),
        ]
    )
    assert code == 2


def test_calculate_uses_ground_truth_dependency(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    gtdir = tmp_path / "gt"
    write_ground_truth(gtdir, [ground_truth_artifact(make_evidence("C001"), score=2)])
    out = tmp_path / "report.yaml"
    code = main(["calculate", "--run", run_dir, "--ground-truth", str(gtdir), "--out", str(out)])
    assert code == 0
    report = read_report(out)
    assert report["primary_metric"]["baseline"]["rho"] is None  # n=1 measurable
    assert report["inputs"]["ground_truth"]["contested_cases"] == []


def test_inspect_validates_and_exits_one_on_tampering(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    out = tmp_path / "report.yaml"
    assert main(["calculate", "--run", run_dir, "--out", str(out)]) == 0
    assert main(["inspect", "--report", str(out), "--validate"]) == 0
    report = read_report(out)
    report["primary_metric"]["baseline"]["rho"] = 0.5

    from evaluation.evidence.serialize import canonical_dump

    out.write_text(canonical_dump(report), encoding="utf-8")
    assert main(["inspect", "--report", str(out), "--validate"]) == 1


def test_validate_run_passes_and_bad_ground_truth_fails(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    assert main(["validate", "--run", run_dir]) == 0
    bad_gt = tmp_path / "bad-gt.yaml"
    bad_gt.write_text("not: a: valid: yaml: [", encoding="utf-8")
    assert main(["validate", "--run", run_dir, "--ground-truth", str(bad_gt)]) == 1


def test_validate_requires_input() -> None:
    assert main(["validate"]) == 2


def test_cli_help_mentions_commands() -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
