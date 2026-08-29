"""CLI behavior for the ground-truth workflow."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ground_truth_helpers import make_review
from scoring_helpers import make_evidence

from evaluation.ground_truth.cli import main


def _write(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _write_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    evidence_path = _write(tmp_path / "evidence.yaml", make_evidence().to_dict())
    review_a, _ = make_review(
        reviewer_id="R01",
        overrides={"maintainability.duplication": {"score": 4}},
    )
    review_b, _ = make_review(
        reviewer_id="R02",
        overrides={"maintainability.duplication": {"score": 2}},
    )
    a_path = _write(tmp_path / "C001-R01-review.yaml", review_a)
    b_path = _write(tmp_path / "C001-R02-review.yaml", review_b)
    return evidence_path, a_path, b_path


def _decisions_path(tmp_path: Path) -> Path:
    decisions = {
        "schema_version": 1,
        "case_id": "C001",
        "adjudicator_id": "R03",
        "contested": False,
        "decisions": [
            {
                "criterion_id": "maintainability.duplication",
                "status": "FOUND",
                "score": 3,
                "citations": ["documentation.readme"],
                "rationale": "middle ground",
            },
        ],
    }
    return _write(tmp_path / "decisions.yaml", decisions)


def test_version_flag(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "python -m evaluation.ground_truth" in capsys.readouterr().out


def test_validate_valid_review(tmp_path: Path, capsys) -> None:
    evidence_path, a_path, _ = _write_case(tmp_path)
    assert main(["validate", "--review", str(a_path), "--evidence", str(evidence_path)]) == 0
    report = yaml.safe_load(capsys.readouterr().out)
    assert report["valid"] is True


def test_validate_invalid_review_exits_nonzero(tmp_path: Path, capsys) -> None:
    evidence_path, a_path, _ = _write_case(tmp_path)
    review = yaml.safe_load(a_path.read_text(encoding="utf-8"))
    review["criteria"] = review["criteria"][:-1]
    _write(a_path, review)
    assert main(["validate", "--review", str(a_path), "--evidence", str(evidence_path)]) == 1
    report = yaml.safe_load(capsys.readouterr().out)
    assert report["valid"] is False
    assert any("missing required criterion" in p for p in report["problems"])


def test_reviewer_schema_rejects_system_results(tmp_path: Path, capsys) -> None:
    evidence_path, a_path, _ = _write_case(tmp_path)
    review = yaml.safe_load(a_path.read_text(encoding="utf-8"))
    review["tier"] = "excellent"
    review["repoguard_score"] = 82.5
    _write(a_path, review)
    assert main(["validate", "--review", str(a_path), "--evidence", str(evidence_path)]) == 1
    report = yaml.safe_load(capsys.readouterr().out)
    assert any("unexpected field 'tier'" in p for p in report["problems"])
    assert any("unexpected field 'repoguard_score'" in p for p in report["problems"])


def test_compare_happy_path(tmp_path: Path, capsys) -> None:
    evidence_path, a_path, b_path = _write_case(tmp_path)
    code = main(
        [
            "compare",
            "--review",
            str(a_path),
            "--review",
            str(b_path),
            "--evidence",
            str(evidence_path),
        ]
    )
    assert code == 0
    report = yaml.safe_load(capsys.readouterr().out)
    assert report["needs_discussion"] is True
    assert report["contested_criteria"][0]["criterion_id"] == "maintainability.duplication"


def test_compare_agreeing_reviews(tmp_path: Path, capsys) -> None:
    evidence_path = _write(tmp_path / "evidence.yaml", make_evidence().to_dict())
    a_path = _write(tmp_path / "C001-R01-review.yaml", make_review(reviewer_id="R01")[0])
    b_path = _write(tmp_path / "C001-R02-review.yaml", make_review(reviewer_id="R02")[0])
    assert (
        main(
            [
                "compare",
                "--review",
                str(a_path),
                "--review",
                str(b_path),
                "--evidence",
                str(evidence_path),
            ]
        )
        == 0
    )
    report = yaml.safe_load(capsys.readouterr().out)
    assert report["needs_discussion"] is False


def test_compare_fails_closed_on_bad_review(tmp_path: Path, capsys) -> None:
    evidence_path, a_path, _ = _write_case(tmp_path)
    review = yaml.safe_load(a_path.read_text(encoding="utf-8"))
    review["dataset_version"] = "9.9.9"
    _write(a_path, review)
    assert (
        main(
            [
                "compare",
                "--review",
                str(a_path),
                "--evidence",
                str(evidence_path),
            ]
        )
        == 1
    )
    assert "error:" in capsys.readouterr().err


def test_adjudicate_writes_record_and_consensus(tmp_path: Path, capsys) -> None:
    evidence_path, a_path, b_path = _write_case(tmp_path)
    decisions = _decisions_path(tmp_path)
    record_out = tmp_path / "record.yaml"
    consensus_out = tmp_path / "consensus.yaml"
    code = main(
        [
            "adjudicate",
            "--case",
            "C001",
            "--review",
            str(a_path),
            "--review",
            str(b_path),
            "--decisions",
            str(decisions),
            "--evidence",
            str(evidence_path),
            "--out-record",
            str(record_out),
            "--out-consensus",
            str(consensus_out),
        ]
    )
    assert code == 0
    record = yaml.safe_load(record_out.read_text(encoding="utf-8"))
    artifact = yaml.safe_load(consensus_out.read_text(encoding="utf-8"))
    assert record["adjudicator_id"] == "R03"
    assert artifact["status"] == "consensus"
    assert artifact["assessment"]["summary"]["score"] == 51.0

    outcome = yaml.safe_load(capsys.readouterr().out)
    assert outcome["ground_truth_identity"] == artifact["ground_truth_identity"]


def test_adjudicate_rejects_undisputed_case(tmp_path: Path) -> None:
    evidence_path = _write(tmp_path / "evidence.yaml", make_evidence().to_dict())
    a_path = _write(tmp_path / "C001-R01-review.yaml", make_review(reviewer_id="R01")[0])
    b_path = _write(tmp_path / "C001-R02-review.yaml", make_review(reviewer_id="R02")[0])
    decisions = _decisions_path(tmp_path)
    assert (
        main(
            [
                "adjudicate",
                "--case",
                "C001",
                "--review",
                str(a_path),
                "--review",
                str(b_path),
                "--decisions",
                str(decisions),
                "--evidence",
                str(evidence_path),
            ]
        )
        == 1
    )


def test_inspect_consensus_validates(tmp_path: Path) -> None:
    evidence_path, a_path, b_path = _write_case(tmp_path)
    decisions = _decisions_path(tmp_path)
    consensus_out = tmp_path / "consensus.yaml"
    assert (
        main(
            [
                "adjudicate",
                "--case",
                "C001",
                "--review",
                str(a_path),
                "--review",
                str(b_path),
                "--decisions",
                str(decisions),
                "--evidence",
                str(evidence_path),
                "--out-consensus",
                str(consensus_out),
            ]
        )
        == 0
    )
    assert (
        main(["inspect", "--artifact", str(consensus_out), "--evidence", str(evidence_path)]) == 0
    )
    assert (
        main(
            [
                "inspect",
                "--artifact",
                str(consensus_out),
                "--evidence",
                str(evidence_path),
                "--validate",
            ]
        )
        == 0
    )


def test_inspect_detects_tampered_consensus(tmp_path: Path, capsys) -> None:
    evidence_path, a_path, b_path = _write_case(tmp_path)
    decisions = _decisions_path(tmp_path)
    consensus_out = tmp_path / "consensus.yaml"
    main(
        [
            "adjudicate",
            "--case",
            "C001",
            "--review",
            str(a_path),
            "--review",
            str(b_path),
            "--decisions",
            str(decisions),
            "--evidence",
            str(evidence_path),
            "--out-consensus",
            str(consensus_out),
        ]
    )
    artifact = yaml.safe_load(consensus_out.read_text(encoding="utf-8"))
    artifact["assessment"]["summary"] = {"earned": 1000, "possible": 100}
    _write(consensus_out, artifact)
    assert (
        main(
            [
                "inspect",
                "--artifact",
                str(consensus_out),
                "--evidence",
                str(evidence_path),
                "--validate",
            ]
        )
        == 1
    )
    report = yaml.safe_load(capsys.readouterr().out)
    assert report["identity_matches"] is False
