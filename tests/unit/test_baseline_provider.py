"""Provider interface, mock provider, and HTTP response parsing."""

from __future__ import annotations

import pytest

from evaluation.baseline import provider as provider_module
from evaluation.baseline.errors import ProviderError
from evaluation.baseline.provider import (
    ENV_PROVIDER,
    MockProvider,
    build_provider,
    parse_http_response,
    request_payload,
)


def _request() -> object:
    from evaluation.baseline.provider import LLMRequest

    return LLMRequest(system="rules", prompt="assessment?", model="m1", max_tokens=200)


def test_mock_provider_returns_canned_response() -> None:
    mock = MockProvider("hello", input_tokens=5, output_tokens=9)
    response = mock.generate(_request())
    assert response.text == "hello"
    assert response.input_tokens == 5
    assert response.output_tokens == 9
    assert response.model == "m1"
    assert response.estimated_cost is None
    assert mock.name == "mock"
    assert mock.public_config()["mode"] == "mock"


def test_mock_provider_raises_configured_exception() -> None:
    mock = MockProvider(exc=ProviderError("boom"))
    with pytest.raises(ProviderError, match="boom"):
        mock.generate(_request())


def test_mock_provider_reads_env_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOGUARD_MOCK_RESPONSE", "canned")
    assert MockProvider().generate(_request()).text == "canned"
    explicit = MockProvider("explicit")
    assert explicit.generate(_request()).text == "explicit"


def test_request_payload_shape() -> None:
    payload = request_payload(_request())
    assert payload["model"] == "m1"
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert payload["messages"][1]["content"] == "assessment?"
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 200


def test_request_payload_omits_unset_max_tokens() -> None:
    from evaluation.baseline.provider import LLMRequest

    payload = request_payload(LLMRequest(system="s", prompt="p", model="m"))
    assert "max_tokens" not in payload


def test_parse_http_response_success() -> None:
    body = (
        '{"model": "m1", '
        '"choices": [{"message": {"content": "{\\"criteria\\": []}"}}], '
        '"usage": {"prompt_tokens": 7, "completion_tokens": 11}}'
    )
    response = parse_http_response(body)
    assert response.text == '{"criteria": []}'
    assert response.model == "m1"
    assert response.input_tokens == 7
    assert response.output_tokens == 11
    assert response.estimated_cost is None
    assert response.metadata["usage"]["prompt_tokens"] == 7


def test_parse_http_response_rejects_malformed() -> None:
    with pytest.raises(ProviderError, match="invalid JSON"):
        parse_http_response("not json")
    with pytest.raises(ProviderError, match="no choices"):
        parse_http_response('{"model": "m"}')
    with pytest.raises(ProviderError, match="no text content"):
        parse_http_response('{"choices": [{"message": {"content": ""}}]}')


def test_build_provider_defaults_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_PROVIDER, raising=False)
    monkeypatch.delenv("REPOGUARD_LLM_BASE_URL", raising=False)
    assert build_provider().name == "mock"
    assert build_provider("mock").name == "mock"


def test_build_provider_unknown_fails_closed() -> None:
    with pytest.raises(ProviderError, match="unknown provider"):
        build_provider("gpt-corner")


def test_openai_compatible_requires_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPOGUARD_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("REPOGUARD_LLM_MODEL", raising=False)
    with pytest.raises(ProviderError, match="REPOGUARD_LLM_BASE_URL"):
        build_provider("openai-compatible")


def test_openai_missing_model_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOGUARD_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.delenv("REPOGUARD_LLM_MODEL", raising=False)
    with pytest.raises(ProviderError, match="model"):
        build_provider("openai-compatible")


def test_openai_compatible_public_config_has_no_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOGUARD_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "m1")
    monkeypatch.setenv("REPOGUARD_LLM_API_KEY", "sk-super-secret")
    provider_impl = provider_module.HTTPCompatibleProvider.from_env()
    config = str(provider_impl.public_config())
    assert "sk-super-secret" not in config
    assert config == "{'mode': 'openai-compatible', 'base_url': 'https://example.com/v1'}"


def test_openai_compatible_falls_back_to_gemini_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single GEMINI_API_KEY variable configures the generic provider for a
    Google Gemini OpenAI-compatible endpoint (nothing is hard-coded)."""
    monkeypatch.setenv(
        "REPOGUARD_LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "gemini-2.5-pro")
    monkeypatch.delenv("REPOGUARD_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-super-secret")
    provider_impl = provider_module.HTTPCompatibleProvider.from_env()
    assert provider_impl._api_key == "AIza-super-secret"
    assert "AIza-super-secret" not in str(provider_impl.public_config())


def test_openai_compatible_falls_back_to_openrouter_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPENROUTER_API_KEY configures the generic provider when the RepoGuard
    key is absent, taking precedence over the Gemini fallback."""
    monkeypatch.setenv("REPOGUARD_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "m1")
    monkeypatch.delenv("REPOGUARD_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fallback")
    provider_impl = provider_module.HTTPCompatibleProvider.from_env()
    assert provider_impl._api_key == "sk-or-secret"
    assert "sk-or-secret" not in str(provider_impl.public_config())
    assert "AIza-fallback" not in str(provider_impl.public_config())


def test_openai_compatible_openrouter_public_config_has_no_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOGUARD_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "m1")
    monkeypatch.delenv("REPOGUARD_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-super-secret")
    provider_impl = provider_module.HTTPCompatibleProvider.from_env()
    config = str(provider_impl.public_config())
    assert "sk-or-super-secret" not in config
    assert config == "{'mode': 'openai-compatible', 'base_url': 'https://openrouter.ai/api/v1'}"


def test_openai_compatible_explicit_key_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOGUARD_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "m1")
    monkeypatch.setenv("REPOGUARD_LLM_API_KEY", "sk-priority")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fallback")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fallback")
    provider_impl = provider_module.HTTPCompatibleProvider.from_env()
    assert provider_impl._api_key == "sk-priority"


def test_openai_compatible_timeout_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOGUARD_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "m1")
    monkeypatch.setenv("REPOGUARD_LLM_TIMEOUT_S", "600")
    assert provider_module.HTTPCompatibleProvider.from_env()._timeout_s == 600.0
    monkeypatch.setenv("REPOGUARD_LLM_TIMEOUT_S", "not-a-number")
    with pytest.raises(ProviderError, match="REPOGUARD_LLM_TIMEOUT_S"):
        provider_module.HTTPCompatibleProvider.from_env()
