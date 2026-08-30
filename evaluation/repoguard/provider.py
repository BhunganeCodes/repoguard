"""RepoGuard provider interface.

RepoGuard deliberately reuses the baseline's provider abstraction
(``evaluation.baseline.provider``) rather than duplicating it: the
:class:`~evaluation.baseline.provider.LLMProvider` protocol, the
``mock`` provider (deterministic and network-free, used by every unit
test), and the environment-configured ``openai-compatible`` provider are
the same contract for both systems (docs/repoguard.md, "Provider
abstraction").

This module exists so RepoGuard code imports one obvious provider
namespace, and so additional RepoGuard-only providers (none today) have a
stable home. Real provider configuration stays external; no credentials
are ever recorded.
"""

from __future__ import annotations

from evaluation.baseline.provider import (
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_GEMINI_API_KEY,
    ENV_MOCK_RESPONSE,
    ENV_MODEL,
    ENV_OPENROUTER_API_KEY,
    ENV_PROVIDER,
    ENV_TIMEOUT_S,
    HTTP_PROVIDER_IDS,
    MOCK_PROVIDER,
    HTTPCompatibleProvider,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    MockProvider,
    build_provider,
    parse_http_response,
    request_payload,
)
from evaluation.repoguard.errors import ProviderError

__all__ = [
    "MOCK_PROVIDER",
    "HTTP_PROVIDER_IDS",
    "ENV_PROVIDER",
    "ENV_MODEL",
    "ENV_BASE_URL",
    "ENV_API_KEY",
    "ENV_TIMEOUT_S",
    "ENV_OPENROUTER_API_KEY",
    "ENV_GEMINI_API_KEY",
    "ENV_MOCK_RESPONSE",
    "LLMRequest",
    "LLMResponse",
    "LLMProvider",
    "MockProvider",
    "HTTPCompatibleProvider",
    "build_provider",
    "parse_http_response",
    "request_payload",
    "ProviderError",
]
