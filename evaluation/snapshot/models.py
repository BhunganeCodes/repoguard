"""Data models for the snapshot subsystem.

Models are plain dataclasses: parsing, validation, and serialization are
explicit so nothing hidden happens between the frozen manifest and the
recorded snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ManifestCase:
    """One entry of the frozen dataset manifest (an included repository)."""

    candidate_id: str
    name: str
    url: str
    pinned_commit: str
    ecosystem: str
    license: str
    dataset_decision: str
    dataset_status: str


@dataclass(frozen=True)
class DatasetManifest:
    """The frozen evaluation dataset manifest, parsed and validated."""

    name: str
    version: str
    creation_date: str
    status: str
    source: str
    cases: list[ManifestCase]


@dataclass(frozen=True)
class DatasetRef:
    """Reference to the frozen dataset a snapshot belongs to."""

    name: str
    version: str


@dataclass(frozen=True)
class AcquisitionOptions:
    """What git options were used so the acquisition is reproducible."""

    remote_scheme: str
    blob_filter: bool
    depth: int | None


@dataclass(frozen=True)
class SnapshotRecord:
    """Immutable metadata record for one acquired snapshot."""

    schema_version: int = 1
    identity: str = ""
    candidate_id: str = ""
    name: str = ""
    repository_url: str = ""
    requested_commit: str = ""
    verified_commit: str = ""
    content_hash: str = ""
    acquired_at: str = ""
    git_version: str = ""
    dataset: DatasetRef = field(default_factory=lambda: DatasetRef("", ""))
    acquisition: AcquisitionOptions = field(
        default_factory=lambda: AcquisitionOptions("", False, None)
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Presence:
    """Raw presence observation: found at least once, plus the evidence paths."""

    present: bool
    paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LanguageCount:
    """Detected language name and how many tracked files it was observed in."""

    language: str
    file_count: int


@dataclass(frozen=True)
class Inventory:
    """Machine-readable repository inventory. Raw observations only; no scores."""

    schema_version: int = 1
    repository_id: str = ""
    repository_url: str = ""
    requested_commit: str = ""
    verified_commit: str = ""
    content_hash: str = ""
    acquired_at: str = ""
    ecosystem: str = ""
    detected_languages: list[LanguageCount] = field(default_factory=list)
    tracked_file_count: int = 0
    source_file_count: int = 0
    test_file_count: int = 0
    documentation_file_count: int = 0
    dependency_manifest: Presence = field(default_factory=lambda: Presence(present=False))
    lockfile: Presence = field(default_factory=lambda: Presence(present=False))
    ci: Presence = field(default_factory=lambda: Presence(present=False))
    docker: Presence = field(default_factory=lambda: Presence(present=False))
    readme: str | None = None
    license_file: str | None = None
    top_level: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotResult:
    """Outcome of an acquisition for one case."""

    case: ManifestCase
    record: SnapshotRecord
    inventory: Inventory
    path: Path
    idempotent: bool
