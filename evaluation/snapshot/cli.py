"""Command-line interface for the snapshot subsystem.

Usage (from the repository root):

    python -m evaluation.snapshot one --manifest evaluation/datasets/dataset-v1.0.0.yaml --case C001
    python -m evaluation.snapshot dataset --manifest evaluation/datasets/dataset-v1.0.0.yaml
    python -m evaluation.snapshot inspect --snapshot evaluation/snapshots/C001-gosim --verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from evaluation.snapshot import git
from evaluation.snapshot._version import __version__
from evaluation.snapshot.acquire import acquire_case, load_snapshot_result
from evaluation.snapshot.errors import SnapshotError
from evaluation.snapshot.hashing import hash_snapshot_tree
from evaluation.snapshot.manifest import case_by_id, load_manifest
from evaluation.snapshot.models import ManifestCase, SnapshotResult
from evaluation.snapshot.paths import (
    CHECKOUT_DIR,
    INVENTORY_FILE,
    SNAPSHOT_RECORD_FILE,
    default_store,
)

_DATASET_DEFAULT = (
    Path(__file__).resolve().parents[2] / "evaluation" / "datasets" / "dataset-v1.0.0.yaml"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.snapshot",
        description="Deterministic, evidence-only snapshot acquisition for the frozen dataset.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    one = subparsers.add_parser("one", help="Snapshot a single case from the dataset.")
    one.add_argument("--manifest", type=Path, default=_DATASET_DEFAULT)
    one.add_argument("--case", required=True, help="Candidate ID, e.g. C001")
    one.add_argument("--store", type=Path, default=default_store())

    dataset = subparsers.add_parser(
        "dataset", help="Snapshot every included case in the frozen dataset."
    )
    dataset.add_argument("--manifest", type=Path, default=_DATASET_DEFAULT)
    dataset.add_argument("--store", type=Path, default=default_store())

    inspect = subparsers.add_parser(
        "inspect", help="Print an existing snapshot record and inventory."
    )
    inspect.add_argument("--snapshot", type=Path, required=True)
    inspect.add_argument(
        "--verify",
        action="store_true",
        help="Re-hash the checkout and re-verify HEAD against the recorded commit.",
    )
    return parser


def _result_dict(result: SnapshotResult, *, basename: bool = False) -> dict[str, object]:
    location = result.path.name if basename else str(result.path)
    return {
        "snapshot": location,
        "idempotent": result.idempotent,
        "record": result.record.to_dict(),
        "inventory": result.inventory.to_dict(),
    }


def _cmd_one(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    case = case_by_id(manifest, args.case)
    result = acquire_case(case, manifest, args.store)
    yaml.safe_dump(_result_dict(result), sys.stdout, sort_keys=False)
    return 0


def _cmd_dataset(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for case in manifest.cases:
        if case.dataset_decision != "include":
            continue
        try:
            result = acquire_case(case, manifest, args.store)
        except SnapshotError as exc:
            failures.append(f"{case.candidate_id}: {exc}")
            print(f"[skip] {case.candidate_id}: {exc}", file=sys.stderr)
            continue
        if case.dataset_status == "pending_license_confirmation":
            print(
                f"[note] {case.candidate_id} license pending confirmation; "
                "snapshot acquired for evidence only",
                file=sys.stderr,
            )
        results.append(_result_dict(result, basename=True))
        print(f"[ok] {case.candidate_id} -> {result.path}", file=sys.stderr)
    yaml.safe_dump(
        {"dataset_version": manifest.version, "snapshots": results}, sys.stdout, sort_keys=False
    )
    return 1 if failures else 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    snapshot_path = args.snapshot
    if (
        not (snapshot_path / SNAPSHOT_RECORD_FILE).is_file()
        or not (snapshot_path / INVENTORY_FILE).is_file()
    ):
        print(f"error: not a snapshot directory: {snapshot_path}", file=sys.stderr)
        return 1
    try:
        record_raw = yaml.safe_load(
            (snapshot_path / SNAPSHOT_RECORD_FILE).read_text(encoding="utf-8")
        )
        if not isinstance(record_raw, dict):
            raise SnapshotError(f"invalid snapshot record: {snapshot_path}")
        case = ManifestCase(
            candidate_id=str(record_raw["candidate_id"]),
            name=str(record_raw["name"]),
            url=str(record_raw["repository_url"]),
            pinned_commit=str(record_raw["requested_commit"]),
            ecosystem="",
            license="",
            dataset_decision="include",
            dataset_status="",
        )
        result = load_snapshot_result(snapshot_path, case)
    except SnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out: dict[str, object] = _result_dict(result, basename=False)
    if args.verify:
        checkout = snapshot_path / CHECKOUT_DIR
        verified = False
        details = "not run"
        try:
            verified_sha = git.verified_head(checkout, result.record.requested_commit)
            current_hash = hash_snapshot_tree(checkout)
            hash_ok = current_hash == result.record.content_hash
            verified = hash_ok and verified_sha == result.record.verified_commit
            details = (
                f"HEAD={verified_sha} verified_commit={result.record.verified_commit} "
                f"hash={'match' if hash_ok else f'MISMATCH {current_hash}'}"
            )
        except SnapshotError as exc:
            details = f"error: {exc}"
        out["verification"] = {"verified": verified, "details": details}
    yaml.safe_dump(out, sys.stdout, sort_keys=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "one":
            return _cmd_one(args)
        if args.command == "dataset":
            return _cmd_dataset(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
    except SnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command {args.command}")
