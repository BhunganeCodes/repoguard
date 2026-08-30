"""Evidence extraction orchestration.

Extraction runs every registered extractor against a single snapshot
checkout and assembles a deterministic :class:`EvidenceArtifact`. The
artifact is then serialized and written next to the immutable snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evaluation.evidence._version import EVIDENCE_EXTRACTION_VERSION
from evaluation.evidence.errors import EvidenceError
from evaluation.evidence.extractors import registry
from evaluation.evidence.extractors.base import ExtractionContext
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import content_identity
from evaluation.snapshot import git
from evaluation.snapshot.paths import CHECKOUT_DIR, SNAPSHOT_RECORD_FILE

_ACQUIRED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> str:
    """Current UTC timestamp, second precision, Z-suffixed and lexically sorted."""
    now = datetime.now(UTC).replace(microsecond=0)
    return now.astimezone(UTC).strftime(_ACQUIRED_AT_FORMAT)


def _load_record(snapshot_dir: Path) -> dict[str, Any]:
    record_path = snapshot_dir / SNAPSHOT_RECORD_FILE
    try:
        raw = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvidenceError(f"snapshot record is unreadable: {record_path}") from exc
    if not isinstance(raw, dict):
        raise EvidenceError(f"snapshot record is invalid: {record_path}")
    return raw


def extract_snapshot_directory(snapshot_dir: Path) -> EvidenceArtifact:
    """Extract evidence from one snapshot and return an unsaved artifact."""
    record = _load_record(snapshot_dir)
    checkout = snapshot_dir / CHECKOUT_DIR
    if not checkout.is_dir():
        raise EvidenceError(f"snapshot has no checkout directory: {checkout}")
    tracked = git.list_tracked_files(checkout)
    case_id = str(record.get("candidate_id", ""))
    if not case_id:
        raise EvidenceError(f"snapshot record has no candidate_id: {snapshot_dir}")

    context = ExtractionContext(
        checkout=checkout,
        tracked_files=tracked,
        case_id=case_id,
        name=str(record.get("name", "")),
        repository_url=str(record.get("repository_url", "")),
        requested_commit=str(record.get("requested_commit", "")),
        verified_commit=str(record.get("verified_commit", "")),
        snapshot_content_hash=str(record.get("content_hash", "")),
    )

    items = []
    for _category, _name, _version, extract_fn in registry():
        items.extend(extract_fn(context))
    items.sort(key=lambda item: (item.category, item.evidence_type))

    artifact = EvidenceArtifact(
        schema_version=1,
        case_id=case_id,
        name=context.name,
        repository_url=context.repository_url,
        requested_commit=context.requested_commit,
        verified_commit=context.verified_commit,
        snapshot_content_hash=context.snapshot_content_hash,
        extraction_version=EVIDENCE_EXTRACTION_VERSION,
        evidence_identity="",
        generated_at=utc_now(),
        items=items,
    )
    artifact.evidence_identity = content_identity(artifact)
    return artifact
