"""Shared fixtures for the snapshot unit tests (local git only, no network)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> dict[str, object]:
    """Build a small local git repository with two commits.

    First commit: README.md, main.go, tests/main_test.go.
    Second commit: appends a main function to main.go.
    """
    repo = tmp_path / "src"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "repo-guard-test"], repo)
    (repo / "README.md").write_text("# local repo\n", encoding="utf-8")
    (repo / "main.go").write_text("package main\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "main_test.go").write_text("package main\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "first"], repo)
    first = _git(["rev-parse", "HEAD"], repo)
    (repo / "main.go").write_text("package main\n\nfunc main() {}\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "second"], repo)
    second = _git(["rev-parse", "HEAD"], repo)
    return {"path": repo, "first": first, "second": second}


def write_manifest(
    target: Path,
    candidates: list[dict[str, object]],
    *,
    name: str = "test-dataset",
    version: str = "0.0.0",
) -> Path:
    """Write a minimal, structurally valid dataset manifest for tests."""
    import yaml

    manifest: dict[str, object] = {
        "dataset": {
            "name": name,
            "version": version,
            "creation_date": "2026-08-28",
            "status": "frozen",
        },
        "candidates": candidates,
    }
    target.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return target


def default_case(
    *,
    candidate_id: str = "T001",
    name: str = "local-repo",
    url: str,
    pinned_commit: str,
    dataset_status: str = "confirmed",
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "name": name,
        "url": url,
        "pinned_commit": pinned_commit,
        "ecosystem": "Go",
        "license": "MIT",
        "dataset_decision": "include",
        "dataset_status": dataset_status,
    }
