"""Command-line interface for the metrics subsystem.

Commands:

- ``metrics calculate`` - primary + secondary metrics from a benchmark run
  (ground truth optional; agreement is unavailable without it).
- ``metrics compare`` - paired baseline vs RepoGuard comparison; no ground
  truth required.
- ``metrics inspect`` - print a metrics report (optionally validating it).
- ``metrics validate`` - validate a run and/or ground-truth inputs
  (fail closed; exit code 1 on any problem).

Every command is read-only. Exit code 0 means the requested artifact was
produced, 1 means fail-closed input problems (2 for usage problems).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from evaluation.benchmark.manifest import load_run_manifest
from evaluation.evidence.serialize import canonical_dump
from evaluation.metrics._version import SYSTEM_ID, __version__
from evaluation.metrics.errors import MetricsError
from evaluation.metrics.report import (
    ALL_METRIC_NAMES,
    ReportOptions,
    calculate_report,
    compare_report,
)
from evaluation.metrics.serialize import read_report, write_report
from evaluation.metrics.validate import validate_report, validate_run_dir

_DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "results" / "metrics"


def _output_path(out: str | Path | None, *, label: str, kind: str) -> Path:
    """Resolve ``--out``: a directory nests the default file name."""
    if out is None:
        return _DEFAULT_RESULTS_DIR / f"{label}-{kind}.yaml"
    path = Path(out)
    if path.is_dir() or str(out).endswith(("/", "\\")):
        return path / f"{label}-{kind}.yaml"
    return path


def _identity_label(value: Any) -> str:
    if not isinstance(value, str):
        return "run"
    return value.replace(":", "-")[-24:]


def _metric_line(name: str, value: dict[str, Any]) -> str:
    if value.get("state") == "available" and value.get("value") is not None:
        unit = f" {value['unit']}" if value.get("unit") else ""
        return f"{name}={value['value']}{unit} (n={value.get('covered')})"
    return f"{name}={value.get('state')}"


def _secondary_summary(metrics: dict[str, Any]) -> str:
    lines: list[str] = []
    for name, value in sorted(metrics.items()):
        if isinstance(value, dict) and isinstance(value.get("state"), str):
            lines.append(_metric_line(name, value))
        elif isinstance(value, dict):
            nested = ", ".join(_metric_line(key, item) for key, item in value.items())
            lines.append(f"{name}: {{ {nested} }}")
        else:
            lines.append(f"{name}: {value}")
    return "; ".join(lines)


def _print_calculate_summary(report: dict[str, Any]) -> None:
    print(f"metrics version: {report.get('metrics_version')}")
    print(f"report identity: {report.get('metrics_identity')}")
    inputs = report.get("inputs")
    if isinstance(inputs, dict):
        print(f"run identity: {inputs.get('run_identity')}")
        gt = inputs.get("ground_truth")
        print(
            "ground truth: "
            + (
                "not provided"
                if gt is None
                else f"{gt.get('case_count')} case(s), "
                f"{len(gt.get('contested_cases') or [])} contested, "
                f"aggregate {gt.get('aggregate_identity')}"
            )
        )
    primary = report.get("primary_metric")
    if isinstance(primary, dict):
        for system in ("baseline", "repoguard"):
            entry = primary.get(system)
            if not isinstance(entry, dict):
                continue
            rho = entry.get("rho")
            if rho is None:
                print(f"agreement {system}: {entry.get('state')} ({entry.get('note', '')})")
            else:
                inclusive = entry.get("rho_including_contested")
                suffix = f", including contested={inclusive:.4f}" if inclusive is not None else ""
                print(f"agreement {system}: rho={rho:.4f} (n={entry.get('n')}){suffix}")
    secondary = report.get("secondary_metrics")
    if isinstance(secondary, dict):
        for system in ("baseline", "repoguard"):
            print(f"secondary {system}: {_secondary_summary(secondary.get(system, {}))}")


def _cmd_calculate(args: argparse.Namespace) -> int:
    unknown = set(args.metric or []) - set(ALL_METRIC_NAMES)
    if unknown:
        print(
            f"error: unknown metric(s): {', '.join(sorted(unknown))}; "
            f"valid: {', '.join(ALL_METRIC_NAMES)}",
            file=sys.stderr,
        )
        return 2
    options = ReportOptions(
        contested=args.contested,
        metrics=tuple(args.metric) if args.metric else ALL_METRIC_NAMES,
        evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
        ground_truth_findings=Path(args.gt_findings) if args.gt_findings else None,
        baseline_findings=Path(args.baseline_findings) if args.baseline_findings else None,
        repoguard_findings=Path(args.repoguard_findings) if args.repoguard_findings else None,
        review_times=Path(args.review_times) if args.review_times else None,
    )
    try:
        report = calculate_report(
            Path(args.run),
            Path(args.ground_truth) if args.ground_truth else None,
            options,
        )
        path = _output_path(
            args.out, label=_identity_label(report["inputs"]["run_identity"]), kind="report"
        )
        write_report(path, report)
    except MetricsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"\nwrote metrics report to {path}")
    _print_calculate_summary(report)
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    try:
        report = compare_report(Path(args.run))
        label = _identity_label(report.get("inputs", {}).get("run_identity"))
        path = _output_path(args.out, label=label, kind="compare")
        write_report(path, report)
    except MetricsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote comparison to {path}")
    summary = report.get("summary")
    if isinstance(summary, dict):
        stats = summary.get("score_delta_statistics")
        print(
            f"paired cases: {summary.get('paired_cases')}, "
            f"both scored: {summary.get('both_scored')}, "
            f"n deltas: {stats.get('n') if isinstance(stats, dict) else None}"
        )
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.report)
    try:
        report = read_report(path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"error: could not read report {path}: {exc}", file=sys.stderr)
        return 1
    if args.validate:
        problems = validate_report(report)
        for problem in problems:
            print(f"problem: {problem}")
        if problems:
            return 1
        print(f"report {path} is valid")
    else:
        print(canonical_dump(report))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    if not args.run and not args.report:
        print("error: metrics validate requires --run and/or --report", file=sys.stderr)
        return 2
    problems: list[str] = []
    if args.run:
        problems += validate_run_dir(Path(args.run))
    if args.ground_truth:
        if not args.run:
            print("error: --ground-truth requires --run", file=sys.stderr)
            return 2
        manifest, error = load_run_manifest(Path(args.run))
        if manifest is None:
            problems += [error]
        else:
            _, gt_problems = _load_gt_for_validation(Path(args.ground_truth), manifest)
            problems += [f"ground truth: {problem}" for problem in gt_problems]
    if args.report:
        try:
            report = read_report(Path(args.report))
        except (OSError, yaml.YAMLError, ValueError) as exc:
            print(f"error: could not read report {args.report}: {exc}", file=sys.stderr)
            return 1
        problems += [f"report: {problem}" for problem in validate_report(report)]
    if not problems:
        print("all inputs valid")
        return 0
    for problem in problems:
        print(f"problem: {problem}")
    return 1


def _load_gt_for_validation(
    ground_truth_path: Path, manifest: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    from evaluation.metrics.report import _load_ground_truth_artifacts

    return _load_ground_truth_artifacts(ground_truth_path, manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metrics",
        description="Evidence-backed benchmark metrics (RepoGuard).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"metrics {__version__} ({SYSTEM_ID})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    calculate = subparsers.add_parser("calculate", help="compute metrics for a benchmark run")
    calculate.add_argument("--run", required=True, type=str, help="benchmark run directory")
    calculate.add_argument(
        "--ground-truth",
        type=str,
        default=None,
        help="ground-truth consensus file or directory (optional)",
    )
    calculate.add_argument("--out", type=str, default=None, help="output file or directory")
    calculate.add_argument(
        "--contested",
        choices=("exclude", "include"),
        default="exclude",
        help="contested cases in the primary metric (decision recorded)",
    )
    calculate.add_argument(
        "--metric",
        action="append",
        default=None,
        help="secondary metric to compute (repeatable; default: all)",
    )
    calculate.add_argument(
        "--evidence-dir",
        type=str,
        default=None,
        help="snapshot/evidence store used to verify citations",
    )
    calculate.add_argument(
        "--gt-findings",
        type=str,
        default=None,
        help="human-flagged critical findings (case_id -> [finding, ...])",
    )
    calculate.add_argument(
        "--baseline-findings", type=str, default=None, help="baseline-reported findings input"
    )
    calculate.add_argument(
        "--repoguard-findings", type=str, default=None, help="RepoGuard-reported findings input"
    )
    calculate.add_argument(
        "--review-times",
        type=str,
        default=None,
        help="per-case human review minutes (case_id -> minutes)",
    )
    calculate.set_defaults(handler=_cmd_calculate)

    comparison = subparsers.add_parser("compare", help="paired baseline vs RepoGuard comparison")
    comparison.add_argument("--run", required=True, type=str, help="benchmark run directory")
    comparison.add_argument("--out", type=str, default=None, help="output file or directory")
    comparison.set_defaults(handler=_cmd_compare)

    inspect = subparsers.add_parser("inspect", help="print a metrics report")
    inspect.add_argument("--report", required=True, type=str)
    inspect.add_argument("--validate", action="store_true", help="validate instead of printing")
    inspect.set_defaults(handler=_cmd_inspect)

    validate = subparsers.add_parser("validate", help="validate inputs fail-closed")
    validate.add_argument("--run", type=str, default=None, help="benchmark run directory")
    validate.add_argument("--ground-truth", type=str, default=None, help="ground-truth inputs")
    validate.add_argument("--report", type=str, default=None, help="a metrics report file")
    validate.set_defaults(handler=_cmd_validate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args.handler
    if not callable(handler):
        return 2
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
