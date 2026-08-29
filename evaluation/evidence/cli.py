"""Command-line interface for the evidence subsystem.

Usage (from the repository root):

    python -m evaluation.evidence one --snapshot evaluation/snapshots/C001-gosim
    python -m evaluation.evidence one --manifest evaluation/datasets/dataset-v1.0.0.yaml --case C001
    python -m evaluation.evidence dataset
    python -m evaluation.evidence inspect --artifact <snapshot>/evidence.yaml --validate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

import yaml

from evaluation.evidence._version import __version__
from evaluation.evidence.errors import EvidenceError
from evaluation.evidence.extract import extract_snapshot_directory
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.paths import evidence_file
from evaluation.evidence.serialize import recompute_identity, write_artifact
from evaluation.evidence.validate import artifact_from_dict, validate_artifact, validate_raw
from evaluation.snapshot.errors import SnapshotError
from evaluation.snapshot.manifest import case_by_id, load_manifest
from evaluation.snapshot.paths import SNAPSHOT_RECORD_FILE, default_store, snapshot_dir

_DATASET_DEFAULT = (
    Path(__file__).resolve().parents[2] / "evaluation" / "datasets" / "dataset-v1.0.0.yaml"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.evidence",
        description="Deterministic, evidence-only extraction for frozen repository snapshots.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    one = subparsers.add_parser("one", help="Extract evidence for a single snapshot.")
    one.add_argument(
        "--snapshot",
        type=Path,
        help="Snapshot directory to extract from (alternative to --manifest/--case).",
    )
    one.add_argument("--manifest", type=Path, default=_DATASET_DEFAULT)
    one.add_argument("--case", help="Candidate ID, e.g. C001")
    one.add_argument("--store", type=Path, default=default_store())

    dataset = subparsers.add_parser(
        "dataset", help="Extract evidence for every snapshot present in the store."
    )
    dataset.add_argument("--store", type=Path, default=default_store())

    inspect = subparsers.add_parser("inspect", help="Inspect an evidence artifact and validate it.")
    inspect.add_argument("--artifact", type=Path, required=True)
    inspect.add_argument(
        "--validate",
        action="store_true",
        help="Exit non-zero when the artifact fails validation or its identity changed.",
    )
    return parser


def _resolve_snapshot_dir(args: argparse.Namespace) -> Path:
    snapshot = args.snapshot
    if snapshot is not None:
        return cast(Path, snapshot)
    case_id = args.case
    if not case_id:
        raise EvidenceError("one requires either --snapshot or --case")
    manifest = load_manifest(args.manifest)
    case = case_by_id(manifest, case_id)
    return snapshot_dir(args.store, case)


def _cmd_one(args: argparse.Namespace) -> int:
    snapshot = _resolve_snapshot_dir(args)
    if not (snapshot / SNAPSHOT_RECORD_FILE).is_file():
        print(f"error: not a snapshot directory: {snapshot}", file=sys.stderr)
        return 1
    artifact = extract_snapshot_directory(snapshot)
    problems = validate_artifact(artifact)
    if problems:
        for problem in problems:
            print(f"error: validation: {problem}", file=sys.stderr)
        return 1
    target = evidence_file(snapshot)
    changed, _rendered = write_artifact(target, artifact)
    summary = artifact.to_dict()
    summary.pop("items", None)
    summary["write"] = {"path": str(target), "changed": changed}
    summary["status_counts"] = _status_counts(artifact)
    yaml.safe_dump(summary, sys.stdout, sort_keys=False)
    return 0


def _cmd_dataset(args: argparse.Namespace) -> int:
    store = args.store
    snapshot_dirs: list[Path] = []
    for child in sorted(store.iterdir()) if store.is_dir() else []:
        if child.is_dir() and (child / SNAPSHOT_RECORD_FILE).is_file():
            snapshot_dirs.append(child)
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for snapshot in snapshot_dirs:
        try:
            artifact = extract_snapshot_directory(snapshot)
            problems = validate_artifact(artifact)
            if problems:
                for problem in problems:
                    print(f"error: {snapshot.name} validation: {problem}", file=sys.stderr)
                raise EvidenceError("artifact failed validation")
            target = evidence_file(snapshot)
            updated, _rendered = write_artifact(target, artifact)
            results.append(
                {
                    "case": artifact.case_id,
                    "artifact": str(target),
                    "changed": updated,
                    "evidence_identity": artifact.evidence_identity,
                    "items": len(artifact.items),
                }
            )
            print(f"[ok] {artifact.case_id} -> {target}", file=sys.stderr)
        except EvidenceError as exc:
            failures.append(f"{snapshot.name}: {exc}")
            print(f"[skip] {snapshot.name}: {exc}", file=sys.stderr)
    yaml.safe_dump({"extracted": results}, sys.stdout, sort_keys=False)
    return 1 if failures else 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    artifact_path = args.artifact
    try:
        raw = yaml.safe_load(artifact_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"error: unreadable artifact: {exc}", file=sys.stderr)
        return 1
    if not isinstance(raw, dict):
        print("error: invalid artifact structure", file=sys.stderr)
        return 1
    problems = validate_raw(raw)
    current = "not recomputed"
    identity_ok = False
    try:
        artifact = artifact_from_dict(raw)
        current = recompute_identity(artifact)
        identity_ok = current == artifact.evidence_identity
    except (KeyError, TypeError, ValueError):
        identity_ok = False
    out = dict(raw)
    out["inspection"] = {
        "valid": not problems,
        "problems": problems,
        "identity_recomputed": current,
        "identity_matches": identity_ok,
    }
    yaml.safe_dump(out, sys.stdout, sort_keys=False)
    if args.validate and (problems or not identity_ok):
        return 1
    return 0


def _status_counts(artifact: EvidenceArtifact) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in artifact.items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return dict(sorted(counts.items()))


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
    except (EvidenceError, SnapshotError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command {args.command}")
