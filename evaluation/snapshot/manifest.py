"""Dataset manifest loading and validation.

Fail-closed: a missing or malformed required field raises ManifestError
instead of silently proceeding.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml

from evaluation.snapshot.commits import normalize_sha
from evaluation.snapshot.errors import ManifestError
from evaluation.snapshot.models import DatasetManifest, ManifestCase

_REQUIRED_CASE_FIELDS = (
    "candidate_id",
    "name",
    "url",
    "pinned_commit",
    "ecosystem",
    "license",
    "dataset_decision",
    "dataset_status",
)


def load_manifest(path: Path) -> DatasetManifest:
    """Parse and validate the frozen dataset manifest at path."""
    if not path.is_file():
        raise ManifestError(f"dataset manifest not found: {path}")
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"dataset manifest is not valid YAML: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"dataset manifest root must be a mapping: {path}")
    cases_raw = raw.get("candidates")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ManifestError("dataset manifest has no candidates list")
    cases: list[ManifestCase] = []
    for index, entry in enumerate(cases_raw):
        if not isinstance(entry, dict):
            raise ManifestError(f"dataset manifest candidate #{index} is not a mapping")
        for field_name in _REQUIRED_CASE_FIELDS:
            value = entry.get(field_name)
            if value is None and field_name != "name":
                raise ManifestError(
                    f"dataset manifest candidate #{index} is missing '{field_name}'"
                )
        cases.append(
            ManifestCase(
                candidate_id=str(entry["candidate_id"]),
                name=str(entry.get("name") or entry["candidate_id"]),
                url=str(entry["url"]),
                pinned_commit=normalize_sha(str(entry["pinned_commit"])),
                ecosystem=str(entry["ecosystem"]),
                license=str(entry["license"]),
                dataset_decision=str(entry["dataset_decision"]),
                dataset_status=str(entry["dataset_status"]),
            )
        )
    dataset = raw.get("dataset")
    if not isinstance(dataset, dict):
        raise ManifestError("dataset manifest is missing the 'dataset' mapping")
    name = dataset.get("name")
    version = dataset.get("version")
    creation_date_value = dataset.get("creation_date")
    status = dataset.get("status")
    if not isinstance(name, str) or not name:
        raise ManifestError("dataset manifest is missing 'dataset.name'")
    if not isinstance(version, str) or not version:
        raise ManifestError("dataset manifest is missing 'dataset.version'")
    if isinstance(creation_date_value, (date, datetime)):
        creation_date = creation_date_value.isoformat()
    elif isinstance(creation_date_value, str):
        creation_date = creation_date_value
    else:
        raise ManifestError("dataset manifest is missing 'dataset.creation_date'")
    if not isinstance(status, str):
        raise ManifestError("dataset manifest is missing 'dataset.status'")
    return DatasetManifest(
        name=name,
        version=version,
        creation_date=creation_date,
        status=status,
        source=str(path),
        cases=cases,
    )


def case_by_id(manifest: DatasetManifest, candidate_id: str) -> ManifestCase:
    """Return the manifest case with candidate_id or raise ManifestError."""
    for case in manifest.cases:
        if case.candidate_id == candidate_id:
            return case
    raise ManifestError(
        f"candidate '{candidate_id}' not found in dataset manifest {manifest.source}"
    )
