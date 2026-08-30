"""Validation rules for evidence artifacts.

An artifact is valid when:

* the schema version, identity, and provenance fields are present;
* every item carries a canonical category, status, and provenance;
* every FOUND item cites at least one repository-relative source path;
* source paths are relative, POSIX, and never absolute or escaping;
* observation/notes never contain quality verdicts, scores, or tiers;
* evidence IDs are unique.

Validation returns a list of human-readable problems (empty == valid). It
never mutates its input.
"""

from __future__ import annotations

import re
from typing import Any

from evaluation.evidence._version import EXTRACTION_SCHEME
from evaluation.evidence.errors import EvidenceError
from evaluation.evidence.models import EvidenceArtifact, EvidenceItem
from evaluation.evidence.statuses import (
    CATEGORIES,
    validate_category,
    validate_status,
)

FORBIDDEN_QUALITY_WORDS = frozenset(
    {
        # Tier labels mirroring the scoring rubric; extractors must never use them.
        "excellent",
        "good",
        "average",
        "weak",
        "challenging",
        "poor",
        "abysmal",
        "strong",
        "robust",
        # Scoring/ranking vocabulary must never appear in observations.
        "score",
        "scoring",
        "rank",
        "ranked",
        "rating",
        "tier",
        "quality",
        # Editorial verdict phrases.
        "clean architecture",
        "well-structured",
        "well maintained",
        "high quality",
        "low quality",
        "spaghetti",
    }
)

_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(FORBIDDEN_QUALITY_WORDS)) + r")\b",
    re.IGNORECASE,
)

_ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"^[A-Za-z]:[\\/]"),
    re.compile(r"^/"),
    re.compile(r"\\"),
)
_TRAVERSAL_COMPONENT = re.compile(r"(^|/)\.\.(/|$)")


def _path_problem(path: str) -> str | None:
    if not path:
        return "empty source path"
    if any(p.search(path) for p in _ABSOLUTE_PATH_PATTERNS) or _TRAVERSAL_COMPONENT.search(path):
        return f"source path is not a repository-relative POSIX path: {path!r}"
    return None


def validate_item(item: EvidenceItem) -> list[str]:
    problems: list[str] = []
    if not item.evidence_id:
        problems.append(f"item missing evidence_id ({item.observation!r})")
    try:
        validate_category(item.category)
    except EvidenceError as exc:
        problems.append(str(exc))
    try:
        validate_status(item.status)
    except EvidenceError as exc:
        problems.append(str(exc))
    if not item.observation.strip():
        problems.append(f"{item.evidence_id}: empty observation")
    if not item.extractor or not item.extractor_version:
        problems.append(f"{item.evidence_id}: missing extractor provenance")
    if item.status == "FOUND" and not item.source_paths:
        problems.append(f"{item.evidence_id}: FOUND without any source path")
    for path in item.source_paths:
        problem = _path_problem(path)
        if problem:
            problems.append(f"{item.evidence_id}: {problem}")
    if item.observed is not None:
        if not isinstance(item.observed, dict):
            problems.append(f"{item.evidence_id}: observed must be a mapping")
    text = f"{item.observation} {item.notes or ''}"
    match = _FORBIDDEN_PATTERN.search(text)
    if match:
        problems.append(f"{item.evidence_id}: forbidden quality/scoring word {match.group(0)!r}")
    return problems


def validate_artifact(artifact: EvidenceArtifact) -> list[str]:
    problems: list[str] = []
    if artifact.schema_version != 1:
        problems.append(f"unsupported schema_version: {artifact.schema_version}")
    if not artifact.case_id:
        problems.append("missing case_id")
    if not artifact.evidence_identity:
        problems.append("missing evidence_identity")
    elif not artifact.evidence_identity.startswith(EXTRACTION_SCHEME + ":"):
        problems.append("evidence_identity does not use the extraction scheme")
    seen_ids: set[str] = set()
    count_by_category: dict[str, int] = {c: 0 for c in CATEGORIES}
    for item in artifact.items:
        problems.extend(validate_item(item))
        if item.evidence_id in seen_ids:
            problems.append(f"duplicate evidence_id: {item.evidence_id}")
        seen_ids.add(item.evidence_id)
        if item.category in count_by_category:
            count_by_category[item.category] += 1
    for category, count in count_by_category.items():
        if count == 0:
            problems.append(f"no evidence items produced for category: {category}")
    return problems


def validate_raw(data: dict[str, Any]) -> list[str]:
    """Validate an artifact parsed back from YAML (public header path)."""
    try:
        artifact = artifact_from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        return [f"artifact structure invalid: {exc}"]
    return validate_artifact(artifact)


def artifact_from_dict(data: dict[str, Any]) -> EvidenceArtifact:
    items_raw = data["items"]
    items: list[EvidenceItem] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            raise ValueError("item is not a mapping")
        items.append(
            EvidenceItem(
                evidence_id=str(raw["evidence_id"]),
                case_id=str(raw["case_id"]),
                category=str(raw["category"]),
                evidence_type=str(raw["evidence_type"]),
                status=str(raw["status"]),
                observation=str(raw["observation"]),
                source_paths=[str(p) for p in raw.get("source_paths", [])],
                extractor=str(raw.get("extractor", "")),
                extractor_version=str(raw.get("extractor_version", "")),
                notes=raw.get("notes"),
                observed=raw.get("observed"),
            )
        )
    return EvidenceArtifact(
        schema_version=int(data["schema_version"]),
        case_id=str(data["case_id"]),
        name=str(data.get("name", "")),
        repository_url=str(data.get("repository_url", "")),
        requested_commit=str(data.get("requested_commit", "")),
        verified_commit=str(data.get("verified_commit", "")),
        snapshot_content_hash=str(data.get("snapshot_content_hash", "")),
        extraction_version=str(data.get("extraction_version", "")),
        evidence_identity=str(data["evidence_identity"]),
        generated_at=str(data.get("generated_at", "")),
        items=items,
    )
