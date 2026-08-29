"""Deterministic serialization and content identity for evidence artifacts.

The identity hash covers every semantic field (items, snapshot metadata) and
excludes only runtime metadata (``generated_at``) and the identity itself.
Two artifacts produced from the same snapshot therefore carry the same
identity regardless of when they were generated.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from evaluation.evidence._version import EXTRACTION_SCHEME
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.validate import artifact_from_dict

_SEMANTIC_EXCLUDED = frozenset({"generated_at", "evidence_identity"})


def canonical_dump(data: dict[str, Any]) -> str:
    """Byte-stable YAML rendering (keys sorted at every level)."""
    return yaml.safe_dump(data, sort_keys=True, width=100, default_flow_style=False)


def semantic_content(artifact: EvidenceArtifact) -> dict[str, Any]:
    """Artifact data excluding runtime metadata and the identity itself."""
    data = artifact.to_dict()
    for key in _SEMANTIC_EXCLUDED:
        data.pop(key, None)
    return data


def serialize(artifact: EvidenceArtifact) -> str:
    data = artifact.to_dict()
    return canonical_dump(data)


def content_identity(artifact: EvidenceArtifact) -> str:
    """Deterministic hash of the semantic content of an artifact."""
    payload = canonical_dump(semantic_content(artifact))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{EXTRACTION_SCHEME}:{digest}"


def recompute_identity(artifact: EvidenceArtifact) -> str:
    return content_identity(artifact)


def write_artifact(path: Path, artifact: EvidenceArtifact) -> tuple[bool, str]:
    """Write the artifact. Returns ``(changed, rendered_text)``.

    ``changed`` reflects semantic changes only: regenerating the same snapshot
    with a different ``generated_at`` is not a change.
    """
    rendered = serialize(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    changed = True
    try:
        existing_raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        existing_raw = None
    if isinstance(existing_raw, dict):
        try:
            existing_artifact = artifact_from_dict(existing_raw)
            existing_semantic = canonical_dump(semantic_content(existing_artifact))
        except (KeyError, TypeError, ValueError):
            existing_semantic = None
        if existing_semantic == canonical_dump(semantic_content(artifact)):
            changed = False
    if changed:
        path.write_text(rendered, encoding="utf-8", newline="\n")
    return changed, rendered
