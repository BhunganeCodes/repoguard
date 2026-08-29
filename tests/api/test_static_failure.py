"""Structural tests for the human-readable failure experience (Issue #23).

Verify, without a browser, that provider/repository failures are mapped to
human-readable primary messages, raw evaluation failure strings never appear
as the primary text, a genuine "Try Demo" action is offered for provider
failures, technical details stay available in a collapsed surface, the
progress card explains Live can take minutes, and a failed result never
renders a score.
"""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "repoguard" / "static"

INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
STYLES_CSS = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")


def _segment(start: str, end: str) -> str:
    return APP_JS.split(start, 1)[1].split(end, 1)[0]


def test_human_readable_primary_copy_is_present() -> None:
    assert "Live Assessment isn't configured on this demo." in APP_JS
    assert "The Live Assessment took too long to complete. No score was produced." in APP_JS
    assert (
        "The assessment service could not complete this request. No score was produced." in APP_JS
    )
    assert "RepoGuard couldn't access that repository or commit." in APP_JS
    assert "Check the URL and commit SHA and try again. No score was produced." in APP_JS


def test_failure_classification_maps_codes_to_categories() -> None:
    assert "function failureCategoryForCode" in APP_JS
    assert '"provider_unavailable"' in _segment(
        "function failureCategoryForCode", "function resultFailureCategory"
    )
    assert '"repository_invalid" || code === "repository_unavailable"' in APP_JS
    assert '"snapshot_error" || code === "evidence_error"' in APP_JS


def test_result_failure_maps_evaluation_kinds_and_timeouts() -> None:
    segment = _segment("function resultFailureCategory", "function auditRows")
    assert "provider_timeout" in segment
    assert "/timeout|timed out|timed-out|run out of time/i" in segment
    assert '"malformed_response", "invalid_plan", "invalid_cross_check"' in segment
    assert '"invalid_assessment", "incomplete_assessment", "invalid_evidence"' in segment
    assert "provider_api" in segment


def test_provider_names_are_not_primary_and_are_escaped() -> None:
    specs = _segment("var FAILURE_SPECS", "function failureCategoryForCode")
    assert "provider_error" not in specs
    assert "malformed_response" not in specs
    assert "AcquisitionError" not in specs
    assert "esc(" in APP_JS


def test_technical_details_stay_in_a_collapsed_surface() -> None:
    assert "Technical details" in APP_JS
    assert "function auditRows" in APP_JS
    assert "<details class='tech'>" in APP_JS
    assert "details.tech" in STYLES_CSS


def test_try_demo_action_runs_the_genuine_demo_flow() -> None:
    assert "data-action='try-demo'" in APP_JS
    assert "'try-demo'" in APP_JS
    assert "Try Demo" in APP_JS
    segment = _segment('failureBody.addEventListener("click"', "function renderFailedResult")
    assert "runDemo()" in segment
    assert "function runDemo" in APP_JS
    assert 'modeSelect.value = "demo"' in APP_JS
    assert "form.requestSubmit()" in APP_JS
    assert "DEMO_URL" in APP_JS


def test_repository_failures_omit_the_demo_cta() -> None:
    specs = _segment("var FAILURE_SPECS", "function failureCategoryForCode")
    repository_block = specs.split("repository:", 1)[1].split("network:", 1)[0]
    assert '"reset"' in repository_block
    provider_block = specs.split("provider_api:", 1)[1].split("repository:", 1)[0]
    assert '"demo"' in provider_block


def test_progress_card_explains_live_can_take_minutes() -> None:
    assert 'id="progress-hint"' in INDEX_HTML
    assert "Live assessments can take several minutes" in APP_JS
    assert "progressHint.textContent" in APP_JS
    assert 'payload.mode === "live"' in APP_JS


def test_failed_result_never_renders_a_score() -> None:
    segment = _segment("function renderFailedResult", "function renderReport")
    assert "formatScore" not in segment
    assert "scorecard" not in segment
    assert "evidenceDetails(body)" in segment
    assert "auditDetails(body, result)" in segment
    assert "formatScore" in APP_JS


def test_no_fake_browser_timer_was_reintroduced() -> None:
    assert "setInterval" not in APP_JS
    assert "startLifecycle" not in APP_JS
