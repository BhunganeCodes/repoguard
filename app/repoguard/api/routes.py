"""HTTP API for the RepoGuard product interface.

All assessment endpoints reuse the evaluation framework's canonical artifacts.
Synchronous by design (documented in docs/product-interface.md): every
``POST /api/assess`` completes the full pipeline and persists a content-
addressed result before returning. Lifecycle transparency is preserved via the
real workflow stage trace recorded in every result (``process.stages``), so a
failed run is always reported honestly rather than converted into a score.

Security boundaries:

* repository URLs are validated to http(s)/file schemes before any git call;
* assessments are addressed by validated 64-hex content digests only (no path
  traversal is possible);
* provider configuration and keys are never exposed -- results are serialized
  through the framework's secret-masking machinery.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from evaluation.snapshot.commits import normalize_sha
from evaluation.snapshot.errors import InvalidShaError
from repoguard.services import executor, store

router = APIRouter(prefix="/api")

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_SCHEMES = frozenset({"http", "https", "file"})


class AssessRequest(BaseModel):
    """Body of ``POST /api/assess``.

    ``commit`` is optional: for live assessments the default-branch HEAD is
    resolved (and pinned) when omitted. ``mode`` selects the assessment path:
    ``live`` snapshots and extracts the real repository, ``demo`` uses the
    deterministic synthetic Demo assessment.
    """

    repository_url: str
    commit: str | None = None
    mode: Literal["live", "demo"] = "live"


def _validate_repository_url(repository_url: str) -> str:
    normalized = repository_url.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="repository_url must not be empty")
    try:
        parts = urlsplit(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid repository URL: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported URL scheme {scheme!r}; expected http, https, or file",
        )
    if scheme in ("http", "https") and not parts.netloc:
        raise HTTPException(status_code=400, detail="repository URL is missing a host")
    if scheme == "file" and not parts.path:
        raise HTTPException(status_code=400, detail="repository URL is missing a path")
    return normalized


def _normalize_commit(commit: str) -> str:
    try:
        return normalize_sha(commit)
    except InvalidShaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _load_digest(assessment_id: str) -> str:
    digest = store.digest_of(assessment_id)
    if not _DIGEST_RE.fullmatch(digest):
        raise HTTPException(status_code=404, detail="assessment not found")
    return digest


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="assessment not found")


@router.post("/assess", status_code=201)
def create_assessment(payload: AssessRequest) -> dict[str, Any]:
    """Run one assessment end-to-end (synchronous) and persist its artifact."""
    repository_url = _validate_repository_url(payload.repository_url)
    commit = _normalize_commit(payload.commit) if payload.commit else None
    try:
        outcome = executor.run_assessment(
            repository_url=repository_url,
            commit=commit,
            mode=payload.mode,
        )
    except executor.AssessmentInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except executor.AssessmentExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "assessment_id": outcome.identity,
        "mode": outcome.mode,
        "demo": outcome.mode == "demo",
        "status": outcome.result.get("status"),
        "result": outcome.result,
        "evidence": outcome.evidence,
    }


@router.get("/assess/{assessment_id}")
def get_assessment(assessment_id: str) -> dict[str, Any]:
    """Return a persisted assessment result by its content identity."""
    digest = _load_digest(assessment_id)
    try:
        result = store.load_yaml(store.result_path(digest))
    except (OSError, ValueError):
        raise _not_found() from None
    return {
        "assessment_id": result.get("result_identity"),
        "status": result.get("status"),
        "result": result,
    }


@router.get("/assess/{assessment_id}/evidence")
def get_assessment_evidence(assessment_id: str) -> dict[str, Any]:
    """Return the evidence artifact behind a persisted assessment."""
    digest = _load_digest(assessment_id)
    try:
        evidence = store.load_yaml(store.evidence_path(digest))
    except (OSError, ValueError):
        raise _not_found() from None
    return {"assessment_id": evidence.get("evidence_identity"), "evidence": evidence}


@router.get("/assess/{assessment_id}/report")
def get_assessment_report(assessment_id: str) -> dict[str, Any]:
    """Return the canonical assessment/report artifact for an assessment."""
    digest = _load_digest(assessment_id)
    try:
        result = store.load_yaml(store.result_path(digest))
    except (OSError, ValueError):
        raise _not_found() from None
    return {
        "assessment_id": result.get("result_identity"),
        "report": result,
    }
