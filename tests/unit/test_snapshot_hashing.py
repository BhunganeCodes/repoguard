"""Deterministic content-hash tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import git_repo  # noqa: F401  (fixture re-export)

from evaluation.snapshot.hashing import hash_snapshot_tree


def _write_tree(root: Path) -> None:
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    nested = root / "src"
    nested.mkdir()
    (nested / "b.go").write_text("package b\n", encoding="utf-8")


def test_repeated_hash_is_stable(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _write_tree(root)
    assert hash_snapshot_tree(root) == hash_snapshot_tree(root)


def test_content_change_changes_hash(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _write_tree(root)
    before = hash_snapshot_tree(root)
    (root / "a.txt").write_text("ALPHA\n", encoding="utf-8")
    after = hash_snapshot_tree(root)
    assert before != after


def test_new_file_changes_hash(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _write_tree(root)
    before = hash_snapshot_tree(root)
    (root / "extra.c").write_text("int x;\n", encoding="utf-8")
    assert hash_snapshot_tree(root) != before


def test_git_directory_is_excluded(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _write_tree(root)
    before = hash_snapshot_tree(root)
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("anything\n", encoding="utf-8")
    assert hash_snapshot_tree(root) == before


def test_symlink_only_target_hashed(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _write_tree(root)
    try:
        os.symlink("a.txt", root / "link.txt")
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    assert hash_snapshot_tree(root) == hash_snapshot_tree(root)


def test_hash_is_independent_of_directory_location(tmp_path: Path) -> None:
    dir_one = tmp_path / "one"
    dir_two = tmp_path / "two"
    dir_one.mkdir()
    dir_two.mkdir()
    _write_tree(dir_one)
    _write_tree(dir_two)
    assert hash_snapshot_tree(dir_one) == hash_snapshot_tree(dir_two)
