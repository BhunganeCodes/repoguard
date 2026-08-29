"""Command-line interface for the ground-truth subsystem.

Usage (from the repository root):

    python -m evaluation.ground_truth --version
    python -m evaluation.ground_truth validate \\
        --review evaluation/ground_truth/local/reviews/C007-R01-review.yaml \\
        --evidence evaluation/snapshots/C007-eyeshield/evidence.yaml
    python -m evaluation.ground_truth compare \\
        --review <R01 review> --review <R02 review> --evidence <path>
    python -m evaluation.ground_truth adjudicate \\
        --case C007 --review <R01> --review <R02> --decisions <file> \\
        --evidence <path> [--out-record <path>] [--out-consensus <path>]
    python -m evaluation.ground_truth inspect --artifact <path> \\
        [--evidence <path>] [--review <R01> --review <R02>] [--validate]

Ground truth is produced by humans only. The CLI never reads baseline or
RepoGuard results, never exposes tiers, ranks, or system scores in reviewer
input, and never writes into ``evaluation/results/``. Exit codes and YAML
conventions mirror the other assessment CLIs; a failed operation (including
an invalid reviewer assessment) exits non-zero and is never coerced into a
consensus artifact.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.validate import artifact_from_dict
from evaluation.ground_truth._version import __version__
from evaluation.ground_truth.compare import compare
from evaluation.ground_truth.consensus import (
    build_adjudication,
    build_consensus,
    validate_adjudication,
)
from evaluation.ground_truth.errors import GroundTruthError
from evaluation.ground_truth.paths import adjudication_file, consensus_file
from evaluation.ground_truth.serialize import (
    adjudication_identity,
    ground_truth_identity,
    review_identity,
)
from evaluation.ground_truth.validate import (
    validate_ground_truth,
    validate_review,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.ground_truth",
        description=(
            "Human-authored ground truth for frozen evaluation cases: "
            "independent reviewer assessments, disagreement detection, "
            "adjudication, and final consensus artifacts (docs/evaluation.md "
            "Section 6, docs/ground-truth.md)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a reviewer assessment.")
    validate.add_argument("--review", type=Path, required=True)
    validate.add_argument("--evidence", type=Path, required=True)

    compare_parser = subparsers.add_parser(
        "compare", help="Detect disagreement between independent reviews."
    )
    compare_parser.add_argument("--review", type=Path, action="append", required=True)
    compare_parser.add_argument("--evidence", type=Path, required=True)
    compare_parser.add_argument("--out", type=Path, help="Write the report to this file.")

    adjudicate = subparsers.add_parser(
        "adjudicate",
        help="Record an adjudicator's decisions and emit the final consensus artifact.",
    )
    adjudicate.add_argument("--case", required=True)
    adjudicate.add_argument("--review", type=Path, action="append", required=True)
    adjudicate.add_argument("--decisions", type=Path, required=True)
    adjudicate.add_argument("--evidence", type=Path, required=True)
    adjudicate.add_argument("--out-record", type=Path, help="Adjudication record path.")
    adjudicate.add_argument("--out-consensus", type=Path, help="Final consensus artifact path.")

    inspect = subparsers.add_parser("inspect", help="Inspect a ground-truth artifact.")
    inspect.add_argument("--artifact", type=Path, required=True)
    inspect.add_argument("--evidence", type=Path)
    inspect.add_argument("--review", type=Path, action="append")
    inspect.add_argument(
        "--validate",
        action="store_true",
        help="Exit non-zero when the artifact fails validation.",
    )
    return parser


def _load_evidence(path: Path) -> EvidenceArtifact:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GroundTruthError(f"unreadable evidence artifact: {exc}") from exc
    if not isinstance(raw, dict):
        raise GroundTruthError("evidence artifact is not a mapping")
    try:
        return artifact_from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise GroundTruthError(f"invalid evidence artifact: {exc}") from exc


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GroundTruthError(f"unreadable YAML file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise GroundTruthError(f"YAML file {path} is not a mapping")
    return raw


def _load_reviews(paths: list[Path]) -> list[dict[str, Any]]:
    return [load_yaml(path) for path in paths]


def _emit(data: dict[str, Any], out: Path | None) -> None:
    rendered = yaml.safe_dump(data, sort_keys=False, width=100)
    if out is None:
        sys.stdout.write(rendered)
    else:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"[ok] wrote {out}", file=sys.stderr)
        except OSError as exc:
            raise GroundTruthError(f"cannot write {out}: {exc}") from exc


def _cmd_validate(args: argparse.Namespace) -> int:
    evidence = _load_evidence(args.evidence)
    review = load_yaml(args.review)
    problems = validate_review(review, evidence)
    report: dict[str, Any] = {
        "review": str(args.review),
        "case_id": review.get("case_id"),
        "reviewer_id": review.get("reviewer_id"),
        "valid": not problems,
        "problems": problems,
    }
    _emit(report, None)
    return 0 if not problems else 1


def _cmd_compare(args: argparse.Namespace) -> int:
    evidence = _load_evidence(args.evidence)
    reviews = _load_reviews(args.review)
    report = compare(reviews, evidence)
    _emit(report, args.out)
    return 0


def _cmd_adjudicate(args: argparse.Namespace) -> int:
    evidence = _load_evidence(args.evidence)
    reviews = _load_reviews(args.review)
    decisions = load_yaml(args.decisions)
    record = build_adjudication(reviews=reviews, evidence=evidence, decisions_data=decisions)
    artifact = build_consensus(reviews=reviews, evidence=evidence, adjudication=record)

    record_path = args.out_record or adjudication_file(args.case)
    consensus_path = args.out_consensus or consensus_file(args.case)
    _emit(record, record_path)
    _emit(artifact, consensus_path)
    outcome: dict[str, Any] = {
        "case_id": args.case,
        "status": artifact["status"],
        "adjudication_record": str(record_path),
        "adjudication_identity": record["adjudication_identity"],
        "consensus_artifact": str(consensus_path),
        "ground_truth_identity": artifact["ground_truth_identity"],
    }
    _emit(outcome, None)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    artifact = load_yaml(args.artifact)
    problems: list[str] = []
    identity_matches: bool | None = None
    kind = _detect_kind(artifact)

    if kind == "review":
        if args.evidence is None:
            raise GroundTruthError("inspecting a reviewer assessment requires --evidence")
        evidence = _load_evidence(args.evidence)
        identity_matches = _verify_identity(artifact, "review_identity", review_identity)
        problems = validate_review(artifact, evidence)
    elif kind == "adjudication":
        if args.evidence is None or not args.review:
            raise GroundTruthError(
                "inspecting an adjudication record requires --evidence and the --review files"
            )
        evidence = _load_evidence(args.evidence)
        reviews = _load_reviews(args.review)
        identity_matches = _verify_identity(
            artifact, "adjudication_identity", adjudication_identity
        )
        problems = validate_adjudication(artifact, reviews, evidence)
    elif kind == "consensus":
        if args.evidence is None:
            raise GroundTruthError("inspecting a consensus artifact requires --evidence")
        evidence = _load_evidence(args.evidence)
        identity_matches = _verify_identity(
            artifact, "ground_truth_identity", ground_truth_identity
        )
        problems = validate_ground_truth(artifact, evidence)
    else:
        raise GroundTruthError(
            f"cannot determine artifact kind for {args.artifact}: expected a reviewer "
            "assessment, adjudication record, or final consensus artifact"
        )

    report: dict[str, Any] = {
        "artifact": str(args.artifact),
        "kind": kind,
        "case_id": artifact.get("case_id"),
        "identity_matches": identity_matches,
        "valid": not problems,
        "problems": problems,
    }
    _emit(report, None)
    return 0 if (not (args.validate and (problems or identity_matches is False))) else 1


def _detect_kind(data: dict[str, Any]) -> str:
    if "ground_truth_identity" in data:
        return "consensus"
    if "adjudication_identity" in data:
        return "adjudication"
    if "reviewer_id" in data and "criteria" in data:
        return "review"
    return "unknown"


def _verify_identity(
    data: dict[str, Any], key: str, identity_fn: Callable[[dict[str, Any]], str]
) -> bool | None:
    recorded = data.get(key)
    if not isinstance(recorded, str) or not recorded:
        return None
    return recorded == identity_fn(data)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "compare":
            return _cmd_compare(args)
        if args.command == "adjudicate":
            return _cmd_adjudicate(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
    except GroundTruthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command {args.command}")


__all__ = ["main"]
