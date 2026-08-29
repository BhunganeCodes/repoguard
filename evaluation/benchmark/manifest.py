"""Run manifests for the benchmark runner.

A run manifest makes a benchmark run reproducible (docs/evaluation.md
Section 12 and docs/benchmark-runner.md): it records the benchmark and
dataset versions, dataset/content identities, rubric version, per-case
evidence identities, evaluator and prompt versions, provider configuration,
result locations, runtime metadata, and the run identity.

The run identity is a SHA-256 over the canonical YAML of every semantic
field, excluding only ``created_at``, ``environment``, and ``run_id`` (labels
that vary between identical runs). Identical inputs therefore always produce
the identical run identity, and no timestamp ever enters a content identity.
Model configuration is sanitized (credential-looking keys are dropped)
before it can appear in a manifest, and rendered manifests are additionally
secret-masked as defense in depth.
"""

from __future__ import annotations

import hashlib
import platform
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from evaluation.baseline._version import __version__ as BASELINE_VERSION
from evaluation.baseline.prompt import PROMPT_VERSION as BASELINE_PROMPT_VERSION
from evaluation.baseline.serialize import mask_secrets, sanitize_config
from evaluation.baseline.serialize import recompute_identity as baseline_identity
from evaluation.benchmark._version import (
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_SCHEME,
    SYSTEM_ID,
    __version__,
)
from evaluation.benchmark.models import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    EvaluatorOutcome,
    ExecutedCase,
)
from evaluation.benchmark.paths import RUN_MANIFEST_FILE, run_dir
from evaluation.evidence.serialize import canonical_dump
from evaluation.repoguard._version import __version__ as REPOGUARD_VERSION
from evaluation.repoguard.prompts import PROMPT_VERSION as REPOGUARD_PROMPT_VERSION
from evaluation.repoguard.serialize import recompute_identity as repoguard_identity
from evaluation.scoring.rubric import RUBRIC_VERSION

if TYPE_CHECKING:
    from evaluation.benchmark.runner import RunInput

# Fields that vary between identical runs but never change the identity.
_SEMANTIC_EXCLUDED = frozenset({"run_identity", "run_id", "created_at", "environment"})

# Keys never recorded, even when a provider exposes them (mirrors the
# baseline/RepoGuard result redaction).
_SECRET_KEY_HINTS = ("key", "token", "secret", "password", "auth", "credential")

# Setup failure kinds: the case failed before any evaluator could run.
_SETUP_KINDS = frozenset(
    {
        "snapshot_missing",
        "snapshot_unreadable",
        "snapshot_mismatch",
        "evidence_missing",
        "evidence_unreadable",
        "evidence_mismatch",
    }
)


def _looks_secret(name: object) -> bool:
    lowered = str(name).lower()
    return any(hint in lowered for hint in _SECRET_KEY_HINTS)


def run_identity(data: dict[str, Any]) -> str:
    """Deterministic content identity of a run manifest."""
    semantic = {key: value for key, value in data.items() if key not in _SEMANTIC_EXCLUDED}
    payload = canonical_dump(semantic)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{BENCHMARK_SCHEME}:{digest}"


def build_run_manifest(run: RunInput, executed: list[ExecutedCase]) -> dict[str, Any]:
    """Compose a manifest from the run inputs and its executed cases."""
    base = run_dir(run.results_dir, run.run_id)

    provider_config: dict[str, Any] = {
        "provider_name": run.config.provider_name,
        "model": run.config.model,
        "temperature": run.config.temperature,
        "max_tokens": run.config.max_tokens,
        "timeout_s": run.config.timeout_s,
        "description": run.provider.name if run.provider.name else run.config.provider_name,
        "extra": sanitize_config(dict(run.config.extra)),
    }
    public = sanitize_config(run.provider.public_config())
    provider_config["public"] = public

    manifest: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "system": SYSTEM_ID,
        "benchmark_version": __version__,
        "run_id": run.run_id,
        "dataset": {
            "name": run.dataset.name,
            "version": run.dataset.version,
            "status": run.dataset.status,
            "identity": run.dataset_identity,
        },
        "rubric_version": RUBRIC_VERSION,
        "cases": [case.candidate_id for case in run.cases],
        "evidence": {case.case_id: case.evidence_identity for case in executed},
        "evaluators": {
            "baseline": {
                "enabled": "baseline" in run.evaluators,
                "baseline_version": BASELINE_VERSION,
                "prompt_version": BASELINE_PROMPT_VERSION,
            },
            "repoguard": {
                "enabled": "repoguard" in run.evaluators,
                "repoguard_version": REPOGUARD_VERSION,
                "prompt_version": REPOGUARD_PROMPT_VERSION,
            },
        },
        "provider": provider_config,
        "results": {case.case_id: _result_entry(case, base) for case in executed},
        "created_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
    manifest["run_identity"] = run_identity(manifest)
    return manifest


def _result_entry(case: ExecutedCase, base: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "status": case.status,
        "delta": case.delta,
        "error": case.error.to_dict() if case.error is not None else None,
    }
    if case.baseline is not None:
        entry["baseline"] = _outcome_with_relative_path(case.baseline, base)
    if case.repoguard is not None:
        entry["repoguard"] = _outcome_with_relative_path(case.repoguard, base)
    return entry


def _outcome_with_relative_path(outcome: EvaluatorOutcome, base: Path) -> dict[str, Any]:
    data = outcome.to_dict()
    raw_path = data.pop("result_path", None)
    if isinstance(raw_path, str):
        try:
            data["result_path"] = Path(raw_path).relative_to(base).as_posix()
        except ValueError:
            data["result_path"] = raw_path
    else:
        data["result_path"] = None
    return data


def write_run_manifest(
    results_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
    secrets: Iterable[str] = (),
) -> Path:
    """Write the immutable run manifest; returns its path."""
    rendered = canonical_dump(manifest)
    path = run_dir(results_dir, run_id) / RUN_MANIFEST_FILE
    path.write_text(mask_secrets(rendered, list(secrets)), encoding="utf-8", newline="\n")
    return path


def load_run_manifest(run_dir_path: Path) -> tuple[dict[str, Any] | None, str]:
    """Read a run manifest. Returns ``(data, error)``; exactly one is set."""
    path = run_dir_path / RUN_MANIFEST_FILE
    if not path.is_file():
        return None, f"run manifest missing: {path}"
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return None, f"run manifest unreadable: {exc}"
    if not isinstance(raw, dict):
        return None, "run manifest is not a mapping"
    return raw, ""


def validate_run(run_dir_path: Path) -> list[str]:
    """Validate an entire run directory; returns human-readable problems."""
    manifest, error = load_run_manifest(run_dir_path)
    if manifest is None:
        return [error]
    problems = validate_manifest_structure(manifest)
    if problems:
        return problems

    for case_id in manifest["cases"]:
        problems += _validate_case(run_dir_path, manifest, str(case_id))
    problems += _scan_for_secrets(run_dir_path)
    return problems


def validate_manifest_structure(manifest: dict[str, Any]) -> list[str]:
    """Structural and identity checks on a loaded manifest."""
    problems: list[str] = []
    if manifest.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        problems.append("run manifest has an unknown schema version")
    if manifest.get("system") != SYSTEM_ID:
        problems.append("run manifest is not a benchmark manifest")
    recorded = manifest.get("run_identity")
    if not isinstance(recorded, str):
        problems.append("run manifest has no run identity")
    elif recorded != run_identity(manifest):
        problems.append("run identity does not match the manifest content")

    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        problems.append("run manifest has no dataset binding")
    else:
        for key in ("name", "version", "status", "identity"):
            if not isinstance(dataset.get(key), str) or not dataset[key]:
                problems.append(f"run manifest dataset.{key} is missing")

    rubric = manifest.get("rubric_version")
    if rubric != RUBRIC_VERSION:
        problems.append(f"run manifest rubric_version {rubric!r} != {RUBRIC_VERSION!r}")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        problems.append("run manifest has no cases")
    evidence = manifest.get("evidence")
    if not isinstance(evidence, dict):
        problems.append("run manifest has no evidence bindings")
    results = manifest.get("results")
    if not isinstance(results, dict):
        problems.append("run manifest has no results")

    if isinstance(cases, list) and isinstance(results, dict):
        for case_id in cases:
            if str(case_id) not in results:
                problems.append(f"run manifest has no outcome for case {case_id}")
    return problems


def _validate_case(run_dir_path: Path, manifest: dict[str, Any], case_id: str) -> list[str]:
    results = manifest["results"]
    evidence = manifest["evidence"]
    rubric = str(manifest["rubric_version"])
    entry = results.get(case_id)
    if not isinstance(entry, dict):
        return [f"case {case_id}: no outcome recorded"]

    problems: list[str] = []
    ev = evidence.get(case_id)
    entry_status = entry.get("status")
    if entry_status not in (STATUS_SUCCEEDED, STATUS_FAILED):
        problems.append(f"case {case_id}: unknown status {entry_status!r}")

    if ev is None:
        # A setup failure: no evidence, no evaluator outcomes.
        for system in ("baseline", "repoguard"):
            if entry.get(system) is not None:
                problems.append(f"case {case_id}: {system} ran without evidence")
        error = entry.get("error")
        if not isinstance(error, dict) or error.get("kind") not in _SETUP_KINDS:
            problems.append(f"case {case_id}: setup failure has no recorded setup error")
        return problems

    problems += _validate_outcome(
        run_dir_path, entry, "baseline", case_id, ev, rubric, baseline_schema=True
    )
    problems += _validate_outcome(
        run_dir_path, entry, "repoguard", case_id, ev, rubric, baseline_schema=False
    )

    record_error = entry.get("error")
    for system in ("baseline", "repoguard"):
        outcome = entry.get(system)
        if isinstance(outcome, dict) and outcome.get("status") == STATUS_FAILED:
            if not isinstance(record_error, dict):
                problems.append(f"case {case_id}: {system} failed without a case error")
    return problems


def _validate_outcome(
    run_dir_path: Path,
    entry: dict[str, Any],
    system: str,
    case_id: str,
    evidence_identity: Any,
    rubric: str,
    *,
    baseline_schema: bool,
) -> list[str]:
    outcome = entry.get(system)
    if outcome is None:
        return []
    if not isinstance(outcome, dict):
        return [f"case {case_id}: outcome for {system} is malformed"]

    recompute = baseline_identity if baseline_schema else repoguard_identity
    problems: list[str] = []
    status = outcome.get("status")
    if status not in (STATUS_SUCCEEDED, STATUS_FAILED):
        problems.append(f"case {case_id}: {system} outcome has unknown status")
        return problems

    rel = outcome.get("result_path")
    if not isinstance(rel, str):
        problems.append(f"case {case_id}: {system} has no result path")
        return problems
    result_path = run_dir_path / rel
    if not result_path.is_file():
        problems.append(f"case {case_id}: {system} result missing: {rel}")
        return problems
    try:
        raw: object = yaml.safe_load(result_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        problems.append(f"case {case_id}: {system} result unreadable: {exc}")
        return problems
    if not isinstance(raw, dict):
        problems.append(f"case {case_id}: {system} result is not a mapping")
        return problems

    recorded_identity = outcome.get("result_identity")
    recomputed = recompute(raw)
    if raw.get("result_identity") != recomputed:
        problems.append(f"case {case_id}: {system} result identity does not match its content")
    elif not isinstance(recorded_identity, str) or recorded_identity != recomputed:
        problems.append(f"case {case_id}: {system} result identity does not match the manifest")
    if raw.get("evidence_identity") != evidence_identity:
        problems.append(f"case {case_id}: {system} result evidence does not match the run")
    if raw.get("rubric_version") != rubric:
        problems.append(f"case {case_id}: {system} result rubric does not match the run")
    if raw.get("status") != status:
        problems.append(f"case {case_id}: {system} result status does not match the manifest")

    if status == STATUS_SUCCEEDED:
        score = outcome.get("score")
        raw_summary = raw.get("scoring")
        raw_score = raw_summary.get("score") if isinstance(raw_summary, dict) else None
        if score is None or raw_score is None or score != raw_score:
            problems.append(f"case {case_id}: {system} score does not match the recorded outcome")
    else:
        if outcome.get("score") is not None:
            problems.append(f"case {case_id}: {system} failed but recorded a score")
        if raw.get("scoring") is not None:
            problems.append(f"case {case_id}: {system} failed result carried a scoring summary")
        if raw.get("error") is None:
            problems.append(f"case {case_id}: {system} failed result has no recorded error")
    return problems


def _scan_for_secrets(run_dir_path: Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(run_dir_path.rglob("*.yaml")):
        try:
            raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if _contains_secret_key(raw):
            problems.append(f"secret-looking key found in {path.relative_to(run_dir_path)}")
    return problems


def _contains_secret_key(value: Any, seen: set[int] | None = None) -> bool:
    if seen is None:
        seen = set()
    marker = id(value)
    if marker in seen:
        return False
    seen.add(marker)
    if isinstance(value, dict):
        for key, sub in value.items():
            if _looks_secret(key) and isinstance(sub, str) and sub:
                return True
            if _contains_secret_key(sub, seen):
                return True
    elif isinstance(value, list):
        for item in value:
            if _contains_secret_key(item, seen):
                return True
    return False
