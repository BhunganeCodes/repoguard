"""Deterministic serialization, identity, and secret redaction for results.

The result artifact separates semantic content from runtime facts:

* ``result_identity`` is a SHA-256 over the canonical, key-sorted YAML
  rendering of every semantic field (everything except ``runtime`` and the
  identity itself). The workflow trace, plan record, and cross-check findings
  are RepoGuard output and therefore part of the identity; timestamps,
  latency, token usage, and cost are not.
* ``runtime`` (request timestamp, latency, token usage, cost, response
  metadata) is recorded in the artifact but excluded from the identity, so
  identical assessments have identical identities regardless of when they
  ran.

Secret redaction reuses the baseline's machinery: model configuration is
sanitized recursively (credential-looking keys are dropped) and
``render_result`` additionally masks known secret values from the rendered
text (defense in depth).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evaluation.baseline.serialize import mask_secrets, sanitize_config
from evaluation.evidence.serialize import canonical_dump
from evaluation.repoguard._version import RESULT_SCHEMA_VERSION, RESULT_SCHEME, SYSTEM_ID
from evaluation.repoguard.models import STATUS_FAILED, RepoResult

_SEMANTIC_EXCLUDED = frozenset({"runtime", "result_identity"})


def semantic_payload(result: RepoResult) -> dict[str, Any]:
    """The semantic content over which the result identity is computed."""
    provider: dict[str, Any] = {
        "name": result.provider_name,
        "model": result.provider_model,
        "config": sanitize_config(dict(result.model_config)),
    }
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "system": SYSTEM_ID,
        "repoguard_version": result.repoguard_version,
        "prompt_version": result.prompt_version,
        "rubric_version": result.rubric_version,
        "case_id": result.case_id,
        "name": result.name,
        "evidence_identity": result.evidence_identity,
        "status": result.status,
        "provider": provider,
        "process": result.process.to_dict(),
        "assessment": result.assessment,
        "scoring": result.scoring,
        "error": result.error.to_dict() if result.error is not None else None,
        "model_response": result.model_response if result.status == STATUS_FAILED else None,
    }


def result_identity(result: RepoResult) -> str:
    payload = canonical_dump(semantic_payload(result))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{RESULT_SCHEME}:{digest}"


def compose_result(result: RepoResult) -> dict[str, Any]:
    """Full artifact: semantic payload + identity + runtime metadata."""
    payload = semantic_payload(result)
    payload["result_identity"] = result_identity(result)
    payload["runtime"] = result.runtime.to_dict()
    return payload


def render_result(result: RepoResult, secrets: Iterable[str] = ()) -> str:
    """Deterministic YAML text of the composed result, secrets masked."""
    text = canonical_dump(compose_result(result))
    return mask_secrets(text, list(secrets))


def write_result(path: Path, result: RepoResult, secrets: Iterable[str] = ()) -> str:
    """Write the composed result to ``path``; returns the rendered text."""
    rendered = render_result(result, secrets)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return rendered


def recompute_identity(data: Any) -> str | None:
    """Recompute the identity of a serialized result (for ``inspect``)."""
    if not isinstance(data, dict):
        return None
    semantic = {key: value for key, value in data.items() if key not in _SEMANTIC_EXCLUDED}
    payload = canonical_dump(semantic)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{RESULT_SCHEME}:{digest}"
