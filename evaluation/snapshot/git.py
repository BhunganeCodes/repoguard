"""Git subprocess operations for snapshot acquisition.

Acquisition is pinned to an exact commit SHA. A checkout whose HEAD differs
from the requested SHA is an error; the subsystem never silently replaces a
revision.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from evaluation.snapshot.commits import normalize_sha
from evaluation.snapshot.errors import (
    AcquisitionError,
    CommitMismatchError,
    CommitNotFoundError,
)
from evaluation.snapshot.models import AcquisitionOptions

_NOT_FOUND_MARKERS = (
    "couldn't find remote ref",
    "not our ref",
    "Server does not allow request for unadvertised object",
)


def git_version() -> str:
    """Human-readable git version string."""
    proc = _run_git(["--version"])
    if proc.returncode != 0:
        raise AcquisitionError("git --version failed")
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        check=False,
    )


def remote_scheme(url: str) -> str:
    """http for https/http remotes (blob filters supported), else file."""
    scheme = urlsplit(url).scheme.lower()
    return "http" if scheme in ("http", "https") else "file"


def ls_remote_head(url: str) -> str:
    """Resolve the SHA of the remote's default branch HEAD.

    Used by the product interface when the caller omits a pinned commit.
    Returns the normalized full SHA; fails closed when the remote is
    unreachable or advertises no HEAD.
    """
    proc = _run_git(["ls-remote", "--symref", url, "HEAD"])
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise AcquisitionError(f"cannot resolve remote HEAD: {stderr.strip()}")
    lines = proc.stdout.decode("utf-8", errors="replace").splitlines()
    for line in lines:
        if not line.startswith("ref:") and line.endswith("\tHEAD"):
            sha = line.split("\t", 1)[0].strip()
            return normalize_sha(sha)
    raise CommitNotFoundError(f"remote {url} advertises no HEAD")


def init_repository(worktree: Path, url: str) -> None:
    """Create an empty git worktree with the remote configured."""
    worktree.mkdir(parents=True, exist_ok=False)
    _raise_on_error(_run_git(["init", "--quiet"], cwd=worktree))
    _raise_on_error(_run_git(["remote", "add", "origin", url], cwd=worktree))


def fetch_commit(worktree: Path, url: str, sha: str) -> AcquisitionOptions:
    """Fetch exactly the commit ``sha`` into the worktree's git store.

    Tries from most aggressive (shallow + blob filter, where supported) to
    most conservative (full history). Every attempt remains pinned to the
    requested SHA; falling back never substitutes another revision.

    Returns the options of the successful attempt for the record.
    """
    if remote_scheme(url) == "http":
        attempts: list[tuple[AcquisitionOptions, list[str]]] = [
            (
                AcquisitionOptions(remote_scheme="http", blob_filter=True, depth=1),
                ["fetch", "--depth", "1", "--no-tags", "--filter=blob:none", "origin", sha],
            ),
            (
                AcquisitionOptions(remote_scheme="http", blob_filter=False, depth=1),
                ["fetch", "--depth", "1", "--no-tags", "origin", sha],
            ),
            (
                AcquisitionOptions(remote_scheme="http", blob_filter=False, depth=None),
                ["fetch", "--no-tags", "origin", sha],
            ),
        ]
    else:
        attempts = [
            (
                AcquisitionOptions(remote_scheme="file", blob_filter=False, depth=1),
                ["fetch", "--depth", "1", "--no-tags", "origin", sha],
            ),
            (
                AcquisitionOptions(remote_scheme="file", blob_filter=False, depth=None),
                ["fetch", "--no-tags", "origin", sha],
            ),
        ]
    last_proc: subprocess.CompletedProcess[bytes] | None = None
    for options, args in attempts:
        proc = _run_git(["-C", str(worktree), *args])
        if proc.returncode == 0:
            return options
        last_proc = proc
    assert last_proc is not None
    stderr = last_proc.stderr.decode("utf-8", errors="replace")
    if any(marker in stderr for marker in _NOT_FOUND_MARKERS):
        raise CommitNotFoundError(f"commit {sha} does not exist at remote: {stderr.strip()}")
    raise AcquisitionError(f"failed to fetch commit {sha}: {stderr.strip() or 'unknown git error'}")


def checkout_commit(worktree: Path, sha: str) -> None:
    """Detached checkout of exactly ``sha``; the working tree matches that commit."""
    proc = _run_git(["-C", str(worktree), "checkout", "--quiet", "--detach", sha])
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise AcquisitionError(f"checkout of {sha} failed: {stderr.strip()}")


def verified_head(worktree: Path, requested: str) -> str:
    """Return the verified HEAD commit, refusing any mismatch.

    - full HEAD SHA must equal the normalized requested SHA
    - the working tree must be clean
    """
    requested = normalize_sha(requested)
    proc = _run_git(["-C", str(worktree), "rev-parse", "--verify", "HEAD^{commit}"])
    if proc.returncode != 0:
        raise AcquisitionError("cannot resolve HEAD after checkout")
    verified_sha = proc.stdout.decode("ascii", errors="replace").strip().lower()
    if verified_sha != requested:
        raise CommitMismatchError(
            f"requested commit {requested} but checkout resolved to {verified_sha}"
        )
    status = _run_git(["-C", str(worktree), "status", "--porcelain"])
    if status.returncode != 0:
        raise AcquisitionError("cannot determine working tree status")
    if status.stdout:
        lines = status.stdout.decode("utf-8", errors="replace").splitlines()
        raise AcquisitionError(f"working tree is not clean at {requested}: {lines[:5]!r}")
    return verified_sha


def list_tracked_files(worktree: Path) -> list[str]:
    """Relative paths of all files tracked at HEAD, sorted, null-safe."""
    proc = _run_git(["-C", str(worktree), "ls-files", "-z"])
    if proc.returncode != 0:
        raise AcquisitionError("git ls-files failed")
    raw = proc.stdout.split(b"\0")
    files = [part.decode("utf-8", errors="replace") for part in raw if part]
    return sorted(files)


def list_top_level_entries(worktree: Path) -> list[str]:
    """Sorted list of top-level path names present in the tree at HEAD."""
    proc = _run_git(["-C", str(worktree), "ls-tree", "--name-only", "-z", "HEAD"])
    if proc.returncode != 0:
        raise AcquisitionError("git ls-tree failed")
    raw = proc.stdout.split(b"\0")
    return sorted(part.decode("utf-8", errors="replace") for part in raw if part)


def _raise_on_error(proc: subprocess.CompletedProcess[bytes]) -> None:
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise AcquisitionError(stderr.strip() or "git command failed")
