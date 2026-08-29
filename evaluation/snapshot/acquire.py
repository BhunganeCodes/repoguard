"""Snapshot acquisition orchestration.

One case = one immutable snapshot at a fixed URL + pinned commit. The
acquisition writes the snapshot directly to its final location in the
snapshot store; completed snapshots are never moved or overwritten.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml

from evaluation.snapshot import git
from evaluation.snapshot.commits import SNAPSHOT_HASH_SCHEME
from evaluation.snapshot.errors import SnapshotError, SnapshotExistsError
from evaluation.snapshot.hashing import hash_snapshot_tree
from evaluation.snapshot.inventory import build_inventory, inventory_from_dict
from evaluation.snapshot.models import (
    AcquisitionOptions,
    DatasetManifest,
    DatasetRef,
    ManifestCase,
    SnapshotRecord,
    SnapshotResult,
)
from evaluation.snapshot.paths import (
    CHECKOUT_DIR,
    INVENTORY_FILE,
    SNAPSHOT_RECORD_FILE,
    snapshot_dir,
)

_ACQUIRED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> str:
    """Current UTC timestamp, second precision, Z-suffixed and lexically sorted."""
    now = datetime.now(UTC).replace(microsecond=0)
    return now.astimezone(UTC).strftime(_ACQUIRED_AT_FORMAT)


def _write_yaml(path: Path, data: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, width=100)


def _load_snapshot_record(record_path: Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SnapshotExistsError(f"existing snapshot record is unreadable: {record_path}") from exc
    if not isinstance(raw, dict):
        raise SnapshotExistsError(f"existing snapshot record is invalid: {record_path}")
    return raw


def acquire_case(
    case: ManifestCase,
    manifest: DatasetManifest,
    store: Path,
) -> SnapshotResult:
    """Acquire an immutable snapshot for one case into the store.

    Idempotent when a snapshot for the same pinned commit already exists;
    fail-closed (never overwrite) when the target holds a different commit
    or a partial acquisition.
    """
    target = snapshot_dir(store, case)
    record_path = target / SNAPSHOT_RECORD_FILE

    if target.exists():
        if not record_path.is_file():
            raise SnapshotExistsError(f"partial snapshot directory (no record): {target}")
        existing = _load_snapshot_record(record_path)
        existing_verified = existing.get("verified_commit")
        if existing_verified == case.pinned_commit:
            return load_snapshot_result(target, case)
        raise SnapshotExistsError(
            "snapshot store is immutable: "
            f"{target} already holds commit {existing_verified!r}, "
            f"requested {case.pinned_commit}"
        )

    target.mkdir(parents=True, exist_ok=False)
    worktree = target / CHECKOUT_DIR
    try:
        git.init_repository(worktree, case.url)
        options = git.fetch_commit(worktree, case.url, case.pinned_commit)
        git.checkout_commit(worktree, case.pinned_commit)
        verified = git.verified_head(worktree, case.pinned_commit)
        content_hash = hash_snapshot_tree(worktree)
        acquired_at = utc_now()

        record = SnapshotRecord(
            identity=f"{SNAPSHOT_HASH_SCHEME}:{content_hash}",
            candidate_id=case.candidate_id,
            name=case.name,
            repository_url=case.url,
            requested_commit=case.pinned_commit,
            verified_commit=verified,
            content_hash=content_hash,
            acquired_at=acquired_at,
            git_version=git.git_version(),
            dataset=DatasetRef(name=manifest.name, version=manifest.version),
            acquisition=options,
        )
        inventory = build_inventory(
            case=case,
            verified_commit=verified,
            content_hash=content_hash,
            acquired_at=acquired_at,
            tracked_files=git.list_tracked_files(worktree),
            top_level=git.list_top_level_entries(worktree),
        )
        _write_yaml(record_path, record.to_dict())
        _write_yaml(target / INVENTORY_FILE, inventory.to_dict())
        return SnapshotResult(
            case=case, record=record, inventory=inventory, path=target, idempotent=False
        )
    except SnapshotError:
        shutil.rmtree(target, ignore_errors=True)
        raise


def load_snapshot_result(target: Path, case: ManifestCase) -> SnapshotResult:
    """Reconstruct a result from an existing, already-verified snapshot."""
    record_path = target / SNAPSHOT_RECORD_FILE
    record_raw = _load_snapshot_record(record_path)
    dataset_mapping = record_raw.get("dataset")
    dataset_raw: dict[str, object] = dataset_mapping if isinstance(dataset_mapping, dict) else {}
    acquisition_mapping = record_raw.get("acquisition")
    acquisition_raw: dict[str, object] = (
        acquisition_mapping if isinstance(acquisition_mapping, dict) else {}
    )
    raw_depth = acquisition_raw.get("depth")
    depth: int | None = (
        raw_depth if isinstance(raw_depth, int) and not isinstance(raw_depth, bool) else None
    )
    record = SnapshotRecord(
        identity=str(record_raw.get("identity", "")),
        candidate_id=str(record_raw.get("candidate_id", case.candidate_id)),
        name=str(record_raw.get("name", case.name)),
        repository_url=str(record_raw.get("repository_url", case.url)),
        requested_commit=str(record_raw.get("requested_commit", case.pinned_commit)),
        verified_commit=str(record_raw.get("verified_commit", "")),
        content_hash=str(record_raw.get("content_hash", "")),
        acquired_at=str(record_raw.get("acquired_at", "")),
        git_version=str(record_raw.get("git_version", "")),
        dataset=DatasetRef(
            name=str(dataset_raw.get("name", "")), version=str(dataset_raw.get("version", ""))
        ),
        acquisition=AcquisitionOptions(
            remote_scheme=str(acquisition_raw.get("remote_scheme", "")),
            blob_filter=bool(acquisition_raw.get("blob_filter", False)),
            depth=depth,
        ),
    )
    inventory_raw = _load_inventory_mapping(target / INVENTORY_FILE)
    inventory = inventory_from_dict(inventory_raw, fallback_ecosystem=case.ecosystem)
    return SnapshotResult(
        case=case, record=record, inventory=inventory, path=target, idempotent=True
    )


def _load_inventory_mapping(path: Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SnapshotExistsError(f"existing inventory is unreadable: {path}") from exc
    if not isinstance(raw, dict):
        raise SnapshotExistsError(f"existing inventory is invalid: {path}")
    return raw
