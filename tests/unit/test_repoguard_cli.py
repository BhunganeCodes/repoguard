"""CLI behavior for RepoGuard (mock provider only)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from repoguard_helpers import staged_response
from scoring_helpers import make_evidence

from evaluation.repoguard.cli import main

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


def _env_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPOGUARD_MOCK_RESPONSE", staged_response(make_evidence()))


def test_version_flag(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "python -m evaluation.repoguard" in capsys.readouterr().out


def test_one_happy_path_to_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    evidence_path = _write_evidence(tmp_path)
    _env_valid(monkeypatch)
    out = tmp_path / "result.yaml"
    code = main(["one", "--evidence", str(evidence_path), "--out", str(out)])
    assert code == 0
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded["status"] == "succeeded"
    assert loaded["case_id"] == "C001"
    assert loaded["result_identity"].startswith("repoguard-v1:")


def test_one_provider_failure_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    evidence_path = _write_evidence(tmp_path)
    monkeypatch.setenv("REPOGUARD_MOCK_RESPONSE", "definitely not json")
    code = main(["one", "--evidence", str(evidence_path)])
    assert code == 1
    out = capsys.readouterr().out
    assert "status: failed" in out
    assert "malformed_response" in out


def test_one_missing_evidence_file(tmp_path: Path, capsys) -> None:
    code = main(["one", "--evidence", str(tmp_path / "missing.yaml")])
    assert code == 1
    assert "unreadable evidence" in capsys.readouterr().err


def test_inspect_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    evidence_path = _write_evidence(tmp_path)
    _env_valid(monkeypatch)
    out = tmp_path / "result.yaml"
    assert main(["one", "--evidence", str(evidence_path), "--out", str(out)]) == 0

    code = main(["inspect", "--result", str(out), "--validate"])
    assert code == 0
    inspected = yaml.safe_load(capsys.readouterr().out)
    assert inspected["inspection"]["valid"] is True
    assert inspected["inspection"]["identity_matches"] is True


def test_inspect_detects_tampering(tmp_path: Path, capsys) -> None:
    # Write a manual, corrupted result file.
    out = tmp_path / "result.yaml"
    out.write_text("status: succeeded\ncase_id: C001\n", encoding="utf-8")
    code = main(["inspect", "--result", str(out), "--validate"])
    assert code == 1
    inspected = yaml.safe_load(capsys.readouterr().out)
    assert inspected["inspection"]["identity_matches"] is False
