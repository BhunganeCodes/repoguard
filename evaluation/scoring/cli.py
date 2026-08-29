"""Command-line interface for the deterministic scoring subsystem.

Usage (from the repository root):

    python -m evaluation.scoring --version
    python -m evaluation.scoring validate \
        --assessment assessment.yaml --evidence evaluation/snapshots/C001-gosim/evidence.yaml
    python -m evaluation.scoring score \
        --assessment assessment.yaml --evidence evaluation/snapshots/C001-gosim/evidence.yaml
    python -m evaluation.scoring inspect \
        --assessment assessment.yaml \
        --evidence evaluation/snapshots/C001-gosim/evidence.yaml --validate

Exit codes, YAML-to-stdout conventions, and error-to-stderr behavior mirror
the snapshot and evidence subsystems. No network access is required.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from evaluation.evidence.errors import EvidenceError
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import recompute_identity
from evaluation.evidence.validate import artifact_from_dict
from evaluation.scoring._version import __version__
from evaluation.scoring.errors import ScoringError
from evaluation.scoring.serialize import compose_assessment, compose_payload, require_complete
from evaluation.scoring.validate import validate_assessment


def _load_evidence(path: Path) -> EvidenceArtifact:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScoringError(f"unreadable evidence artifact: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScoringError("evidence artifact is not a mapping")
    try:
        return artifact_from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ScoringError(f"invalid evidence artifact: {exc}") from exc


def _load_assessment(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScoringError(f"unreadable assessment: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScoringError("assessment is not a mapping")
    return raw


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.scoring",
        description=(
            "Deterministic rubric scoring over evidence artifacts "
            "(docs/scoring-rubric.md version 1.0)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate", help="Validate an assessment against the rubric and its evidence."
    )
    validate.add_argument("--assessment", type=Path, required=True)
    validate.add_argument("--evidence", type=Path, required=True)

    score = subparsers.add_parser(
        "score", help="Score a complete assessment and emit the structured artifact."
    )
    score.add_argument("--assessment", type=Path, required=True)
    score.add_argument("--evidence", type=Path, required=True)
    score.add_argument(
        "--out", type=Path, help="Write the artifact to this file instead of stdout."
    )

    inspect = subparsers.add_parser(
        "inspect", help="Print an assessment with validation and scoring-status details."
    )
    inspect.add_argument("--assessment", type=Path, required=True)
    inspect.add_argument("--evidence", type=Path, required=True)
    inspect.add_argument(
        "--validate",
        action="store_true",
        help="Exit non-zero when the assessment fails validation.",
    )
    return parser


def _computed_summary(data: dict[str, Any], evidence: EvidenceArtifact) -> dict[str, Any] | None:
    try:
        payload, _identity = compose_payload(data, evidence)
    except ScoringError:
        return None
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else None


def _inspection(data: dict[str, Any], evidence: EvidenceArtifact) -> dict[str, Any]:
    problems = validate_assessment(data, evidence)
    summary = _computed_summary(data, evidence) if not problems else None
    complete = bool(summary and summary["complete"]) if summary else None
    inspection: dict[str, Any] = {
        "valid": not problems,
        "problems": problems,
        "evidence_identity_matches": _identity_matches(data, evidence),
    }
    if summary is not None:
        inspection["complete"] = complete
        inspection["pending"] = list(summary.get("pending") or [])
        inspection["scoreable"] = complete and (summary.get("possible") or 0) > 0
        if complete:
            inspection["computed"] = {
                "earned": summary.get("earned"),
                "possible": summary.get("possible"),
                "score": summary.get("score"),
            }
    else:
        inspection["complete"] = None
        inspection["scoreable"] = None
    return inspection


def _identity_matches(data: dict[str, Any], evidence: EvidenceArtifact) -> bool:
    recorded = data.get("evidence_identity")
    if not isinstance(recorded, str):
        return False
    try:
        return recorded == recompute_identity(evidence)
    except (KeyError, TypeError, ValueError):
        return False


def _cmd_validate(args: argparse.Namespace) -> int:
    data = _load_assessment(args.assessment)
    evidence = _load_evidence(args.evidence)
    problems = validate_assessment(data, evidence)
    out: dict[str, Any] = {
        "schema_version": data.get("schema_version"),
        "case_id": data.get("case_id"),
        "rubric_version": data.get("rubric_version"),
        "evidence_identity": data.get("evidence_identity"),
        "evidence_identity_matches": _identity_matches(data, evidence),
        "valid": not problems,
        "problems": problems,
    }
    if not problems:
        inspection = _inspection(data, evidence)
        out["complete"] = inspection.get("complete")
        out["scoreable"] = inspection.get("scoreable")
        if inspection.get("computed") is not None:
            out["computed"] = inspection["computed"]
        if inspection.get("pending"):
            out["pending"] = inspection["pending"]
    yaml.safe_dump(out, sys.stdout, sort_keys=False)
    return 1 if problems else 0


def _cmd_score(args: argparse.Namespace) -> int:
    data = _load_assessment(args.assessment)
    evidence = _load_evidence(args.evidence)
    problems = validate_assessment(data, evidence)
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    artifact = compose_assessment(data, evidence)
    try:
        require_complete(artifact)
    except ScoringError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    rendered = yaml.safe_dump(artifact, sort_keys=False)
    if args.out:
        args.out.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"[ok] {artifact['case_id']} -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    data = _load_assessment(args.assessment)
    evidence = _load_evidence(args.evidence)
    inspection = _inspection(data, evidence)
    out = dict(data)
    out["inspection"] = inspection
    yaml.safe_dump(out, sys.stdout, sort_keys=False)
    if args.validate and not inspection["valid"]:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "score":
            return _cmd_score(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
    except (ScoringError, EvidenceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command {args.command}")
