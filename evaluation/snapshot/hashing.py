"""Deterministic snapshot content hash.

The hash is computed over the tracked file content (and symlink targets) of
the checked-out snapshot. It excludes .git metadata, timestamps, temporary
files, and every local absolute path, so identical URL + commit produces an
identical hash on any machine.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from evaluation.snapshot.commits import SNAPSHOT_HASH_SCHEME
from evaluation.snapshot.errors import HashError

_GIT_DIR = ".git"

_BYTE = b""


def _path_bytes(relative: Path) -> bytes:
    return relative.as_posix().encode("utf-8", errors="replace")


def _walk(root: Path) -> list[tuple[bytes, bytes]]:
    """Return sorted [(relative_path_bytes, content_or_target_bytes)] entries.

    Regular files contribute their bytes; symlinks contribute their link
    target. Directories and the .git metadata directory are skipped.
    """
    entries: list[tuple[bytes, bytes]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            if current.name == _GIT_DIR:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d != _GIT_DIR]
            for name in filenames:
                full = current / name
                relative = full.relative_to(root)
                if full.is_symlink():
                    entries.append((_path_bytes(relative), os.readlink(full).encode("utf-8")))
                elif full.is_file():
                    entries.append((_path_bytes(relative), _read_file(full)))
    except OSError as exc:
        raise HashError(f"cannot walk snapshot tree {root}: {exc}") from exc
    entries.sort(key=lambda item: item[0])
    return entries


def _read_file(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read()
    except OSError as exc:
        raise HashError(f"cannot read {path}: {exc}") from exc


def hash_snapshot_tree(root: Path) -> str:
    """SHA-256 content hash over the snapshot tree (excluding .git)."""
    digest = hashlib.sha256()
    digest.update(SNAPSHOT_HASH_SCHEME.encode("utf-8"))
    for relative, content in _walk(root):
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()
