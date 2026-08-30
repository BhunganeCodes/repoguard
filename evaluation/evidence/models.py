"""Data models for deterministic evidence extraction.

Every :class:`EvidenceItem` is a single auditable fact extracted from a
snapshot checkout. Fields follow the schema required by the evaluation
framework:

* ``evidence_id`` - stable, unique identifier, ``{category}.{type}``
* ``case_id`` - repository/candidate ID (e.g. ``C001``)
* ``category`` - one of the five rubric dimensions
* ``evidence_type`` - semantic type of the observation
* ``status`` - FOUND / NOT_FOUND / UNCERTAIN / NOT_APPLICABLE
* ``source_paths`` - concrete repository-relative paths backing the claim
* ``observation`` - free-form factual statement (no scoring, no ranking)
* ``extractor`` / ``extractor_version`` - provenance of the claim

Items are signal only: they never carry a quality score, rank, or tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EvidenceItem:
    evidence_id: str
    case_id: str
    category: str
    evidence_type: str
    status: str
    observation: str
    source_paths: list[str] = field(default_factory=list)
    extractor: str = ""
    extractor_version: str = ""
    notes: str | None = None
    observed: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "case_id": self.case_id,
            "category": self.category,
            "evidence_type": self.evidence_type,
            "status": self.status,
            "observation": self.observation,
            "source_paths": list(self.source_paths),
            "extractor": self.extractor,
            "extractor_version": self.extractor_version,
        }
        if self.notes is not None:
            data["notes"] = self.notes
        if self.observed is not None:
            data["observed"] = self.observed
        return data


@dataclass(slots=True)
class EvidenceArtifact:
    """Deterministic result of extracting evidence from one snapshot."""

    schema_version: int
    case_id: str
    name: str
    repository_url: str
    requested_commit: str
    verified_commit: str
    snapshot_content_hash: str
    extraction_version: str
    evidence_identity: str
    generated_at: str
    items: list[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "name": self.name,
            "repository_url": self.repository_url,
            "requested_commit": self.requested_commit,
            "verified_commit": self.verified_commit,
            "snapshot_content_hash": self.snapshot_content_hash,
            "extraction_version": self.extraction_version,
            "evidence_identity": self.evidence_identity,
            "generated_at": self.generated_at,
            "items": [item.to_dict() for item in self.items],
        }
