"""Command-line interface for RepoGuard.

Usage (from the repository root):

    python -m evaluation.repoguard --version
    python -m evaluation.repoguard one \
        --evidence evaluation/snapshots/C001-gosim/evidence.yaml \
        --out evaluation/results/local/repoguard/C001-repoguard.yaml
    python -m evaluation.repoguard one \
        --evidence <path> --provider openai-compatible --model <model>
    python -m evaluation.repoguard dataset
    python -m evaluation.repoguard inspect --result <path> --validate

Providers reuse the baseline contract:
    mock                deterministic, network-free (default; tests and smoke runs)
    openai-compatible   generic chat-completions HTTP endpoint, configured via
                        REPOGUARD_LLM_BASE_URL, REPOGUARD_LLM_MODEL, and an API key
                        (REPOGUARD_LLM_API_KEY, or OPENROUTER_API_KEY for OpenRouter
                        endpoints, or GEMINI_API_KEY for Google endpoints); fails
                        closed when unconfigured.

Exit codes and YAML-to-stdout conventions mirror the snapshot, evidence,
scoring, and baseline CLIs. A failed run is printed/written (for the audit
record) and exits non-zero; it is never converted into a score.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from evaluation.baseline.pipeline import EvaluatorConfig
from evaluation.baseline.provider import (
    ENV_API_KEY,
    ENV_MODEL,
    ENV_PROVIDER,
    HTTP_PROVIDER_IDS,
    build_provider,
)
from evaluation.evidence.errors import EvidenceError
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.validate import artifact_from_dict
from evaluation.repoguard._version import __version__
from evaluation.repoguard.errors import RepoGuardError
from evaluation.repoguard.models import STATUS_FAILED, STATUS_SUCCEEDED
from evaluation.repoguard.paths import default_results_dir
from evaluation.repoguard.pipeline import run_case
from evaluation.repoguard.serialize import render_result, write_result
from evaluation.snapshot.paths import default_store

_EVIDENCE_FILENAME = "evidence.yaml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.repoguard",
        description=(
            "Structured, evidence-first repository assessment over a frozen "
            "evidence artifact (docs/scoring-rubric.md version 1.0)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    one = subparsers.add_parser(
        "one", help="Run one RepoGuard assessment for a single evidence artifact."
    )
    one.add_argument("--evidence", type=Path, required=True)
    one.add_argument("--out", type=Path, help="Write the result to this file instead of stdout.")
    _add_provider_args(one)

    dataset = subparsers.add_parser(
        "dataset", help="Run RepoGuard over every evidence artifact present in the store."
    )
    dataset.add_argument("--store", type=Path, default=default_store())
    dataset.add_argument("--results-dir", type=Path, default=default_results_dir())
    _add_provider_args(dataset)

    inspect = subparsers.add_parser("inspect", help="Inspect a RepoGuard result artifact.")
    inspect.add_argument("--result", type=Path, required=True)
    inspect.add_argument(
        "--validate",
        action="store_true",
        help="Exit non-zero when the artifact fails identity/status checks.",
    )
    return parser


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        help=f"Provider name (mock or openai-compatible); default from {ENV_PROVIDER} or mock.",
    )
    parser.add_argument("--model", help=f"Model id; default from {ENV_MODEL} or mock.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=None)


def _effective_model(args: argparse.Namespace) -> str:
    explicit = args.model
    if explicit:
        return str(explicit)
    provider_name = (args.provider or os.environ.get(ENV_PROVIDER) or "mock").strip().lower()
    if provider_name in HTTP_PROVIDER_IDS:
        return os.environ.get(ENV_MODEL, "").strip() or "mock"
    return "mock"


def _secrets() -> list[str]:
    api_key = os.environ.get(ENV_API_KEY, "")
    return [api_key] if api_key else []


def _load_evidence(path: Path) -> EvidenceArtifact:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RepoGuardError(f"unreadable evidence artifact: {exc}") from exc
    if not isinstance(raw, dict):
        raise RepoGuardError("evidence artifact is not a mapping")
    try:
        return artifact_from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise RepoGuardError(f"invalid evidence artifact: {exc}") from exc


def _discover_evidence(store: Path) -> list[Path]:
    found: list[Path] = []
    if not store.is_dir():
        return found
    for child in sorted(store.iterdir()):
        evidence = child / _EVIDENCE_FILENAME
        if child.is_dir() and evidence.is_file():
            found.append(evidence)
    return found


def _read_identity(path: Path) -> str:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    identity = raw.get("result_identity") if isinstance(raw, dict) else None
    return identity if isinstance(identity, str) else ""


def _run_one(evidence: EvidenceArtifact, args: argparse.Namespace) -> int:
    provider = build_provider(args.provider, model=args.model)
    config = EvaluatorConfig(
        provider_name=provider.name,
        model=_effective_model(args),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    try:
        result = run_case(evidence, provider, config=config)
    except RepoGuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    secrets = _secrets()
    if args.out:
        write_result(args.out, result, secrets)
        print(f"[ok] {result.case_id} -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(render_result(result, secrets))
    return 0 if result.status == STATUS_SUCCEEDED else 1


def _cmd_one(args: argparse.Namespace) -> int:
    return _run_one(_load_evidence(args.evidence), args)


def _cmd_dataset(args: argparse.Namespace) -> int:
    provider = build_provider(args.provider, model=args.model)
    config = EvaluatorConfig(
        provider_name=provider.name,
        model=_effective_model(args),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    results: list[dict[str, object]] = []
    failures: list[str] = []
    secrets = _secrets()
    for evidence_path in _discover_evidence(args.store):
        try:
            evidence = _load_evidence(evidence_path)
            result = run_case(evidence, provider, config=config)
        except (RepoGuardError, EvidenceError) as exc:
            failures.append(f"{evidence_path.parent.name}: {exc}")
            print(f"[skip] {evidence_path.parent.name}: {exc}", file=sys.stderr)
            continue
        out = args.results_dir / f"{evidence.case_id}-repoguard-v{result.repoguard_version}.yaml"
        write_result(out, result, secrets)
        cases = evidence.case_id
        if result.status == STATUS_FAILED:
            failures.append(f"{cases}: {result.error.kind if result.error else 'failed'}")
        results.append(
            {
                "case": cases,
                "result": str(out),
                "status": result.status,
                "score": result.scoring.get("score") if result.scoring else None,
                "evidence_identity": evidence.evidence_identity,
                "result_identity": _read_identity(out),
            }
        )
        print(f"[ok] {cases} -> {out}", file=sys.stderr)
    yaml.safe_dump({"results": results}, sys.stdout, sort_keys=False)
    return 1 if failures else 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        raw = yaml.safe_load(args.result.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"error: unreadable result: {exc}", file=sys.stderr)
        return 1
    from evaluation.repoguard.serialize import recompute_identity

    valid = False
    identity_matches = False
    if isinstance(raw, dict):
        recorded = raw.get("result_identity")
        recomputed = recompute_identity(raw)
        identity_matches = isinstance(recorded, str) and recorded == recomputed
        valid = identity_matches and raw.get("status") in (STATUS_SUCCEEDED, STATUS_FAILED)
    out: dict[str, object] = raw if isinstance(raw, dict) else {"error": "not a mapping"}
    inspection = {
        "valid": valid,
        "identity_matches": identity_matches,
        "recomputed": recompute_identity(raw),
    }
    out = dict(out)
    out["inspection"] = inspection
    yaml.safe_dump(out, sys.stdout, sort_keys=False)
    if args.validate and not valid:
        return 1
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
    except (RepoGuardError, EvidenceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command {args.command}")
