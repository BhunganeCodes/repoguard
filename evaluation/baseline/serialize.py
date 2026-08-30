"""Deterministic serialization, identity, and secret redaction for results.

The result artifact separates semantic content from runtime facts:

* ``result_identity`` is a SHA-256 over the canonical, key-sorted YAML
  rendering of every semantic field (everything except ``runtime`` and the
  identity itself).
* ``runtime`` (request timestamp, latency, token usage, cost, response
  metadata) is recorded in the artifact but excluded from the identity, so
  identical assessments have identical identities regardless of when they
  ran.

Model configuration is sanitized before it can appear in an artifact: any
configuration key that looks like a credential (key/token/secret/password/
auth) is dropped recursively. As a final safety net, ``render_result`` masks
known secret values from the rendered text.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evaluation.baseline._version import RESULT_SCHEMA_VERSION, RESULT_SCHEME, SYSTEM_ID
from evaluation.baseline.models import STATUS_FAILED, BaselineResult
from evaluation.evidence.serialize import canonical_dump

_SEMANTIC_EXCLUDED = frozenset({"runtime", "result_identity"})

# Keys never recorded, even when a provider exposes them. Applied recursively
# to model configuration before serialization.
_SECRET_KEY_HINTS = ("key", "token", "secret", "password", "auth", "credential")


def _looks_secret(name: object) -> bool:
    lowered = str(name).lower()
    return any(hint in lowered for hint in _SECRET_KEY_HINTS)


def sanitize_config(value: Any) -> Any:
    """Drop credential-looking keys from any nested mapping."""
    if isinstance(value, dict):
        return {key: sanitize_config(sub) for key, sub in value.items() if not _looks_secret(key)}
    if isinstance(value, list):
        return [sanitize_config(item) for item in value]
    return value


def mask_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace known secret values with ``<redacted>`` (defense in depth)."""
    for secret in secrets:
        if isinstance(secret, str) and secret:
            text = text.replace(secret, "<redacted>")
    return text


def semantic_payload(result: BaselineResult) -> dict[str, Any]:
    """The semantic content over which the result identity is computed."""
    provider: dict[str, Any] = {
        "name": result.provider_name,
        "model": result.provider_model,
        "config": sanitize_config(dict(result.model_config)),
    }
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "system": SYSTEM_ID,
        "baseline_version": result.baseline_version,
        "prompt_version": result.prompt_version,
        "rubric_version": result.rubric_version,
        "case_id": result.case_id,
        "name": result.name,
        "evidence_identity": result.evidence_identity,
        "status": result.status,
        "provider": provider,
        "assessment": result.assessment,
        "scoring": result.scoring,
        "error": result.error.to_dict() if result.error is not None else None,
        "model_response": result.model_response if result.status == STATUS_FAILED else None,
    }


def result_identity(result: BaselineResult) -> str:
    payload = canonical_dump(semantic_payload(result))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{RESULT_SCHEME}:{digest}"


def compose_result(result: BaselineResult) -> dict[str, Any]:
    """Full artifact: semantic payload + identity + runtime metadata."""
    payload = semantic_payload(result)
    payload["result_identity"] = result_identity(result)
    payload["runtime"] = result.runtime.to_dict()
    return payload


def render_result(result: BaselineResult, secrets: Iterable[str] = ()) -> str:
    """Deterministic YAML text of the composed result, secrets masked."""
    text = canonical_dump(compose_result(result))
    return mask_secrets(text, list(secrets))


def write_result(path: Path, result: BaselineResult, secrets: Iterable[str] = ()) -> str:
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
