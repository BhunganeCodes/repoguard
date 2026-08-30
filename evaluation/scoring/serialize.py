"""Deterministic serialization and content identity for assessments.

The assessment identity is a SHA-256 over the canonical, key-sorted YAML
rendering of every semantic field of the composed assessment, prefixed with
the scheme ``repoguard-assessment-v1``. The identity itself is excluded.
The composed artifact contains no runtime metadata, so scoring the same
authored assessment twice produces byte-identical output.
"""

from __future__ import annotations

import hashlib
from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import canonical_dump
from evaluation.scoring._version import ASSESSMENT_SCHEMA_VERSION, ASSESSMENT_SCHEME
from evaluation.scoring.compute import compute_dimensions, compute_summary, parse_criterion
from evaluation.scoring.errors import ScoringError

_SEMANTIC_EXCLUDED = frozenset({"assessment_identity"})


def assessment_identity(assessment: dict[str, Any]) -> str:
    """Deterministic content hash of a composed assessment payload."""
    content = {key: value for key, value in assessment.items() if key not in _SEMANTIC_EXCLUDED}
    payload = canonical_dump(content)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{ASSESSMENT_SCHEME}:{digest}"


def compose_payload(data: dict[str, Any], evidence: EvidenceArtifact) -> tuple[dict[str, Any], str]:
    """Compose the semantic assessment payload and its content identity.

    Dimension totals, the summary, and the identity are always recomputed
    deterministically rather than copied from the input, so a stale or
    falsified aggregate can never propagate.
    """
    criteria = [parse_criterion(raw) for raw in data.get("criteria", [])]
    dimensions = compute_dimensions(criteria)
    summary = compute_summary(criteria, dimensions)

    name = data.get("name")
    if not isinstance(name, str) or not name:
        name = evidence.name

    payload: dict[str, Any] = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "case_id": str(data["case_id"]),
        "name": name,
        "rubric_version": str(data["rubric_version"]),
        "evidence_identity": str(data["evidence_identity"]),
        "criteria": [criterion.to_dict() for criterion in criteria],
        "dimensions": [dimension.to_dict() for dimension in dimensions],
        "summary": summary.to_dict(),
    }
    return payload, assessment_identity(payload)


def compose_assessment(data: dict[str, Any], evidence: EvidenceArtifact) -> dict[str, Any]:
    """Produce the structured assessment artifact from an authored assessment."""
    payload, identity = compose_payload(data, evidence)
    payload["assessment_identity"] = identity
    return payload


def require_complete(assessment: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when the composed assessment is not complete."""
    summary = assessment.get("summary")
    if not isinstance(summary, dict) or summary.get("complete") is not True:
        pending = summary.get("pending") if isinstance(summary, dict) else []
        raise ScoringError(
            "assessment is not scoreable: criteria pending assessment: "
            + (", ".join(pending) if pending else "unknown")
        )
    return assessment
