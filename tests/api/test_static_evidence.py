"""Structural tests for the Evidence + Auditability UX (Issue #22).

Verify, without a browser, that the static UI keeps the scorecard primary and
exposes the extracted evidence and the audit trail in collapsible sections that
are collapsed by default. Finding -> evidence navigation must open the evidence
section, scroll, and give the cited row a non-color-only target treatment.
Audit rows only come from canonical artifact fields; nothing secret is rendered.
"""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "repoguard" / "static"

APP_JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
STYLES_CSS = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")


def test_sections_render_as_details_collapsed_by_default() -> None:
    assert "id='evidence-details'" in APP_JS
    assert "id='audit-details'" in APP_JS
    assert "<details class='tech' id='evidence-details'>" in APP_JS
    assert "<details class='tech' id='audit-details'>" in APP_JS
    assert "' open'" not in APP_JS


def test_summaries_label_the_technical_sections() -> None:
    assert "<summary>Evidence <span class='tech-count'>" in APP_JS
    assert "<summary>Audit trail</summary>" in APP_JS
    assert "items</span></summary>" in APP_JS


def test_scorecard_stays_primary_and_evidence_is_secondary() -> None:
    report = APP_JS.split("function renderReport", 1)[1].split("function evidenceDetails", 1)[0]
    assert 'block("Findings", renderFindings(assessment))' in report
    assert "evidenceDetails(data)" in report
    assert "auditDetails(data, result)" in report


def test_evidence_rows_expose_canonical_fields() -> None:
    assert "id='evidence-" in APP_JS
    assert "esc(item.category)" in APP_JS
    assert "esc(item.evidence_id)" in APP_JS
    assert "chipFor(item.status)" in APP_JS
    assert "(item.source_paths || []).join" in APP_JS
    assert "esc(item.observation)" in APP_JS


def test_citation_click_reveals_and_targets_the_evidence_row() -> None:
    assert "function revealEvidence" in APP_JS
    assert 'classList.contains("ev-link")' in APP_JS
    assert "event.preventDefault()" in APP_JS
    assert "details.open = true" in APP_JS
    assert 'row.scrollIntoView({ behavior: "smooth", block: "center" })' in APP_JS
    assert 'row.setAttribute("tabindex", "-1")' in APP_JS
    assert "row.focus()" in APP_JS
    assert "announce(" in APP_JS


def test_evidence_target_is_not_color_only() -> None:
    assert "tr.ev-target" in STYLES_CSS
    assert "tr.ev-target td:first-child { border-left:" in STYLES_CSS
    assert "outline:" in STYLES_CSS
    assert "details.tech summary:focus-visible" in STYLES_CSS


def test_audit_rows_use_only_canonical_metadata() -> None:
    audit = APP_JS.split("function renderAudit", 1)[1].split("function renderStages", 1)[0]
    labels = [
        '"Case ID"',
        '"Repository"',
        '"Commit (requested / verified)"',
        '"Snapshot content hash"',
        '"Evidence"',
        '"Rubric version"',
        '"Assessment identity"',
        '"Result identity"',
        '"Model"',
        '"Requested at"',
    ]
    for label in labels:
        assert label in audit
    assert "rows.push([" in audit
    assert "if (evidence.case_id)" in audit


def test_audit_never_renders_secret_fields() -> None:
    assert "api_key" not in APP_JS
    assert "authorization" not in APP_JS
    assert "sk-" not in APP_JS


def test_workflow_stages_live_inside_the_audit_section() -> None:
    audit_details = APP_JS.split("function auditDetails", 1)[1].split("function revealEvidence", 1)[
        0
    ]
    assert 'block("Assessment workflow", renderStages(result))' in audit_details


def test_download_link_targets_the_canonical_artifact_endpoint() -> None:
    assert "href='/api/assess/" in APP_JS
    assert "esc(data.assessment_id)" in APP_JS
    assert "/download' download>" in APP_JS
    assert "Download assessment artifact (YAML)" in APP_JS
    assert ".download-link" in STYLES_CSS


def test_details_styles_and_download_styles_present() -> None:
    assert "details.tech" in STYLES_CSS
    assert ".tech-count" in STYLES_CSS
    assert ".tech-body" in STYLES_CSS
    assert ".audit-download" in STYLES_CSS
    assert "@media (prefers-reduced-motion: reduce)" in STYLES_CSS
