"""Deterministic serialization and content identity tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from evaluation.evidence._version import EXTRACTION_SCHEME
from evaluation.evidence.models import EvidenceArtifact, EvidenceItem
from evaluation.evidence.serialize import (
    canonical_dump,
    content_identity,
    serialize,
    write_artifact,
)


def _item(category: str, evidence_type: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"{category}.{evidence_type}",
        case_id="C001",
        category=category,
        evidence_type=evidence_type,
        status="FOUND",
        observation=f"{category} {evidence_type} observed.",
        source_paths=[f"{category}/{evidence_type}.type.txt"],
        extractor=category,
        extractor_version="1",
    )


def _artifact(generated_at: str) -> EvidenceArtifact:
    return EvidenceArtifact(
        schema_version=1,
        case_id="C001",
        name="lib",
        repository_url="https://example.com/x.git",
        requested_commit="a",
        verified_commit="b",
        snapshot_content_hash="c",
        extraction_version="v1",
        evidence_identity="",
        generated_at=generated_at,
        items=[_item("testing", "test_files"), _item("architecture", "top_level_structure")],
    )


def test_canonical_dump_is_deterministic() -> None:
    data = {"b": {"z": 1, "a": 2}, "a": [3, 1, 2]}
    assert canonical_dump(data) == canonical_dump(data)
    assert canonical_dump(data) == canonical_dump({"b": {"a": 2, "z": 1}, "a": [3, 1, 2]})


def test_serialization_is_sorted_and_stable() -> None:
    first = serialize(_artifact("2026-08-28T00:00:00Z"))
    second = serialize(_artifact("2026-08-28T00:00:00Z"))
    assert first == second
    loaded = yaml.safe_load(first)
    assert loaded["schema_version"] == 1


def test_identity_is_independent_of_generated_at() -> None:
    identity_one = content_identity(_artifact("2026-08-28T00:00:00Z"))
    identity_two = content_identity(_artifact("2027-01-02T03:04:05Z"))
    assert identity_one == identity_two
    assert identity_one.startswith(EXTRACTION_SCHEME + ":")


def test_identity_changes_when_content_changes() -> None:
    artifact = _artifact("2026-08-28T00:00:00Z")
    base = content_identity(artifact)
    artifact.items[0].observation = "A different observation."
    assert content_identity(artifact) != base


def test_write_artifact_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "evidence.yaml"
    artifact = _artifact("2026-08-28T00:00:00Z")
    changed_first, text_first = write_artifact(target, artifact)
    changed_second, text_second = write_artifact(target, artifact)
    assert changed_first is True
    assert changed_second is False
    assert text_first == text_second
    assert target.read_text(encoding="utf-8") == text_first


def test_write_not_changed_when_only_timestamp_differs(tmp_path: Path) -> None:
    target = tmp_path / "evidence.yaml"
    first = _artifact("2026-08-28T00:00:00Z")
    first.evidence_identity = content_identity(first)
    assert write_artifact(target, first)[0] is True
    regenerated = _artifact("2027-09-09T09:09:09Z")
    regenerated.evidence_identity = content_identity(regenerated)
    changed, _rendered = write_artifact(target, regenerated)
    assert changed is False


def test_write_artifact_roundtrip_identity(tmp_path: Path) -> None:
    target = tmp_path / "evidence.yaml"
    artifact = _artifact("2026-08-28T00:00:00Z")
    artifact.evidence_identity = content_identity(artifact)
    identity = artifact.evidence_identity
    _changed, text = write_artifact(target, artifact)
    reloaded = yaml.safe_load(text)
    assert reloaded["evidence_identity"] == identity
