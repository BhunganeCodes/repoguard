"""CLI behavior for the baseline evaluator (mock provider only)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from baseline_helpers import mock_valid, valid_assessment_text
from scoring_helpers import make_evidence

from evaluation.baseline.cli import main

_PROVIDER_ENV_VARS = (
    "REPOGUARD_LLM_PROVIDER",
    "REPOGUARD_LLM_BASE_URL",
    "REPOGUARD_LLM_MODEL",
    "REPOGUARD_LLM_API_KEY",
    "REPOGUARD_LLM_TIMEOUT_S",
    "REPOGUARD_MOCK_RESPONSE",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """These CLI tests use only the mock provider; strip ambient real-provider
    environment so a configured host does not leak a live endpoint into them."""
    for name in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _write_evidence(tmp_path: Path) -> Path:
    evidence = make_evidence()
    path = tmp_path / "evidence.yaml"
    path.write_text(yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8")
    return path


def _env_valid(monkeypatch: pytest.MonkeyPatch, evidence) -> None:
    monkeypatch.setenv("REPOGUARD_MOCK_RESPONSE", valid_assessment_text(evidence))


def test_version_flag(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "python -m evaluation.baseline" in out
    assert "0.1.0" in out


def test_one_happy_path_via_mock_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    evidence_path = _write_evidence(tmp_path)
    _env_valid(monkeypatch, make_evidence())
    code = main(["one", "--evidence", str(evidence_path)])
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "succeeded"
    assert out["scoring"]["score"] == 50.0
    assert out["result_identity"].startswith("repoguard-baseline-v1:")


def test_one_writes_out_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    evidence_path = _write_evidence(tmp_path)
    _env_valid(monkeypatch, make_evidence())
    out_path = tmp_path / "result.yaml"
    code = main(["one", "--evidence", str(evidence_path), "--out", str(out_path)])
    assert code == 0
    assert out_path.is_file()
    assert yaml.safe_load(out_path.read_text(encoding="utf-8"))["status"] == "succeeded"


def test_one_malformed_response_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    evidence_path = _write_evidence(tmp_path)
    monkeypatch.setenv("REPOGUARD_MOCK_RESPONSE", "not an assessment")
    code = main(["one", "--evidence", str(evidence_path)])
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 1
    assert out["status"] == "failed"
    assert out["error"]["kind"] == "malformed_response"


def test_one_missing_evidence_exits_nonzero(tmp_path: Path, capsys) -> None:
    code = main(["one", "--evidence", str(tmp_path / "nope.yaml")])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_one_unknown_provider(tmp_path: Path, capsys) -> None:
    evidence_path = _write_evidence(tmp_path)
    code = main(["one", "--evidence", str(evidence_path), "--provider", "gpt-corner"])
    assert code == 1
    assert "unknown provider" in capsys.readouterr().err


def test_inspect_valid_result(tmp_path: Path, capsys) -> None:
    from evaluation.baseline.pipeline import EvaluatorConfig, run_case
    from evaluation.baseline.serialize import write_result

    evidence = make_evidence()
    result = run_case(evidence, mock_valid(evidence), config=EvaluatorConfig())
    result_path = tmp_path / "result.yaml"
    write_result(result_path, result)
    code = main(["inspect", "--result", str(result_path), "--validate"])
    assert code == 0
    inspection = yaml.safe_load(capsys.readouterr().out)["inspection"]
    assert inspection["valid"] is True
    assert inspection["identity_matches"] is True


def test_inspect_corrupt_result(tmp_path: Path, capsys) -> None:
    result_path = tmp_path / "bad.yaml"
    result_path.write_text(
        "result_identity: repoguard-baseline-v1:deadbeef\nstatus: succeeded\n", encoding="utf-8"
    )
    code = main(["inspect", "--result", str(result_path), "--validate"])
    assert code == 1
    inspection = yaml.safe_load(capsys.readouterr().out)["inspection"]
    assert inspection["identity_matches"] is False


def test_dataset_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    evidence = make_evidence(case_id="T001")
    store = tmp_path / "store"
    snapshot = store / "T001-synthetic"
    snapshot.mkdir(parents=True)
    (snapshot / "evidence.yaml").write_text(
        yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8"
    )
    _env_valid(monkeypatch, evidence)
    results_dir = tmp_path / "results"
    code = main(["dataset", "--store", str(store), "--results-dir", str(results_dir)])
    out = yaml.safe_load(capsys.readouterr().out)
    assert code == 0
    assert out["results"][0]["case"] == "T001"
    assert out["results"][0]["status"] == "succeeded"
    result_file = results_dir / "T001-baseline-v0.1.0.yaml"
    assert result_file.is_file()
