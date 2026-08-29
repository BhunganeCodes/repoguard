"""Issue #24 — Demo / reproducibility regression tests.

These verify, through the real product/API path (no mocked API response), that
Demo works in a completely clean LLM environment, is isolated from ambient
provider configuration, stays deterministic across repeated executions, and
never invokes an HTTP provider. The Demo runs the genuine demo implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repoguard.main import app
from repoguard.services import store

PROVIDER_ENV_VARS = (
    "REPOGUARD_LLM_PROVIDER",
    "REPOGUARD_LLM_BASE_URL",
    "REPOGUARD_LLM_MODEL",
    "REPOGUARD_LLM_TIMEOUT_S",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "REPOGUARD_LLM_API_KEY",
)

DEMO_URL = "https://github.com/example/demo-synthetic-repo"


@pytest.fixture
def clean_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with an isolated data dir and a completely absent LLM env."""
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    for name in PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return TestClient(app)


@pytest.fixture
def ambient_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with the full ambient live-provider environment present."""
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv("REPOGUARD_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("REPOGUARD_LLM_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "ambient-model")
    monkeypatch.setenv("REPOGUARD_LLM_TIMEOUT_S", "120")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-ambient-gemini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-ambient-openrouter")
    monkeypatch.setenv("REPOGUARD_LLM_API_KEY", "sk-ambient-llm")
    return TestClient(app)


def _post_demo(client: TestClient, **overrides: object) -> dict:
    payload = {"repository_url": DEMO_URL, "mode": "demo", **overrides}
    response = client.post("/api/assess", json=payload)
    return response.status_code, response.json()


def test_live_is_unconfigured_in_clean_environment(clean_client: TestClient) -> None:
    """The clean env genuinely lacks a provider: Live fails closed (never mock)."""
    status, body = _post_demo(clean_client, mode="live")
    assert status == 400
    assert body["detail"]["error"] == "provider_unavailable"


def test_demo_succeeds_with_completely_absent_provider_environment(
    clean_client: TestClient,
) -> None:
    """Demo works with every provider variable and key absent (no network)."""
    identities: set[str] = set()
    scores: set[float] = set()
    for _ in range(3):
        status, body = _post_demo(clean_client)
        assert status == 201
        assert body["demo"] is True
        assert body["status"] == "succeeded"
        identities.add(body["assessment_id"])
        scores.add(body["result"]["scoring"]["score"])
        assert body["result"]["provider"]["name"] == "mock"
        assert body["result"]["provider"]["model"] == "mock"
        assert body["result"]["error"] is None
        assert body["result"]["result_identity"] == body["assessment_id"]
        assert body["result"]["case_id"] == "DEMO001"
        assert body["result"]["name"] == "demo-synthetic-repo"

    assert len(identities) == 1
    assert len(scores) == 1
    assert scores.pop() == 63.0


def test_demo_artifact_is_valid_and_persisted(clean_client: TestClient) -> None:
    """The canonical artifact files exist on disk under the runtime store."""
    status, body = _post_demo(clean_client)
    assert status == 201
    digest = store.digest_of(body["assessment_id"])
    result_file = store.result_path(digest)
    evidence_file = store.evidence_path(digest)
    assert result_file.exists()
    assert evidence_file.exists()
    persisted = store.load_yaml(result_file)
    assert persisted["result_identity"] == body["assessment_id"]
    assert persisted["status"] == "succeeded"


def test_demo_ignores_ambient_live_provider_environment(
    clean_client: TestClient, ambient_client: TestClient
) -> None:
    """Provider env on the host cannot redirect Demo to a live provider."""
    clean_status, clean_body = _post_demo(clean_client)
    ambient_status, ambient_body = _post_demo(ambient_client)
    assert clean_status == 201 and ambient_status == 201
    assert ambient_body["status"] == "succeeded"
    assert ambient_body["result"]["provider"]["name"] == "mock"
    assert ambient_body["result"]["provider"]["model"] == "mock"
    assert ambient_body["assessment_id"] == clean_body["assessment_id"]
    assert ambient_body["result"]["scoring"]["score"] == clean_body["result"]["scoring"]["score"]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_SRC = (_REPO_ROOT / "app" / "repoguard" / "services" / "demo.py").read_text(encoding="utf-8")
_EXECUTOR_SRC = (_REPO_ROOT / "app" / "repoguard" / "services" / "executor.py").read_text(
    encoding="utf-8"
)


def test_demo_source_never_references_an_http_provider() -> None:
    """Network isolation at the source level: the only provider is MockProvider."""
    assert "MockProvider" in _DEMO_SRC
    assert "build_provider" not in _DEMO_SRC
    assert "build_demo_provider" in _DEMO_SRC
    for http_marker in ("requests", "urllib", "httpx", "http.client"):
        assert http_marker not in _DEMO_SRC


def test_executor_demo_branch_resolves_the_demo_path_not_live() -> None:
    demo_branch = _EXECUTOR_SRC.split('if mode == "demo":', 1)[1].split("else:", 1)[0]
    live_after = _EXECUTOR_SRC.split("else:", 1)[1]
    assert "build_demo_provider()" in demo_branch
    assert "build_provider(" not in demo_branch
    assert "_resolve_live_provider(provider)" in live_after
