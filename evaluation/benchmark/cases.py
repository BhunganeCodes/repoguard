"""Dataset, snapshot, and evidence binding for a benchmark run.

Everything here is read-only: the frozen dataset manifest, the immutable
snapshots in the snapshot store, and the frozen evidence artifacts. The
runner never modifies them. Every verification fails closed and reports a
structured :class:`BenchmarkArtifactError` with a stable ``kind`` that the
runner records as the case outcome (docs/benchmark-runner.md,
"Executing a case").
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from evaluation.benchmark._version import DATASET_SCHEME
from evaluation.benchmark.errors import BenchmarkArtifactError, BenchmarkDatasetError
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import canonical_dump, recompute_identity
from evaluation.evidence.validate import artifact_from_dict, validate_artifact
from evaluation.snapshot.commits import SNAPSHOT_HASH_SCHEME, normalize_sha
from evaluation.snapshot.errors import ManifestError
from evaluation.snapshot.hashing import hash_snapshot_tree
from evaluation.snapshot.manifest import case_by_id, load_manifest
from evaluation.snapshot.models import DatasetManifest, ManifestCase
from evaluation.snapshot.paths import SNAPSHOT_RECORD_FILE, default_store, snapshot_dir

# Datasets run by default: candidates whose license is confirmed.
_CONFIRMED_STATUS = "confirmed"
# Statuses that may be run but only when explicitly selected.
_PENDING_STATUSES = frozenset({"pending_license_confirmation"})
# Statuses that are never part of a benchmark run (explicit or default).
_EXCLUDED_STATUSES = frozenset({"excluded"})


def load_dataset(path: Path) -> DatasetManifest:
    """Load and validate the frozen dataset manifest (fail closed)."""
    try:
        return load_manifest(path)
    except Exception as exc:
        raise BenchmarkDatasetError(f"cannot load dataset manifest: {exc}") from exc


def dataset_identity(path: Path) -> str:
    """Deterministic content identity of the frozen dataset manifest.

    The hash covers the manifest exactly as on disk (including provenance and
    freeze metadata); two identical manifests always produce the same
    identity regardless of where the file lives.
    """
    raw = _load_dataset_mapping(path)
    payload = canonical_dump(raw)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{DATASET_SCHEME}:{digest}"


def _load_dataset_mapping(path: Path) -> dict[str, Any]:
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BenchmarkDatasetError(f"unreadable dataset manifest: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise BenchmarkDatasetError(f"dataset manifest root is not a mapping: {path}")
    return raw


def select_cases(
    manifest: DatasetManifest, explicit: list[str] | None = None
) -> list[ManifestCase]:
    """Determine which cases a run evaluates.

    Default: every confirmed candidate in the frozen dataset. An explicit
    selection must reference candidates present in the dataset; a
    licence-pending candidate is allowed with an explicit selection (the
    caller warns), and excluded candidates are always rejected.
    """
    if explicit:
        selected: list[ManifestCase] = []
        for candidate_id in explicit:
            try:
                case = case_by_id(manifest, candidate_id)
            except ManifestError as exc:
                raise BenchmarkDatasetError(str(exc)) from exc
            if case.dataset_status in _EXCLUDED_STATUSES:
                raise BenchmarkDatasetError(
                    f"candidate '{candidate_id}' is excluded from the dataset and cannot be run"
                )
            selected.append(case)
        return selected
    return [case for case in manifest.cases if case.dataset_status == _CONFIRMED_STATUS]


def unconfirmed_status(case: ManifestCase) -> bool:
    """True when the case needs approval to run but was explicitly selected."""
    return case.dataset_status in _PENDING_STATUSES


def snapshot_artifacts(case: ManifestCase, store: Path | None = None) -> Path:
    """The immutable snapshot directory for a case (may not exist yet)."""
    return snapshot_dir(store or default_store(), case)


class SnapshotInfo:
    """Verified facts about an immutable snapshot for one case."""

    def __init__(self, content_hash: str, verified_commit: str) -> None:
        self.content_hash = content_hash
        self.verified_commit = verified_commit


def verify_snapshot(
    snapshot_root: Path,
    case: ManifestCase,
    dataset_name: str,
    dataset_version: str,
) -> SnapshotInfo:
    """Verify snapshot existence and identity against the frozen dataset.

    The checkout's content hash is recomputed and must equal the recorded
    content hash, which must equal the snapshot identity suffix (the same
    check ``python -m evaluation.snapshot inspect --verify`` performs).
    """
    record_path = snapshot_root / SNAPSHOT_RECORD_FILE
    if not snapshot_root.is_dir():
        raise BenchmarkArtifactError(
            "snapshot_missing", f"snapshot not present for {case.candidate_id}: {snapshot_root}"
        )
    if not record_path.is_file():
        raise BenchmarkArtifactError("snapshot_missing", f"snapshot record missing: {record_path}")
    try:
        raw: object = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BenchmarkArtifactError("snapshot_unreadable", str(exc)) from exc
    if not isinstance(raw, dict):
        raise BenchmarkArtifactError("snapshot_unreadable", "snapshot record is not a mapping")

    def _field(key: str) -> object:
        return raw.get(key)

    if _field("schema_version") != 1:
        raise BenchmarkArtifactError("snapshot_mismatch", "snapshot record has an unknown schema")
    identity = _field("identity")
    content_hash = _field("content_hash")
    if not isinstance(identity, str) or not isinstance(content_hash, str):
        raise BenchmarkArtifactError("snapshot_mismatch", "snapshot identity is missing")
    if not identity.startswith(f"{SNAPSHOT_HASH_SCHEME}:") or not identity.endswith(content_hash):
        raise BenchmarkArtifactError(
            "snapshot_mismatch", "snapshot identity does not match its content hash"
        )
    if str(_field("candidate_id")) != case.candidate_id:
        raise BenchmarkArtifactError(
            "snapshot_mismatch", "snapshot case id does not match the dataset"
        )

    def _commit(key: str) -> str:
        value = _field(key)
        if not isinstance(value, str):
            raise BenchmarkArtifactError("snapshot_mismatch", f"snapshot {key} is missing")
        try:
            return normalize_sha(value)
        except Exception as exc:
            raise BenchmarkArtifactError("snapshot_mismatch", f"invalid {key}: {exc}") from exc

    requested = _commit("requested_commit")
    verified = _commit("verified_commit")
    if requested != case.pinned_commit or verified != case.pinned_commit:
        raise BenchmarkArtifactError(
            "snapshot_mismatch",
            f"snapshot commit {verified} does not match pinned commit {case.pinned_commit}",
        )

    dataset_block = _field("dataset")
    if not isinstance(dataset_block, dict):
        raise BenchmarkArtifactError("snapshot_mismatch", "snapshot dataset reference is missing")
    block_name = str(dataset_block.get("name"))
    block_version = str(dataset_block.get("version"))
    if block_name != dataset_name or block_version != dataset_version:
        raise BenchmarkArtifactError(
            "snapshot_mismatch", "snapshot dataset reference does not match the frozen dataset"
        )

    checkout = snapshot_root / "checkout"
    if not checkout.is_dir():
        raise BenchmarkArtifactError("snapshot_mismatch", "snapshot checkout directory is missing")
    current_hash = hash_snapshot_tree(checkout)
    if current_hash != content_hash:
        raise BenchmarkArtifactError("snapshot_mismatch", "snapshot content hash did not verify")
    return SnapshotInfo(content_hash=content_hash, verified_commit=verified)


def load_evidence(
    snapshot_root: Path,
    case: ManifestCase,
    snapshot: SnapshotInfo,
) -> EvidenceArtifact:
    """Load, validate, and bind the frozen evidence artifact for a case.

    The artifact must be structurally valid, its recomputed identity must
    match the recorded one, and it must reference exactly this snapshot and
    dataset case (fail closed; no silent substitution).
    """
    evidence_path = snapshot_root / "evidence.yaml"
    if not evidence_path.is_file():
        raise BenchmarkArtifactError("evidence_missing", f"evidence not present: {evidence_path}")
    try:
        raw: object = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BenchmarkArtifactError("evidence_unreadable", str(exc)) from exc
    if not isinstance(raw, dict):
        raise BenchmarkArtifactError("evidence_unreadable", "evidence artifact is not a mapping")
    try:
        artifact = artifact_from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise BenchmarkArtifactError("evidence_mismatch", f"invalid evidence: {exc}") from exc

    problems = validate_artifact(artifact)
    if problems:
        raise BenchmarkArtifactError("evidence_mismatch", "; ".join(problems))
    if recompute_identity(artifact) != artifact.evidence_identity:
        raise BenchmarkArtifactError(
            "evidence_mismatch", "evidence identity does not match its content"
        )
    if artifact.case_id != case.candidate_id:
        raise BenchmarkArtifactError(
            "evidence_mismatch", "evidence case id does not match the dataset case"
        )
    if artifact.verified_commit != snapshot.verified_commit:
        raise BenchmarkArtifactError(
            "evidence_mismatch",
            (
                "evidence commit "
                f"{artifact.verified_commit} does not match snapshot {snapshot.verified_commit}"
            ),
        )
    if artifact.snapshot_content_hash != snapshot.content_hash:
        raise BenchmarkArtifactError(
            "evidence_mismatch", "evidence does not reference this snapshot content"
        )
    return artifact
