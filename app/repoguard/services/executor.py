"""Assessment orchestration for the product interface.

``run_assessment`` wires together the evaluation framework's subsystems in
their canonical order -- snapshot acquisition -> evidence extraction ->
RepoGuard (`run_case`) -- and persists the resulting artifacts to the runtime
store. No scoring or validation logic is reimplemented here: the product layer
only calls the framework's existing functions.

Failure semantics match the framework:

* input problems raise :class:`AssessmentInputError` (client error, HTTP 400)
* acquisition/extraction/provider failures raise
  :class:`AssessmentExecutionError` (server/environment error, HTTP 502)
* model failures (``provider_error``, ``malformed_response``, ...) never raise:
  ``run_case`` records them in a ``failed`` result artifact, which is persisted
  and returned -- failed runs are never converted into scores.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from evaluation.baseline.pipeline import EvaluatorConfig
from evaluation.baseline.provider import LLMProvider, build_provider
from evaluation.evidence.extract import extract_snapshot_directory
from evaluation.evidence.serialize import write_artifact
from evaluation.repoguard.pipeline import run_case
from evaluation.repoguard.serialize import compose_result, write_result
from evaluation.snapshot.acquire import acquire_case
from evaluation.snapshot.errors import CommitNotFoundError, SnapshotError
from evaluation.snapshot.git import ls_remote_head
from evaluation.snapshot.models import DatasetManifest, ManifestCase
from repoguard.services import demo as demo_service
from repoguard.services import store as store_service


class AssessmentInputError(Exception):
    """Invalid input or an unresolvable requested commit (client error)."""


class AssessmentExecutionError(Exception):
    """The assessment could not be executed (server/environment error)."""


@dataclass(slots=True)
class AssessmentOutcome:
    result: dict[str, Any]
    evidence: dict[str, Any]
    identity: str
    mode: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _repo_name(repository_url: str) -> str:
    name = urlsplit(repository_url.rstrip("/")).path.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repository"


def _case_id_for(repository_url: str, commit: str) -> str:
    digest = hashlib.sha256(f"{repository_url}@{commit}".encode()).hexdigest()
    return f"R{digest[:12]}"


def run_assessment(
    *,
    repository_url: str,
    commit: str | None,
    mode: str,
    provider: LLMProvider | None = None,
) -> AssessmentOutcome:
    """Run one assessment; persists result + evidence; returns the outcome."""
    if mode not in ("live", "demo"):
        raise AssessmentInputError(f"unknown mode {mode!r}; expected live or demo")

    if mode == "demo":
        evidence = demo_service.build_demo_evidence(
            repository_url=repository_url,
            requested_commit=commit or demo_service.DEMO_NAME,
            verified_commit=commit or demo_service.DEMO_NAME,
        )
        resolved_commit = commit or demo_service.DEMO_NAME
        config = EvaluatorConfig(provider_name="mock", model="mock")
        resolved_provider: LLMProvider = demo_service.build_demo_provider()
    else:
        resolved_commit = commit if commit else ls_remote_head(repository_url)
        snapshot = _acquire(repository_url, resolved_commit)
        try:
            evidence = extract_snapshot_directory(snapshot)
        except Exception as exc:  # noqa: BLE001 - surface as execution error
            raise AssessmentExecutionError(f"evidence extraction failed: {exc}") from exc
        config = EvaluatorConfig()
        resolved_provider = provider or build_provider()

    outcome = run_case(evidence, resolved_provider, config=config, requested_at=_utc_now_iso())
    identity = compose_result(outcome)["result_identity"]
    digest = store_service.digest_of(identity)
    write_result(store_service.result_path(digest), outcome)
    write_artifact(store_service.evidence_path(digest), evidence)
    return AssessmentOutcome(
        result=compose_result(outcome),
        evidence=evidence.to_dict(),
        identity=identity,
        mode=mode,
    )


def _acquire(repository_url: str, commit: str) -> Path:
    case = ManifestCase(
        candidate_id=_case_id_for(repository_url, commit),
        name=_repo_name(repository_url),
        url=repository_url,
        pinned_commit=commit,
        ecosystem="unknown",
        license="unknown",
        dataset_decision="product-interface",
        dataset_status="adhoc",
    )
    manifest = DatasetManifest(
        name="repoguard-runtime",
        version="adhoc",
        creation_date=_utc_now_iso(),
        status="adhoc",
        source="product-interface",
        cases=[case],
    )
    try:
        acquired = acquire_case(case, manifest, store_service.snapshots_dir())
    except CommitNotFoundError as exc:
        raise AssessmentInputError(str(exc)) from exc
    except SnapshotError as exc:
        raise AssessmentExecutionError(f"snapshot acquisition failed: {exc}") from exc
    return acquired.path
