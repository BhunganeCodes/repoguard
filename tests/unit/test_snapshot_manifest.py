"""Dataset manifest parsing tests."""

from __future__ import annotations

import pytest
import yaml
from conftest import default_case, write_manifest

from evaluation.snapshot.errors import InvalidShaError, ManifestError
from evaluation.snapshot.manifest import case_by_id, load_manifest

SHA = "e80360834b59dd4c8bfd45344ad1478ab9f86565"


def test_loads_valid_manifest(tmp_path) -> None:
    path = write_manifest(
        tmp_path / "manifest.yaml", [default_case(url="file:///x", pinned_commit=SHA)]
    )
    manifest = load_manifest(path)
    assert manifest.name == "test-dataset"
    assert manifest.version == "0.0.0"
    assert len(manifest.cases) == 1
    case = manifest.cases[0]
    assert case.candidate_id == "T001"
    assert case.url == "file:///x"
    assert case.pinned_commit == SHA
    assert case.dataset_decision == "include"


def test_uppercase_pinned_commit_is_normalized(tmp_path) -> None:
    path = write_manifest(
        tmp_path / "m.yaml", [default_case(url="file:///x", pinned_commit=SHA.upper())]
    )
    assert load_manifest(path).cases[0].pinned_commit == SHA


def test_creation_date_accepts_yaml_date_object(tmp_path) -> None:
    # Unquoted 2026-08-28 parses as a YAML date; it must be accepted and
    # normalized to an ISO string.
    manifest: dict[str, object] = {
        "dataset": {
            "name": "test-dataset",
            "version": "0.0.0",
            "creation_date": "2026-08-28",
            "status": "frozen",
        },
        "candidates": [default_case(url="file:///x", pinned_commit=SHA)],
    }
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    loaded = load_manifest(path)
    assert loaded.creation_date in ("2026-08-28", "2026-08-28T00:00:00")


def test_missing_manifest_raises(tmp_path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "nope.yaml")


def test_invalid_yaml_raises(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("not: [valid: yaml\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_missing_dataset_block_raises(tmp_path) -> None:
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump({"candidates": []}), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_missing_required_case_field_raises(tmp_path) -> None:
    case = default_case(url="file:///x", pinned_commit=SHA)
    del case["url"]
    path = write_manifest(tmp_path / "m.yaml", [case])
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_invalid_pinned_commit_raises(tmp_path) -> None:
    case = default_case(url="file:///x", pinned_commit="short")
    path = write_manifest(tmp_path / "m.yaml", [case])
    with pytest.raises(InvalidShaError):
        load_manifest(path)


def test_case_by_id_found_and_not_found(tmp_path) -> None:
    path = write_manifest(tmp_path / "m.yaml", [default_case(url="file:///x", pinned_commit=SHA)])
    manifest = load_manifest(path)
    assert case_by_id(manifest, "T001").candidate_id == "T001"
    with pytest.raises(ManifestError):
        case_by_id(manifest, "X999")
