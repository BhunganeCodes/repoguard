"""Command-line interface for the benchmark runner.

Usage (from the repository root):

    python -m evaluation.benchmark --version
    python -m evaluation.benchmark run
    python -m evaluation.benchmark run --case C001
    python -m evaluation.benchmark run --evaluator baseline
    python -m evaluation.benchmark run --provider openai-compatible --model <model>
    python -m evaluation.benchmark inspect --run evaluation/results/benchmark/<run-id>
    python -m evaluation.benchmark validate --run evaluation/results/benchmark/<run-id>

Protocol:

* ``run`` executes the frozen dataset through the selected evaluators. The
  default provider is the deterministic mock (network-free); a real LLM is
  used only when explicitly requested with ``--provider``. A key in the
  environment never triggers a network call.
* ``inspect`` prints a run manifest and (optionally) one case record.
* ``validate`` re-verifies an entire run directory (identities, evidence and
  rubric bindings, per-case scores, secret redaction).

Exit codes and YAML-to-stdout conventions mirror the snapshot, evidence,
scoring, baseline, and RepoGuard CLIs. A run whose summary shows any failed
case exits non-zero; failures are recorded, never converted into scores.
"""

from __future__ import annotations

import argparse
import secrets as stdlib_secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evaluation.benchmark._version import __version__
from evaluation.benchmark.cases import (
    dataset_identity,
    load_dataset,
    select_cases,
    unconfirmed_status,
)
from evaluation.benchmark.errors import BenchmarkError
from evaluation.benchmark.manifest import load_run_manifest, validate_run
from evaluation.benchmark.models import STATUS_FAILED
from evaluation.benchmark.paths import case_record_file, default_results_dir, run_dir
from evaluation.benchmark.runner import (
    ALL_EVALUATORS,
    RunInput,
    build_run_input,
    default_secrets,
    execute_run,
    resolve_provider,
)
from evaluation.snapshot.paths import default_store


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.benchmark",
        description=(
            "Deterministic benchmark runner: executes the frozen dataset "
            "through the baseline and RepoGuard evaluators and isolates the "
            "results (docs/benchmark-runner.md)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run", help="Run the frozen dataset through the configured evaluators."
    )
    run.set_defaults(handler=_cmd_run)
    run.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "evaluation"
        / "datasets"
        / "dataset-v1.0.0.yaml",
    )
    run.add_argument("--store", type=Path, default=default_store())
    run.add_argument(
        "--case",
        action="append",
        default=None,
        metavar="CASE_ID",
        help="Run only this case (repeatable). Default: every confirmed dataset case.",
    )
    run.add_argument(
        "--evaluator",
        choices=("all", "baseline", "repoguard"),
        default="all",
        help="Which systems to run (default: all).",
    )
    run.add_argument(
        "--out",
        type=Path,
        default=default_results_dir(),
        help="Output area; the run is written under <out>/<run-id>/.",
    )
    run.add_argument("--run-id", default=None, help="Stable run id (default: auto-generated).")
    run.add_argument(
        "--provider", default="mock", help="Provider name; mock never uses the network."
    )
    run.add_argument("--model", default=None, help="Model id for the provider.")
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-tokens", type=int, default=None)
    run.add_argument("--timeout-s", type=float, default=60.0)

    inspect = subparsers.add_parser(
        "inspect", help="Print a run manifest and an optional case record."
    )
    inspect.set_defaults(handler=_cmd_inspect)
    inspect.add_argument("--run", type=Path, required=True, help="A run directory.")
    inspect.add_argument("--case", default=None, help="Also print this case's record.")

    validate = subparsers.add_parser(
        "validate",
        help="Re-verify an entire run directory (exits non-zero on problems).",
    )
    validate.set_defaults(handler=_cmd_validate)
    validate.add_argument("--run", type=Path, required=True, help="A run directory.")
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    dataset_ident = dataset_identity(args.dataset)
    cases = select_cases(dataset, args.case)
    for case in cases:
        if unconfirmed_status(case):
            print(
                (
                    f"[warn] {case.candidate_id}: {case.dataset_status}; "
                    "running because explicitly selected"
                ),
                file=sys.stderr,
            )
    if not cases:
        print("error: no benchmark cases selected", file=sys.stderr)
        return 1

    provider, config = resolve_provider(
        name=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout_s,
    )
    evaluators = ALL_EVALUATORS if args.evaluator == "all" else frozenset({args.evaluator})
    run_id = args.run_id or _new_run_id()
    run: RunInput = build_run_input(
        dataset=dataset,
        dataset_identity=dataset_ident,
        cases=cases,
        store=args.store,
        provider=provider,
        config=config,
        evaluators=evaluators,
        results_dir=args.out,
        run_id=run_id,
        secrets=default_secrets(),
    )

    executed = execute_run(run)
    manifest, _ = load_run_manifest(run_dir(args.out, run_id))
    run_identity = str(manifest.get("run_identity")) if manifest else ""

    rows: list[dict[str, Any]] = []
    for outcome in executed:
        rows.append(
            {
                "case": outcome.case_id,
                "status": outcome.status,
                "baseline_score": outcome.baseline.score if outcome.baseline else None,
                "repoguard_score": outcome.repoguard.score if outcome.repoguard else None,
                "delta": outcome.delta,
                "error": outcome.error.to_dict() if outcome.error else None,
            }
        )
        if outcome.status == STATUS_FAILED:
            print(
                f"[fail] {outcome.case_id}: {outcome.error.kind if outcome.error else 'failed'}",
                file=sys.stderr,
            )
        else:
            print(f"[ok] {outcome.case_id}", file=sys.stderr)

    yaml.safe_dump(
        {
            "run_id": run_id,
            "run_identity": run_identity,
            "results_dir": str(run_dir(args.out, run_id)),
            "cases": rows,
        },
        sys.stdout,
        sort_keys=False,
    )
    return 0 if not rows or all(row["status"] != STATUS_FAILED for row in rows) else 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    manifest, error = load_run_manifest(args.run)
    if manifest is None:
        print(f"error: {error}", file=sys.stderr)
        return 1
    out: dict[str, Any] = {"run_manifest": manifest}
    if args.case:
        record_path = case_record_file(args.run.parent, args.run.name, args.case)
        if not record_path.is_file():
            print(f"error: case record missing: {record_path}", file=sys.stderr)
            return 1
        raw: object = yaml.safe_load(record_path.read_text(encoding="utf-8"))
        fallback = {"error": "case record is not a mapping"}
        out["case_record"] = raw if isinstance(raw, dict) else fallback
    yaml.safe_dump(out, sys.stdout, sort_keys=False)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    problems = validate_run(args.run)
    manifest, _ = load_run_manifest(args.run)
    run_id = str(manifest.get("run_id")) if manifest else args.run.name
    yaml.safe_dump(
        {"run_id": run_id, "valid": not problems, "problems": problems},
        sys.stdout,
        sort_keys=False,
    )
    return 0 if not problems else 1


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")
    return f"{stamp}-{stdlib_secrets.token_hex(2)}"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
