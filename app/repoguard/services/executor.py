"""Assessment orchestration for the product interface.

``run_assessment`` wires together the evaluation framework's subsystems in
their canonical order -- snapshot acquisition -> evidence extraction ->
RepoGuard (`run_case`) -- and persists the resulting artifacts to the runtime
store. No scoring or validation logic is reimplemented here: the product layer
only calls the framework's existing functions.

Failure semantics match the framework:

* input problems raise :class:`AssessmentInputError` (client error, HTTP 400)
* acquisition/extraction/provider-resolution failures raise
  :class:`AssessmentExecutionError` (server/environment error, HTTP 502)
* model failures (``provider_error``, ``malformed_response``, ...) never raise:
  ``run_case`` records them in a ``failed`` result artifact, which is persisted
  and returned -- failed runs are never converted into scores.

Every product-level failure carries a stable ``code`` from a small, documented
vocabulary (``repository_invalid``, ``repository_unavailable``,
``snapshot_error``, ``evidence_error``, ``provider_unavailable``); the API
translates these into status codes and human messages. The evaluation engine's
own failure vocabulary is never duplicated.

Live mode mirrors the CLI's model resolution: the configured provider is used
for the run, and the configured model reaches the provider request. Live never
implicitly falls back to ``MockProvider`` -- a missing provider is a controlled
product error instead.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from evaluation.baseline.errors import ProviderError
from evaluation.baseline.pipeline import EvaluatorConfig
from evaluation.baseline.provider import (
    ENV_MODEL,
    ENV_PROVIDER,
    HTTP_PROVIDER_IDS,
    LLMProvider,
    build_provider,
)
from evaluation.evidence.extract import extract_snapshot_directory
from evaluation.evidence.serialize import write_artifact
from evaluation.repoguard.pipeline import run_case
from evaluation.repoguard.serialize import compose_result, write_result
from evaluation.snapshot.acquire import acquire_case
from evaluation.snapshot.errors import (
    AcquisitionError,
    CommitNotFoundError,
    SnapshotError,
)
from evaluation.snapshot.git import ls_remote_head
from evaluation.snapshot.models import DatasetManifest, ManifestCase
from repoguard.services import demo as demo_service
from repoguard.services import store as store_service

# Stable product-level error codes (documented in docs/product-interface.md).
ERROR_REPOSITORY_INVALID = "repository_invalid"
ERROR_REPOSITORY_UNAVAILABLE = "repository_unavailable"
ERROR_SNAPSHOT = "snapshot_error"
ERROR_EVIDENCE = "evidence_error"
ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"


class AssessmentInputError(Exception):
    """Invalid input or an unresolvable requested commit (client error).

    Carries a stable ``code`` and a human message; the ``code`` is exposed to
    clients so the UI can classify the failure without parsing prose.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or [])


class AssessmentExecutionError(Exception):
    """The assessment could not be executed (server/environment error).

    Carries a stable ``code`` and a human message (see
    :class:`AssessmentInputError`).
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or [])


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


def _env_provider_name() -> str:
    return (os.environ.get(ENV_PROVIDER, "") or "").strip().lower()


def _effective_model(provider_name: str) -> str:
    """Mirror the CLI's model resolution (evaluation/repoguard/cli.py).

    HTTP providers use the configured ``REPOGUARD_LLM_MODEL`` (falling back to
    ``"mock"`` exactly as the CLI does); every other provider resolves to
    ``"mock"``. The product has no per-request ``--model`` override.
    """
    if provider_name in HTTP_PROVIDER_IDS:
        return os.environ.get(ENV_MODEL, "").strip() or "mock"
    return "mock"


def _resolve_live_provider(provider: LLMProvider | None) -> LLMProvider:
    """Resolve the Live provider without silently falling back to Mock.

    ``provider`` is an optional explicit override so tests (and future
    hard-wiring) can inject a provider directly. The implicit production
    fallback is deliberately absent: an unset ``REPOGUARD_LLM_PROVIDER`` is a
    controlled product error, never a MockProvider.
    """
    if provider is not None:
        # Explicit override (unit tests / injected providers): honoured as
        # configured, since this is not an implicit fallback.
        return provider
    if not _env_provider_name():
        raise AssessmentInputError(
            ERROR_PROVIDER_UNAVAILABLE,
            "Live Assessment is not configured on this server.",
        )
    try:
        return build_provider()
    except ProviderError as exc:
        raise AssessmentInputError(
            ERROR_PROVIDER_UNAVAILABLE,
            "Live Assessment is not configured on this server.",
        ) from exc


def run_assessment(
    *,
    repository_url: str,
    commit: str | None,
    mode: str,
    provider: LLMProvider | None = None,
) -> AssessmentOutcome:
    """Run one assessment; persists result + evidence; returns the outcome."""
    if mode not in ("live", "demo"):
        raise AssessmentInputError(
            "invalid_mode",
            f"Unknown mode {mode!r}; expected 'live' or 'demo'.",
        )

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
        resolved_provider = _resolve_live_provider(provider)
        provider_name = _env_provider_name() if provider is None else provider.name
        config = EvaluatorConfig(
            provider_name=provider_name,
            model=_effective_model(provider_name),
        )
        resolved_commit = _resolve_commit(repository_url, commit)
        snapshot = _acquire(repository_url, resolved_commit)
        try:
            evidence = extract_snapshot_directory(snapshot)
        except Exception as exc:  # noqa: BLE001 - surface as product error
            raise AssessmentExecutionError(
                ERROR_EVIDENCE,
                "Evidence could not be extracted from the repository snapshot.",
                details=[str(exc)],
            ) from exc

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


def _resolve_commit(repository_url: str, commit: str | None) -> str:
    """Pin the commit for a Live run.

    A provided commit is trusted as-is (the user pinned it); otherwise the
    remote's default-branch HEAD is resolved. Unresolvable remotes are
    classified as ``repository_unavailable`` (infrastructure/reachability),
    not as a user-fixable input error.
    """
    if commit:
        return commit
    try:
        return ls_remote_head(repository_url)
    except CommitNotFoundError as exc:
        raise AssessmentInputError(
            ERROR_REPOSITORY_INVALID,
            "That commit could not be resolved for the repository.",
        ) from exc
    except AcquisitionError as exc:
        raise AssessmentExecutionError(
            ERROR_REPOSITORY_UNAVAILABLE,
            "RepoGuard could not access that repository or commit.",
        ) from exc


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
        raise AssessmentInputError(
            ERROR_REPOSITORY_INVALID,
            "That commit does not exist in the repository.",
        ) from exc
    except AcquisitionError as exc:
        raise AssessmentExecutionError(
            ERROR_REPOSITORY_UNAVAILABLE,
            "RepoGuard could not access that repository or commit.",
        ) from exc
    except SnapshotError as exc:
        raise AssessmentExecutionError(
            ERROR_SNAPSHOT,
            "The repository snapshot could not be recorded.",
        ) from exc
    return acquired.path
