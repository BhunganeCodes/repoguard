"""Snapshot acquisition tests against temporary local git repositories.

No test here touches the network or GitHub; all remotes are local paths.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import write_manifest

from evaluation.snapshot import git
from evaluation.snapshot.acquire import acquire_case
from evaluation.snapshot.errors import (
    AcquisitionError,
    CommitMismatchError,
    CommitNotFoundError,
    SnapshotExistsError,
)
from evaluation.snapshot.hashing import hash_snapshot_tree
from evaluation.snapshot.manifest import load_manifest
from evaluation.snapshot.models import SnapshotResult


def _case_payload(url: str, sha: str, **overrides) -> dict[str, object]:
    payload = {
        "candidate_id": "T001",
        "name": "local-repo",
        "url": url,
        "pinned_commit": sha,
        "ecosystem": "Go",
        "license": "MIT",
        "dataset_decision": "include",
        "dataset_status": "confirmed",
    }
    payload.update(overrides)
    return payload


def _acquire(git_repo: dict[str, object], store: Path, **overrides) -> SnapshotResult:
    url = str(git_repo["path"])  # type: ignore[arg-type]
    sha = str(git_repo["first"])
    manifest_path = write_manifest(
        Path(store) / ".." / "manifest.yaml", [_case_payload(url, sha, **overrides)]
    )
    manifest = load_manifest(manifest_path)
    return acquire_case(manifest.cases[0], manifest, store)


def test_acquire_pins_exact_commit(git_repo: dict[str, object], tmp_path: Path) -> None:
    result = _acquire(git_repo, tmp_path / "store")
    assert result.record.requested_commit == result.record.verified_commit == git_repo["first"]
    assert result.record.content_hash
    checkout = result.path / "checkout"
    assert hash_snapshot_tree(checkout) == result.record.content_hash
    assert result.inventory.tracked_file_count == 3
    assert result.inventory.readme == "README.md"
    assert result.inventory.ecosystem == "Go"


def test_acquire_second_run_is_idempotent(git_repo: dict[str, object], tmp_path: Path) -> None:
    store = tmp_path / "store"
    first = _acquire(git_repo, store)
    second = _acquire(git_repo, store)
    assert first.idempotent is False
    assert second.idempotent is True
    assert second.record.content_hash == first.record.content_hash


def test_hash_deterministic_across_stores(git_repo: dict[str, object], tmp_path: Path) -> None:
    first = _acquire(git_repo, tmp_path / "store-a")
    second = _acquire(git_repo, tmp_path / "store-b")
    assert first.record.content_hash == second.record.content_hash


def test_acquire_non_default_commit_not_substituted(
    git_repo: dict[str, object], tmp_path: Path
) -> None:
    # `second` is the current branch tip; requesting `first` must NOT follow
    # the moving branch head. The verified commit must equal `first`.
    result = _acquire(git_repo, tmp_path / "store", pinned_commit=str(git_repo["first"]))
    assert result.record.verified_commit == git_repo["first"]
    assert "func main" not in (result.path / "checkout" / "main.go").read_text(encoding="utf-8")


def test_conflicting_existing_snapshot_is_refused(
    git_repo: dict[str, object], tmp_path: Path
) -> None:
    store = tmp_path / "store"
    _acquire(git_repo, store, pinned_commit=str(git_repo["first"]))
    # Same candidate id pinned to a different commit must fail closed.
    with pytest.raises(SnapshotExistsError):
        _acquire(git_repo, store, pinned_commit=str(git_repo["second"]))
    # A different candidate id is a distinct snapshot and is allowed.
    other = _acquire(git_repo, store, candidate_id="T002", pinned_commit=str(git_repo["second"]))
    assert other.record.verified_commit == git_repo["second"]


def test_unknown_commit_fails_closed(git_repo: dict[str, object], tmp_path: Path) -> None:
    bogus = "f" * 40
    with pytest.raises((CommitNotFoundError, AcquisitionError)):
        _acquire(git_repo, tmp_path / "store", pinned_commit=bogus)


def test_checkout_mismatch_is_refused(git_repo: dict[str, object], tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    git.init_repository(worktree, str(git_repo["path"]))  # type: ignore[arg-type]
    git.fetch_commit(worktree, str(git_repo["path"]), str(git_repo["second"]))  # type: ignore[arg-type]
    git.checkout_commit(worktree, str(git_repo["second"]))
    verified = git.verified_head(worktree, str(git_repo["second"]))
    assert verified == git_repo["second"]
    with pytest.raises(CommitMismatchError):
        git.verified_head(worktree, str(git_repo["first"]))


def test_ls_remote_head_resolves_default_branch(
    git_repo: dict[str, object], tmp_path: Path
) -> None:
    url = str(git_repo["path"])
    assert git.ls_remote_head(url) == git_repo["second"]


def test_ls_remote_head_fails_closed_on_unknown_remote(tmp_path: Path) -> None:
    with pytest.raises(AcquisitionError):
        git.ls_remote_head(str(tmp_path / "does-not-exist"))


def test_dirty_worktree_is_refused(git_repo: dict[str, object], tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    git.init_repository(worktree, str(git_repo["path"]))  # type: ignore[arg-type]
    git.fetch_commit(worktree, str(git_repo["path"]), str(git_repo["first"]))  # type: ignore[arg-type]
    git.checkout_commit(worktree, str(git_repo["first"]))
    (worktree / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(AcquisitionError):
        git.verified_head(worktree, str(git_repo["first"]))


def test_exec_no_repository_code_runs(git_repo: dict[str, object], tmp_path: Path) -> None:
    """The snapshot stage is extraction-only: repo content is fetched and
    checked out as files, never executed (no hooks, build, or script run)."""
    repo = git_repo["path"]
    assert isinstance(repo, Path)
    (repo / "evil.sh").write_text("touch pwned-marker\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "evil.sh"], capture_output=True, text=True, check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-qm", "evil"],
        capture_output=True,
        text=True,
        check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    result = _acquire(git_repo, tmp_path / "store", pinned_commit=sha, name="has-evil")
    checkout = result.path / "checkout"
    script = checkout / "evil.sh"
    assert script.is_file()
    assert script.read_text(encoding="utf-8") == "touch pwned-marker\n"
    # Nothing from the repository ran: no side-effect marker outside the
    # repo, and the script on disk is byte-identical to what was committed.
    assert not (tmp_path / "pwned-marker").exists()
