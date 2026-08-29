"""Evidence pipeline tests: extraction from a real git checkout + CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from evaluation.evidence.cli import main
from evaluation.evidence.paths import evidence_file
from evaluation.evidence.serialize import recompute_identity
from evaluation.evidence.validate import artifact_from_dict, validate_artifact
from evaluation.snapshot.hashing import hash_snapshot_tree


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _prepare_snapshot(tmp_path: Path, git_repo: dict[str, object]) -> Path:
    """Build a snapshot directory with a real git checkout and a record file."""
    snapshot_dir = tmp_path / "C001-local-repo"
    checkout = snapshot_dir / "checkout"
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "-q", str(git_repo["path"]), str(checkout)], checkout.parent)
    content_hash = hash_snapshot_tree(checkout)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "identity": f"repoguard-snapshot-v1:{content_hash}",
        "candidate_id": "C001",
        "name": "local-repo",
        "repository_url": "https://example.com/local.git",
        "requested_commit": git_repo["second"],
        "verified_commit": git_repo["second"],
        "content_hash": content_hash,
        "acquired_at": "2026-08-28T00:00:00Z",
        "git_version": "test",
        "dataset": {"name": "test-dataset", "version": "0.0.0"},
        "acquisition": {"remote_scheme": "file", "blob_filter": False, "depth": None},
    }
    (snapshot_dir / "snapshot.yaml").write_text(yaml.safe_dump(record), encoding="utf-8")
    return snapshot_dir


def test_one_command_roundtrip(tmp_path: Path, git_repo: dict[str, object], capsys) -> None:
    snapshot_dir = _prepare_snapshot(tmp_path, git_repo)
    exit_code = main(["one", "--snapshot", str(snapshot_dir)])
    assert exit_code == 0
    captured = capsys.readouterr().out
    summary = yaml.safe_load(captured)
    assert summary["case_id"] == "C001"
    assert summary["write"]["changed"] is True

    artifact_path = evidence_file(snapshot_dir)
    assert artifact_path.is_file()
    rendered = yaml.safe_load(artifact_path.read_text(encoding="utf-8"))
    artifact = artifact_from_dict(rendered)
    assert validate_artifact(artifact) == []
    assert recompute_identity(artifact) == artifact.evidence_identity
    assert artifact.evidence_identity == summary["evidence_identity"]


def test_one_is_idempotent(tmp_path: Path, git_repo: dict[str, object], capsys) -> None:
    snapshot_dir = _prepare_snapshot(tmp_path, git_repo)
    first = main(["one", "--snapshot", str(snapshot_dir)])
    assert first == 0
    capsys.readouterr()
    artifact_path = evidence_file(snapshot_dir)
    before = artifact_path.read_text(encoding="utf-8")
    second = main(["one", "--snapshot", str(snapshot_dir)])
    assert second == 0
    summary = yaml.safe_load(capsys.readouterr().out)
    assert summary["write"]["changed"] is False
    assert artifact_path.read_text(encoding="utf-8") == before


def test_inspect_validates(tmp_path: Path, git_repo: dict[str, object], capsys) -> None:
    snapshot_dir = _prepare_snapshot(tmp_path, git_repo)
    assert main(["one", "--snapshot", str(snapshot_dir)]) == 0
    capsys.readouterr()
    artifact_path = evidence_file(snapshot_dir)
    exit_code = main(["inspect", "--artifact", str(artifact_path), "--validate"])
    assert exit_code == 0
    inspection = yaml.safe_load(capsys.readouterr().out)["inspection"]
    assert inspection["valid"] is True
    assert inspection["identity_matches"] is True


def test_dataset_command(tmp_path: Path, git_repo: dict[str, object], capsys) -> None:
    snapshot_dir = _prepare_snapshot(tmp_path, git_repo)
    store = snapshot_dir.parent
    exit_code = main(["dataset", "--store", str(store)])
    assert exit_code == 0
    summary = yaml.safe_load(capsys.readouterr().out)
    assert summary["extracted"][0]["case"] == "C001"
    assert summary["extracted"][0]["changed"] is True


def test_one_rejects_non_snapshot_dir(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "not-a-snapshot"
    empty.mkdir()
    exit_code = main(["one", "--snapshot", str(empty)])
    assert exit_code == 1
    assert "not a snapshot directory" in capsys.readouterr().err
