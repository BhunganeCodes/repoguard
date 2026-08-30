"""Deterministic serialization and content identity for metrics reports.

The report identity is a SHA-256 over the canonical, key-sorted YAML
rendering of every semantic field (everything except the identity and
``generated_at``). The report's semantic payload includes the benchmark run
identity, the aggregate ground-truth identity, and the metric implementation
version and configuration, so identical inputs always produce the identical
report and no timestamp ever enters a content identity.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from evaluation.evidence.serialize import canonical_dump
from evaluation.metrics._version import (
    GROUND_TRUTH_AGGREGATE_SCHEME,
    METRICS_SCHEME,
)

_SEMANTIC_EXCLUDED = frozenset({"metrics_identity", "generated_at"})


def metrics_identity(payload: dict[str, Any]) -> str:
    content = {key: value for key, value in payload.items() if key not in _SEMANTIC_EXCLUDED}
    digest = hashlib.sha256(canonical_dump(content).encode("utf-8")).hexdigest()
    return f"{METRICS_SCHEME}:{digest}"


def ground_truth_identities_identity(identities: Mapping[str, str]) -> str:
    """Aggregate identity over the consumed ground-truth artifacts (by case)."""
    payload = canonical_dump({case_id: identities[case_id] for case_id in sorted(identities)})
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{GROUND_TRUTH_AGGREGATE_SCHEME}:{digest}"


def compose_report(data: dict[str, Any]) -> dict[str, Any]:
    """Set the identity on a report payload (without mutating the input)."""
    report = dict(data)
    report["metrics_identity"] = metrics_identity(report)
    return report


def recompute_identity(data: Any) -> str | None:
    """Recompute the identity of a serialized report (for ``inspect``)."""
    if not isinstance(data, dict):
        return None
    return metrics_identity(data)


def write_report(path: Path, report: dict[str, Any]) -> str:
    """Write the composed report to ``path``; returns the rendered text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = canonical_dump(report)
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return rendered


def read_report(path: Path) -> dict[str, Any]:
    """Load a serialized metrics report (for ``inspect``/``validate``)."""
    loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: metrics report is not a mapping")
    return loaded
