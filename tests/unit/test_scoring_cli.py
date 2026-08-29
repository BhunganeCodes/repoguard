"""CLI behavior for the scoring subsystem."""

from __future__ import annotations

from pathlib import Path

import yaml
from scoring_helpers import make_assessment

from evaluation.scoring.cli import main


def _write(tmp_path: Path) -> tuple[Path, Path]:
    assessment, evidence = make_assessment()
    assessment_path = tmp_path / "assessment.yaml"
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text(yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8")
    assessment_path.write_text(yaml.safe_dump(assessment, sort_keys=False), encoding="utf-8")
    return assessment_path, evidence_path


def test_validate_ok(tmp_path: Path, capsys) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    code = main(
        ["validate", "--assessment", str(assessment_path), "--evidence", str(evidence_path)]
    )
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 0
    assert out["valid"] is True
    assert out["problems"] == []
    assert out["complete"] is True
    assert out["computed"]["score"] == 50.0


def test_validate_rejects_unknown_criterion(tmp_path: Path, capsys) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    row = assessment_path.read_text(encoding="utf-8").replace(
        "architecture.project_organization", "quality.nonexistent"
    )
    assessment_path.write_text(row, encoding="utf-8")
    code = main(
        ["validate", "--assessment", str(assessment_path), "--evidence", str(evidence_path)]
    )
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 1
    assert out["valid"] is False
    assert any("unknown criterion id" in p for p in out["problems"])


def test_validate_missing_evidence_file(tmp_path: Path, capsys) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    code = main(
        [
            "validate",
            "--assessment",
            str(assessment_path),
            "--evidence",
            str(tmp_path / "nope.yaml"),
        ]
    )
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_score_writes_artifact_to_out(tmp_path: Path, capsys) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    out_path = tmp_path / "scored.yaml"
    code = main(
        [
            "score",
            "--assessment",
            str(assessment_path),
            "--evidence",
            str(evidence_path),
            "--out",
            str(out_path),
        ]
    )
    assert code == 0
    assert out_path.is_file()
    scored = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert scored["summary"]["earned"] == 50
    assert scored["summary"]["possible"] == 100
    assert scored["summary"]["score"] == 50.0
    assert len(scored["criteria"]) == 25
    assert len(scored["dimensions"]) == 5


def test_score_stdout_matches_out_file(tmp_path: Path, capsys) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    assert (
        main(["score", "--assessment", str(assessment_path), "--evidence", str(evidence_path)]) == 0
    )
    stdout_artifact = capsys.readouterr().out
    assert yaml.safe_load(stdout_artifact)["summary"]["score"] == 50.0
    assert "assessment_identity:" in stdout_artifact


def test_score_rejects_pending_assessment(tmp_path: Path, capsys) -> None:
    assessment, evidence = make_assessment(
        overrides={"architecture.extensibility": {"status": "PENDING", "score": None}}
    )
    assessment_path = tmp_path / "assessment.yaml"
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text(yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8")
    assessment_path.write_text(yaml.safe_dump(assessment, sort_keys=False), encoding="utf-8")
    code = main(["score", "--assessment", str(assessment_path), "--evidence", str(evidence_path)])
    assert code == 1
    assert "pending assessment" in capsys.readouterr().err


def test_score_repeated_runs_identical(tmp_path: Path) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    first_out = tmp_path / "first.yaml"
    second_out = tmp_path / "second.yaml"
    main(
        [
            "score",
            "--assessment",
            str(assessment_path),
            "--evidence",
            str(evidence_path),
            "--out",
            str(first_out),
        ]
    )
    main(
        [
            "score",
            "--assessment",
            str(assessment_path),
            "--evidence",
            str(evidence_path),
            "--out",
            str(second_out),
        ]
    )
    assert first_out.read_bytes() == second_out.read_bytes()


def test_inspect_ok(tmp_path: Path, capsys) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    code = main(
        [
            "inspect",
            "--assessment",
            str(assessment_path),
            "--evidence",
            str(evidence_path),
            "--validate",
        ]
    )
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 0
    inspection = out["inspection"]
    assert inspection["valid"] is True
    assert inspection["scoreable"] is True


def test_inspect_validate_flag_fails_on_bad_assessment(tmp_path: Path, capsys) -> None:
    assessment_path, evidence_path = _write(tmp_path)
    row = assessment_path.read_text(encoding="utf-8").replace("score: 2", "score: 9")
    assessment_path.write_text(row, encoding="utf-8")
    code = main(
        [
            "inspect",
            "--assessment",
            str(assessment_path),
            "--evidence",
            str(evidence_path),
            "--validate",
        ]
    )
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 1
    assert out["inspection"]["valid"] is False


def test_version_flag(tmp_path: Path, capsys) -> None:
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "python -m evaluation.scoring" in out
    assert "0.1.0" in out
