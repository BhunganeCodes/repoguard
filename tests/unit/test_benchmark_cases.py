"""Dataset selection, snapshot verification, and evidence binding."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from benchmark_helpers import (
    case_dict,
    make_case,
    read_snapshot_content_hash,
    write_dataset,
    write_evidence,
    write_snapshot_store,
)

from evaluation.benchmark.cases import (
    dataset_identity,
    load_dataset,
    load_evidence,
    select_cases,
    verify_snapshot,
)
from evaluation.benchmark.errors import BenchmarkArtifactError, BenchmarkDatasetError
from evaluation.evidence.serialize import content_identity
from evaluation.snapshot.commits import SNAPSHOT_HASH_SCHEME


def test_load_dataset_and_identity(tmp_path: Path) -> None:
    path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    dataset = load_dataset(path)
    assert dataset.name == "repoguard-evaluation-dataset"
    assert dataset.version == "1.0.0"
    identity = dataset_identity(path)
    assert identity.startswith("repoguard-dataset-v1:")
    # An identical clone produces the identical identity.
    clone = tmp_path / "clone.yaml"
    clone.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    assert dataset_identity(clone) == identity


def test_dataset_identity_changes_with_manifest(tmp_path: Path) -> None:
    path = write_dataset(tmp_path / "dataset.yaml", [case_dict("C001")])
    original = dataset_identity(path)
    tampered = write_dataset(tmp_path / "tampered.yaml", [case_dict("C001", commit="b" * 40)])
    assert dataset_identity(tampered) != original


def test_dataset_identity_changes_with_licence_status(tmp_path: Path) -> None:
    confirmed = write_dataset(tmp_path / "a.yaml", [case_dict("C001")])
    pending = write_dataset(
        tmp_path / "b.yaml", [case_dict("C001", status="pending_license_confirmation")]
    )
    assert dataset_identity(confirmed) != dataset_identity(pending)


def test_load_dataset_fails_closed_on_missing(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkDatasetError):
        load_dataset(tmp_path / "nope.yaml")


def test_selection_defaults_to_confirmed_only(tmp_path: Path) -> None:
    dataset_path = write_dataset(
        tmp_path / "dataset.yaml",
        [
            case_dict("C001"),
            case_dict("C011", status="pending_license_confirmation"),
            case_dict("C007", status="excluded"),
        ],
    )
    dataset = load_dataset(dataset_path)
    selected = select_cases(dataset)
    assert [case.candidate_id for case in selected] == ["C001"]


def test_explicit_selection_runs_pending_but_never_excluded(tmp_path: Path) -> None:
    dataset_path = write_dataset(
        tmp_path / "dataset.yaml",
        [
            case_dict("C001"),
            case_dict("C011", status="pending_license_confirmation"),
            case_dict("C007", status="excluded"),
        ],
    )
    dataset = load_dataset(dataset_path)
    selected = select_cases(dataset, explicit=["C011"])
    assert [case.candidate_id for case in selected] == ["C011"]
    with pytest.raises(BenchmarkDatasetError):
        select_cases(dataset, explicit=["C007"])
    with pytest.raises(BenchmarkDatasetError):
        select_cases(dataset, explicit=["nope"])


def test_verify_snapshot_and_evidence_ok(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    evidence = write_evidence(snapshot_root, case)
    info = verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    assert info.content_hash == read_snapshot_content_hash(snapshot_root)
    loaded = load_evidence(snapshot_root, case, info)
    assert loaded.evidence_identity == evidence.evidence_identity


def test_missing_snapshot_kind(tmp_path: Path) -> None:
    case = make_case("C001")
    with pytest.raises(BenchmarkArtifactError) as exc:
        verify_snapshot(tmp_path / "nope", case, "d", "1")
    assert exc.value.kind == "snapshot_missing"


def test_missing_evidence_kind(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    info = verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    with pytest.raises(BenchmarkArtifactError) as exc:
        load_evidence(snapshot_root, case, info)
    assert exc.value.kind == "evidence_missing"


def test_snapshot_content_alteration_detected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case, files={"main.py": "import os\n"})
    # Mutate the checkout after the record was written.
    (snapshot_root / "checkout" / "main.py").write_text("import sys\n", encoding="utf-8")
    with pytest.raises(BenchmarkArtifactError) as exc:
        verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    assert exc.value.kind == "snapshot_mismatch"


def test_snapshot_commit_mismatch_detected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    record_path = snapshot_root / "snapshot.yaml"
    record = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    record["verified_commit"] = "b" * 40
    record_path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    with pytest.raises(BenchmarkArtifactError) as exc:
        verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    assert exc.value.kind == "snapshot_mismatch"


def test_snapshot_identity_does_not_match_recorded_hash(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    record_path = snapshot_root / "snapshot.yaml"
    record = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    record["content_hash"] = "0" * 64
    record["identity"] = f"{SNAPSHOT_HASH_SCHEME}:{'1' * 64}"
    record_path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    with pytest.raises(BenchmarkArtifactError) as exc:
        verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    assert exc.value.kind == "snapshot_mismatch"


def test_evidence_identity_tamper_detected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    evidence = write_evidence(snapshot_root, case)
    info = verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    evidence.items[0].observation = "edited observation"
    (snapshot_root / "evidence.yaml").write_text(
        yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(BenchmarkArtifactError) as exc:
        load_evidence(snapshot_root, case, info)
    assert exc.value.kind == "evidence_mismatch"
    assert "identity" in exc.value.message


def test_evidence_case_mismatch_detected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    info = verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    evidence = write_evidence(snapshot_root, case)
    evidence.case_id = "C099"
    (snapshot_root / "evidence.yaml").write_text(
        yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(BenchmarkArtifactError) as exc:
        load_evidence(snapshot_root, case, info)
    assert exc.value.kind == "evidence_mismatch"


def test_evidence_must_reference_same_snapshot_content(tmp_path: Path) -> None:
    store = tmp_path / "store"
    case = make_case("C001")
    snapshot_root = write_snapshot_store(store, case)
    info = verify_snapshot(snapshot_root, case, "repoguard-evaluation-dataset", "1.0.0")
    evidence = write_evidence(snapshot_root, case)
    evidence.snapshot_content_hash = "0" * 64
    evidence.evidence_identity = content_identity(evidence)
    (snapshot_root / "evidence.yaml").write_text(
        yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(BenchmarkArtifactError) as exc:
        load_evidence(snapshot_root, case, info)
    assert exc.value.kind == "evidence_mismatch"
