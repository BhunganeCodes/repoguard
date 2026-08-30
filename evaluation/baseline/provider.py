"""LLM provider interface and implementations for the baseline evaluator.

The baseline talks to a model through a small, provider-agnostic interface so
no proprietary vendor is hard-coded (docs/baseline.md, "Provider interface").

Two implementations exist:

* :class:`MockProvider` - deterministic, network-free provider used by unit
  tests and available for offline smoke runs. It never requires an API key.
  It can read a canned response from the ``REPOGUARD_MOCK_RESPONSE``
  environment variable for CLI smoke tests.
* :class:`HTTPCompatibleProvider` - a generic ``/chat/completions`` HTTP
  client configured through environment variables. It speaks the de-facto
  chat-completions JSON shape, so it works with any endpoint implementing it
  (including OpenAI, Google Gemini's OpenAI-compatible layer, and local
  servers), and is never exercised by the unit tests. The API key is read
  from ``REPOGUARD_LLM_API_KEY``, or ``OPENROUTER_API_KEY`` for OpenRouter
  endpoints, or ``GEMINI_API_KEY`` as a fallback for Google endpoints.

No API key is required to construct or test the baseline: the default
provider is the mock, and the HTTP provider fails closed unless configured.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from evaluation.baseline.errors import ProviderError

# Environment variables configuring the HTTP provider (never committed).
ENV_PROVIDER = "REPOGUARD_LLM_PROVIDER"
ENV_MODEL = "REPOGUARD_LLM_MODEL"
ENV_BASE_URL = "REPOGUARD_LLM_BASE_URL"
ENV_API_KEY = "REPOGUARD_LLM_API_KEY"
ENV_TIMEOUT_S = "REPOGUARD_LLM_TIMEOUT_S"
ENV_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"
ENV_MOCK_RESPONSE = "REPOGUARD_MOCK_RESPONSE"

# Provider identifiers accepted by :func:`build_provider`.
MOCK_PROVIDER = "mock"
HTTP_PROVIDER_IDS = ("http", "openai", "openai-compatible")


@dataclass(slots=True)
class LLMRequest:
    """The exact inputs sent to a provider."""

    system: str
    prompt: str
    model: str
    temperature: float = 0.0
    max_tokens: int | None = None


@dataclass(slots=True)
class LLMResponse:
    """What a provider returned, plus metadata it exposed.

    ``input_tokens``, ``output_tokens``, and ``estimated_cost`` are recorded
    only when the provider exposes them; otherwise they stay ``None``. Cost
    is never invented.
    """

    text: str
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    """Minimal provider contract. Implementations must be thread-safe enough
    for one request per assessment (the baseline sends exactly one)."""

    name: str

    def generate(self, request: LLMRequest) -> LLMResponse: ...
    def public_config(self) -> dict[str, Any]:
        """Non-secret configuration recorded in result artifacts."""
        ...


class MockProvider:
    """Deterministic, network-free provider for tests and smoke runs."""

    name = MOCK_PROVIDER

    def __init__(
        self,
        response_text: str | None = None,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        estimated_cost: float | None = None,
        metadata: dict[str, Any] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._response_text = (
            response_text if response_text is not None else os.environ.get(ENV_MOCK_RESPONSE, "")
        )
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._estimated_cost = estimated_cost
        self._metadata = dict(metadata or {})
        self._exc = exc

    def generate(self, request: LLMRequest) -> LLMResponse:
        if self._exc is not None:
            raise self._exc
        return LLMResponse(
            text=self._response_text,
            model=request.model or self.name,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            estimated_cost=self._estimated_cost,
            metadata={"provider": self.name, **self._metadata},
        )

    def public_config(self) -> dict[str, Any]:
        return {"mode": self.name}


def request_payload(request: LLMRequest) -> dict[str, Any]:
    """Build the generic chat-completions request body (pure, testable)."""
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.prompt},
        ],
        "temperature": request.temperature,
    }
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    return payload


def parse_http_response(body: str) -> LLMResponse:
    """Parse a chat-completions JSON body into an :class:`LLMResponse`.

    Pure and testable without network access. Fails closed on any shape it
    does not understand.
    """
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"provider returned invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProviderError("provider response is not a JSON mapping")
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("provider response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderError("provider choice is not a mapping")
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("provider returned no text content")

    model = raw.get("model")
    if not isinstance(model, str):
        model = ""

    usage = raw.get("usage")
    input_tokens: int | None = None
    output_tokens: int | None = None
    if isinstance(usage, dict):
        input_tokens = _optional_int(usage.get("prompt_tokens"))
        output_tokens = _optional_int(usage.get("completion_tokens"))

    metadata: dict[str, Any] = {"provider": HTTP_PROVIDER_IDS[-1]}
    if isinstance(usage, dict):
        metadata["usage"] = dict(usage)

    return LLMResponse(
        text=content,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=None,
        metadata=metadata,
    )


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


class HTTPCompatibleProvider:
    """Generic chat-completions HTTP provider (env-configured)."""

    name = HTTP_PROVIDER_IDS[-1]

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s

    @classmethod
    def from_env(
        cls,
        *,
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> HTTPCompatibleProvider:
        base_url = os.environ.get(ENV_BASE_URL, "").strip()
        if not base_url:
            raise ProviderError(f"openai-compatible provider requires {ENV_BASE_URL} to be set")
        resolved_model = (model or os.environ.get(ENV_MODEL, "")).strip()
        if not resolved_model:
            raise ProviderError(
                f"openai-compatible provider requires the model (set {ENV_MODEL} or pass --model)"
            )
        api_key = (
            os.environ.get(ENV_API_KEY, "")
            or os.environ.get(ENV_OPENROUTER_API_KEY, "")
            or os.environ.get(ENV_GEMINI_API_KEY, "")
        )
        timeout_value = os.environ.get(ENV_TIMEOUT_S, "").strip()
        if timeout_value:
            try:
                timeout_s = float(timeout_value)
            except ValueError as exc:
                raise ProviderError(
                    f"{ENV_TIMEOUT_S} must be a number, got {timeout_value!r}"
                ) from exc
        return cls(base_url=base_url, model=resolved_model, api_key=api_key, timeout_s=timeout_s)

    def generate(self, request: LLMRequest) -> LLMResponse:
        url = f"{self._base_url}/chat/completions"
        data = json.dumps(request_payload(request)).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        http_request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout_s) as response:
                body = response.read().decode("utf-8")
        except OSError as exc:
            raise ProviderError(f"provider request failed: {exc}") from exc
        return parse_http_response(body)

    def public_config(self) -> dict[str, Any]:
        return {"mode": self.name, "base_url": self._base_url}


def build_provider(
    name: str | None = None,
    *,
    model: str | None = None,
    timeout_s: float = 60.0,
) -> LLMProvider:
    """Resolve a provider by name, env var, or the ``mock`` default.

    The HTTP provider is selected only when explicitly requested by name or
    by ``REPOGUARD_LLM_PROVIDER``; it fails closed when required
    configuration is absent. Unit tests never reach the network.
    """
    provider_name = (name or os.environ.get(ENV_PROVIDER) or MOCK_PROVIDER).strip().lower()
    if provider_name == MOCK_PROVIDER:
        return MockProvider()
    if provider_name in HTTP_PROVIDER_IDS:
        return HTTPCompatibleProvider.from_env(model=model, timeout_s=timeout_s)
    raise ProviderError(
        f"unknown provider {provider_name!r}; expected one of {MOCK_PROVIDER}, openai-compatible"
    )
