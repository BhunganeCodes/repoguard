"""Product interface tests: HTTP API, demo mode, live wiring, and security.

No test here touches the network or a real model. Live-mode tests run against
temporary local git repositories (file:// URLs) and the framework's own
``MockProvider``; the extraction, scoring, and fail-closed validation are the
real framework code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evaluation.baseline.errors import ProviderError
from evaluation.baseline.provider import LLMResponse, MockProvider
from evaluation.scoring.rubric import CRITERIA, DIMENSIONS
from repoguard.main import app
from repoguard.services import executor, store

DEMO_URL = "https://github.com/example/demo-synthetic-repo"

FAKE_KEYS = {
    "REPOGUARD_LLM_API_KEY": "sk-repoguard-llm-secret",
    "OPENROUTER_API_KEY": "sk-openrouter-fake-secret",
    "GEMINI_API_KEY": "sk-gemini-fake-secret",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with an isolated runtime data dir and ambient keys masked."""
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv("REPOGUARD_LLM_PROVIDER", "mock")
    for name, value in FAKE_KEYS.items():
        monkeypatch.setenv(name, value)
    return TestClient(app)


def _post_assess(client: TestClient, **overrides: object) -> dict:
    payload = {"repository_url": DEMO_URL, "mode": "demo", **overrides}
    response = client.post("/api/assess", json=payload)
    return response.status_code, response.json()


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_demo_assessment_succeeds_and_is_deterministic(client: TestClient) -> None:
    status, body = _post_assess(client)
    assert status == 201
    assert body["demo"] is True
    assert body["mode"] == "demo"
    assert body["status"] == "succeeded"

    result = body["result"]
    assert result["result_identity"].startswith("repoguard-v1:")
    assert result["evidence_identity"]
    assert result["name"] == "demo-synthetic-repo"
    assert result["case_id"] == "DEMO001"
    assert result["error"] is None
    assert result["assessment"]["summary"]["complete"] is True
    assert result["scoring"]["score"] == 63.0
    assert {row["dimension"] for row in result["assessment"]["dimensions"]} == set(DIMENSIONS)
    assert all(row["status"] == "ok" for row in result["process"]["stages"])
    assert len(result["assessment"]["criteria"]) == len(CRITERIA)

    evidence = body["evidence"]
    assert evidence["evidence_identity"].startswith("repoguard-evidence-v1:")
    assert len(evidence["items"]) == 25
    assert {item["category"] for item in evidence["items"]} == set(DIMENSIONS)

    _, second = _post_assess(client)
    assert second["assessment_id"] == body["assessment_id"]
    assert second["evidence"]["evidence_identity"] == body["evidence"]["evidence_identity"]


def test_assess_lookup_endpoints_round_trip(client: TestClient) -> None:
    _, body = _post_assess(client)
    assessment_id = body["assessment_id"]

    lookup = client.get(f"/api/assess/{assessment_id}")
    assert lookup.status_code == 200
    assert lookup.json()["assessment_id"] == assessment_id
    assert lookup.json()["status"] == "succeeded"

    evidence = client.get(f"/api/assess/{assessment_id}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["evidence"]["evidence_identity"] == body["evidence"]["evidence_identity"]

    report = client.get(f"/api/assess/{assessment_id}/report")
    assert report.status_code == 200
    assert report.json()["report"]["result_identity"] == assessment_id

    digest = assessment_id.split(":", 1)[1]
    assert client.get(f"/api/assess/{digest}").status_code == 200


def test_download_endpoint_returns_the_exact_canonical_artifact(
    client: TestClient,
) -> None:
    _, body = _post_assess(client)
    assessment_id = body["assessment_id"]
    digest = assessment_id.split(":", 1)[1]
    import yaml

    expected = store.load_yaml(store.result_path(digest))

    response = client.get(f"/api/assess/{assessment_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-yaml")
    disposition = response.headers["content-disposition"]
    assert disposition == f'attachment; filename="{digest}.yaml"'

    downloaded = yaml.safe_load(response.content)
    assert downloaded == expected
    assert downloaded["result_identity"] == assessment_id

    text = response.text
    for _, value in FAKE_KEYS.items():
        assert value not in text


def test_download_endpoint_404_for_unknown_assessment(client: TestClient) -> None:
    assert (
        client.get(
            "/api/assess/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/download"
        ).status_code
        == 404
    )


def test_unknown_or_malformed_assessment_ids_are_404(client: TestClient) -> None:
    assert client.get("/api/assess/nope").status_code == 404
    assert client.get("/api/assess/not a valid digest").status_code == 404
    traversal = "../" * 4 + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert client.get(f"/api/assess/{traversal}").status_code == 404
    assert (
        client.get(
            "/api/assess/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ).status_code
        == 404
    )


def test_invalid_repository_url_rejected(client: TestClient) -> None:
    for bad_url in ("", "not-a-url", "ftp://host/repo.git", "http://", "gh:example/repo"):
        status, body = _post_assess(client, repository_url=bad_url)
        assert status == 400, bad_url
        assert "detail" in body


def test_malformed_commit_rejected(client: TestClient) -> None:
    status, body = _post_assess(client, commit="not-a-sha")
    assert status == 400
    status, body = _post_assess(client, commit="ABC")
    assert status == 400


def test_no_secret_material_leaks(client: TestClient) -> None:
    status, body = _post_assess(client)
    assert status == 201
    digest = body["assessment_id"].split(":", 1)[1]
    responses = [
        body,
        client.get(f"/api/assess/{digest}").json(),
        client.get(f"/api/assess/{digest}/evidence").json(),
        client.get(f"/api/assess/{digest}/report").json(),
    ]
    text = json.dumps(responses)
    for name, value in FAKE_KEYS.items():
        assert name not in text
        assert value not in text
    assert "sk-" not in text


def _staged_response_for(evidence_items: list[dict]) -> str:
    """A valid staged model response over the extracted evidence items.

    Picks one stable citation per rubric criterion and a status the cited item
    can support, so the real cross-check finds no contradictions.
    """
    buckets: dict[str, list[str]] = {
        "FOUND": [],
        "UNCERTAIN": [],
        "NOT_FOUND": [],
        "NOT_APPLICABLE": [],
    }
    for item in evidence_items:
        buckets.setdefault(item["status"], []).append(item["evidence_id"])
    for ids in buckets.values():
        ids.sort()

    citation = (
        buckets["FOUND"]
        or buckets["UNCERTAIN"]
        or buckets["NOT_FOUND"]
        or buckets["NOT_APPLICABLE"]
    )[0]
    if buckets["FOUND"]:
        status, score = "FOUND", 3
    elif buckets["UNCERTAIN"]:
        status, score = "UNCERTAIN", 1
    elif buckets["NOT_FOUND"]:
        status, score = "NOT_FOUND", 0
    else:
        status, score = "NOT_APPLICABLE", None

    rows: list[dict] = []
    for criterion_id in CRITERIA:
        row: dict = {
            "criterion_id": criterion_id,
            "dimension": CRITERIA[criterion_id]["dimension"],
            "status": status,
            "score": score,
            "citations": [citation],
        }
        if status == "UNCERTAIN":
            row["uncertainty_reason"] = "test: cited evidence is marked UNCERTAIN"
        if status == "NOT_APPLICABLE":
            row["justification"] = "test: not applicable to this repository"
        rows.append(row)
    plan = {
        "criteria": [{"criterion_id": cid, "relevant_evidence": [citation]} for cid in CRITERIA]
    }
    return json.dumps({"plan": plan, "criteria": rows, "cross_check": {"findings": []}})


def test_live_assessment_success_via_executor(
    git_repo: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live run over a real local checkout yields a scored assessment.

    The provider is the framework's MockProvider fed a staged response derived
    from the actually-extracted evidence, so the only stage exercised outside
    the real snapshot/evidence path is the model call itself.
    """
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    url = str(git_repo["path"]).replace("\\", "/")
    commit = str(git_repo["first"])

    failed = executor.run_assessment(
        repository_url=url,
        commit=commit,
        mode="live",
        provider=MockProvider(response_text="", input_tokens=0, output_tokens=0),
    )
    assert failed.result["status"] == "failed"
    assert failed.evidence["verified_commit"] == commit

    provider = MockProvider(
        response_text=_staged_response_for(failed.evidence["items"]),
        input_tokens=8,
        output_tokens=4,
    )
    outcome = executor.run_assessment(
        repository_url=url, commit=commit, mode="live", provider=provider
    )
    assert outcome.result["status"] == "succeeded"
    assert outcome.result["scoring"]["score"] > 0
    assert outcome.result["evidence_identity"] == failed.evidence["evidence_identity"]
    assert outcome.identity
    assert outcome.result["process"]["stages"][-1]["status"] == "ok"


def test_live_assessment_wires_snapshot_and_records_failures(
    git_repo: dict[str, object], client: TestClient, tmp_path: Path
) -> None:
    """Live mode runs real snapshot + extraction and honors fail-closed results.

    The mock provider returns an empty response, so the pipeline must record a
    failed ``malformed_response`` artifact rather than inventing a score; the
    snapshot, evidence, and result artifacts are still persisted and servable.
    """
    url = Path(git_repo["path"]).as_uri()
    commit = str(git_repo["first"])
    response = client.post(
        "/api/assess", json={"repository_url": url, "commit": commit, "mode": "live"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "live"
    assert body["demo"] is False
    assert body["status"] == "failed"
    error = body["result"]["error"]
    assert error is not None
    assert error["kind"] == "malformed_response"

    snapshot_dirs = [p for p in store.snapshots_dir().iterdir() if p.is_dir()]
    assert snapshot_dirs, "live assessment produced no snapshot store"

    evidence = client.get(f"/api/assess/{body['assessment_id']}/evidence")
    assert evidence.status_code == 200
    items = evidence.json()["evidence"]["items"]
    assert items, "live assessment extracted no evidence"
    assert {item["category"] for item in items} == set(DIMENSIONS)

    report = client.get(f"/api/assess/{body['assessment_id']}/report")
    assert report.status_code == 200
    assert report.json()["report"]["result_identity"] == body["assessment_id"]


class _CapturingProvider:
    """Records every LLMRequest and answers with a staged valid success."""

    name = "openai-compatible"

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.requests: list = []

    def generate(self, request):
        self.requests.append(request)
        return LLMResponse(
            text=self._response_text,
            model=request.model,
            input_tokens=4,
            output_tokens=2,
        )

    def public_config(self) -> dict[str, object]:
        return {"mode": self.name}


def _live_url_commit(git_repo: dict[str, object]) -> tuple[str, str]:
    return Path(git_repo["path"]).as_uri(), str(git_repo["first"])


def test_live_uses_configured_env_model_for_the_request(
    git_repo: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The configured environment model must reach the provider request.

    Mirrors the CLI's model resolution: the product executor derives the
    ``EvaluatorConfig.model`` from ``REPOGUARD_LLM_MODEL`` for HTTP providers,
    and ``run_case`` sends it as ``LLMRequest.model``.
    """
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv("REPOGUARD_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("REPOGUARD_LLM_MODEL", "configured-model-42")
    url, commit = _live_url_commit(git_repo)

    failed = executor.run_assessment(
        repository_url=url,
        commit=commit,
        mode="live",
        provider=MockProvider(response_text=""),
    )
    assert failed.result["status"] == "failed"

    capturing = _CapturingProvider(_staged_response_for(failed.evidence["items"]))
    outcome = executor.run_assessment(
        repository_url=url,
        commit=commit,
        mode="live",
        provider=capturing,
    )
    assert outcome.result["status"] == "succeeded"
    assert capturing.requests, "provider.generate was never called"
    assert capturing.requests[0].model == "configured-model-42"
    assert outcome.result["provider"]["model"] == "configured-model-42"

    model_config = outcome.result["provider"]["config"]
    assert model_config["mode"] == "openai-compatible"
    assert model_config["timeout_s"] == 60.0


def test_live_without_configured_provider_is_controlled_error(
    git_repo: dict[str, object], client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset REPOGUARD_LLM_PROVIDER must never imply MockProvider for Live."""
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.delenv("REPOGUARD_LLM_PROVIDER", raising=False)
    url, commit = _live_url_commit(git_repo)

    response = client.post(
        "/api/assess", json={"repository_url": url, "commit": commit, "mode": "live"}
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "provider_unavailable"
    assert "not configured" in detail["message"]

    with pytest.raises(executor.AssessmentInputError) as err_info:
        executor.run_assessment(repository_url=url, commit=commit, mode="live")
    assert err_info.value.code == "provider_unavailable"


def test_unresolvable_repository_is_controlled_error_not_500(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository the remote cannot reach yields a controlled error, no 500."""
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    missing = (tmp_path / "no-such-repository").as_uri()

    response = client.post("/api/assess", json={"repository_url": missing, "mode": "live"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error"] == "repository_unavailable"
    assert "traceback" not in response.text.lower()
    assert str(tmp_path) not in response.text


def test_acquisition_of_a_commit_that_does_not_exist_is_controlled(
    git_repo: dict[str, object], client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid-but-missing commit must classify as user/unavailable, never 500."""
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    url, _ = _live_url_commit(git_repo)
    missing_commit = "0" * 40

    response = client.post(
        "/api/assess",
        json={"repository_url": url, "commit": missing_commit, "mode": "live"},
    )
    assert response.status_code in (400, 502)
    detail = response.json()["detail"]
    assert detail["error"] in ("repository_invalid", "repository_unavailable")
    assert "traceback" not in response.text.lower()


def test_provider_exception_records_failed_result_without_score(
    git_repo: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    url, commit = _live_url_commit(git_repo)
    outcome = executor.run_assessment(
        repository_url=url,
        commit=commit,
        mode="live",
        provider=MockProvider(exc=ProviderError("upstream exploded")),
    )
    assert outcome.result["status"] == "failed"
    assert outcome.result["error"]["kind"] == "provider_error"
    assert outcome.result["scoring"] is None
    assert outcome.result["assessment"] is None


def test_provider_timeout_records_failed_result_without_score(
    git_repo: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider timeout terminates as a recorded failure; never a score."""
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    url, commit = _live_url_commit(git_repo)
    outcome = executor.run_assessment(
        repository_url=url,
        commit=commit,
        mode="live",
        provider=MockProvider(exc=TimeoutError("The read operation timed out")),
    )
    assert outcome.result["status"] == "failed"
    assert outcome.result["error"]["kind"] == "provider_error"
    assert "timed out" in outcome.result["error"]["message"]
    assert outcome.result["scoring"] is None


def test_error_responses_never_leak_credentials(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(store.ENV_DATA_DIR, str(tmp_path / "data"))
    missing = (tmp_path / "no-such-repository").as_uri()
    responses = [
        client.post("/api/assess", json={"repository_url": missing, "mode": "live"}),
        client.post("/api/assess", json={"repository_url": "not-a-url", "mode": "live"}),
    ]
    for response in responses:
        text = response.text
        for name, value in FAKE_KEYS.items():
            assert name not in text
            assert value not in text
        assert "authorization" not in text.lower()
        assert "bearer " not in text.lower()
        assert "sk-" not in text
        assert "traceback" not in text.lower()
