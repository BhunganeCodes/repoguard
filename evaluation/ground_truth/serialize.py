"""Deterministic serialization and content identity for ground-truth artifacts.

Every ground-truth artifact (reviewer assessment, adjudication record, final
consensus) carries a content identity: a SHA-256 over the canonical,
key-sorted YAML rendering of its semantic fields, prefixed with the relevant
scheme. Runtime metadata such as ``review_time_minutes`` is excluded so that
recording the same assessment again yields the same identity; the identity
itself is always excluded from the hash.
"""

from __future__ import annotations

import hashlib
from typing import Any

from evaluation.evidence.serialize import canonical_dump
from evaluation.ground_truth._version import (
    ADJUDICATION_SCHEME,
    GROUND_TRUTH_SCHEME,
    REVIEW_SCHEME,
)


def _identity(scheme: str, data: dict[str, Any], excluded: frozenset[str]) -> str:
    content = {key: value for key, value in data.items() if key not in excluded}
    payload = canonical_dump(content)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{scheme}:{digest}"


def review_identity(review: dict[str, Any]) -> str:
    """Content identity of a reviewer assessment (runtime fields excluded)."""
    return _identity(REVIEW_SCHEME, review, frozenset({"review_identity", "review_time_minutes"}))


def adjudication_identity(record: dict[str, Any]) -> str:
    """Content identity of an adjudication record."""
    return _identity(ADJUDICATION_SCHEME, record, frozenset({"adjudication_identity"}))


def ground_truth_identity(artifact: dict[str, Any]) -> str:
    """Content identity of the final consensus artifact."""
    return _identity(GROUND_TRUTH_SCHEME, artifact, frozenset({"ground_truth_identity"}))


__all__ = [
    "adjudication_identity",
    "canonical_dump",
    "ground_truth_identity",
    "review_identity",
]
