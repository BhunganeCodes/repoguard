"""Structural tests for the product UI assessment lifecycle.

Verify, without a browser framework, that the static interface exposes an
honest, finite, resettable lifecycle: an aria-live status region, an
indeterminate running card that never pretends backend stages completed, and
a "Run another assessment" reset on both the result and failure surfaces.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "repoguard" / "static"

INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
STYLES_CSS = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")


def test_single_h1_and_assessment_form_not_duplicated() -> None:
    assert len(re.findall(r"<h1[ >]", INDEX_HTML)) == 1
    assert INDEX_HTML.count('id="assess-form"') == 1


def test_aria_live_status_region_announces_lifecycle() -> None:
    assert 'id="sr-status"' in INDEX_HTML
    assert 'role="status"' in INDEX_HTML
    assert 'aria-live="polite"' in INDEX_HTML
    assert 'aria-atomic="true"' in INDEX_HTML
    assert "function announce" in APP_JS


def test_progress_card_is_honest_roadmap() -> None:
    progress = INDEX_HTML.split('id="progress"', 1)[1].split("</section>", 1)[0]
    for phase in ("Repository", "Evidence", "Assessment", "Score"):
        assert f"<li>{phase}</li>" in progress
    assert 'id="progress-repo"' in INDEX_HTML
    assert 'class="spinner"' in progress
    assert "setInterval" not in APP_JS
    assert "startLifecycle" not in APP_JS


def test_result_and_failure_surfaces_offer_reset() -> None:
    assert 'id="result-body"' in INDEX_HTML
    assert 'id="failure-body"' in INDEX_HTML
    assert INDEX_HTML.count("Run another assessment") == 2
    assert 'id="new-assessment-result"' in INDEX_HTML
    assert 'id="new-assessment-failure"' in INDEX_HTML


def test_js_reset_wires_both_surfaces_and_clears_state() -> None:
    assert "function resetAssessment" in APP_JS
    assert APP_JS.count('getElementById("new-assessment-result")') == 1
    assert APP_JS.count('getElementById("new-assessment-failure")') == 1
    assert 'resultBody.innerHTML = ""' in APP_JS
    assert 'failureBody.innerHTML = ""' in APP_JS
    assert "urlInput.focus()" in APP_JS


def test_css_supports_lifecycle_surfaces() -> None:
    assert ".sr-only" in STYLES_CSS
    assert ".spinner" in STYLES_CSS
    assert "@keyframes spin" in STYLES_CSS
    assert "prefers-reduced-motion" in STYLES_CSS
    assert ".result-actions" in STYLES_CSS
    assert "button:focus-visible" in STYLES_CSS
