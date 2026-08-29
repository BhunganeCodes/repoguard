"""Structural tests for the product scorecard + findings presentation.

Verify, without a browser, that the static UI only presents canonical
backend values: the score and dimension bars come straight from the artifact,
severity is a presentation-only classification derived from the canonical
status field, findings link to real evidence IDs, and failed assessments
never render a score or scorecard.
"""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "repoguard" / "static"

APP_JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
STYLES_CSS = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")


def test_overall_score_comes_from_canonical_summary() -> None:
    assert "renderReport" in APP_JS
    assert "formatScore(summary.score)" in APP_JS
    assert "esc(summary.possible)" in APP_JS
    assert "renderDims(assessment.dimensions)" in APP_JS


def test_frontend_never_recomputes_scores() -> None:
    assert "reduce(" not in APP_JS
    assert ".reduce" not in APP_JS
    assert "accumulator" not in APP_JS
    assert "Math.round" in APP_JS  # bar width only (visual proportion)
    assert APP_JS.count("formatScore(summary.score)") == 1


def test_severity_is_presentation_derived_from_status_only() -> None:
    assert "function severityFor" in APP_JS
    assert 'case "FOUND": return "positive"' in APP_JS
    assert 'case "NOT_FOUND": return "warning"' in APP_JS
    assert 'case "UNCERTAIN": return "warning"' in APP_JS
    assert 'case "NOT_APPLICABLE": return "neutral"' in APP_JS
    assert "sev-critical" not in APP_JS
    assert 'return "critical"' not in APP_JS
    assert ".sev-warning" in STYLES_CSS
    assert ".sev-positive" in STYLES_CSS


def test_findings_link_to_evidence_ids() -> None:
    assert "class='ev-link' href='#evidence-" in APP_JS
    assert "Evidence: " in APP_JS
    assert ".ev-link" in STYLES_CSS
    assert "tr:target" in STYLES_CSS


def test_evidence_rendered_with_anchor_ids() -> None:
    assert "id='evidence-" in APP_JS


def test_failed_assessment_renders_no_scorecard() -> None:
    segment = APP_JS.split("function renderFailedResult", 1)[1].split("function ", 1)[0]
    assert "formatScore" not in segment
    assert "scorecard" not in segment
    assert "evidenceDetails(body)" in segment
    assert "auditDetails(body, result)" in segment


def test_scorecard_styles_present() -> None:
    assert ".scorecard" in STYLES_CSS
    assert ".score-meaning" in STYLES_CSS
    assert ".findings-summary" in STYLES_CSS
    assert ".note-uncertain" in STYLES_CSS
