"""Commit SHA validation and snapshot identity constants."""

from __future__ import annotations

import re

from evaluation.snapshot.errors import InvalidShaError

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# Scheme tag embedded in every content hash so hashes are never ambiguous
# across hash-spec revisions.
SNAPSHOT_HASH_SCHEME = "repoguard-snapshot-v1"


def is_full_sha(value: str) -> bool:
    """True when value is exactly a 40-character lowercase hex SHA-1."""
    return _FULL_SHA.fullmatch(value) is not None


def normalize_sha(value: str) -> str:
    """Return the canonical lowercase 40-char SHA or raise InvalidShaError."""
    stripped = value.strip()
    if len(stripped) != 40 or any(c not in "0123456789abcdefABCDEF" for c in stripped):
        raise InvalidShaError(f"expected a 40-character hex commit SHA, got {value!r}")
    lowered = stripped.lower()
    if not is_full_sha(lowered):
        raise InvalidShaError(f"expected a 40-character hex commit SHA, got {value!r}")
    return lowered
