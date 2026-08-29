"""Prompt construction for the baseline evaluator."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from scoring_helpers import make_evidence

from evaluation.baseline.errors import BaselineError
from evaluation.baseline.prompt import (
    EXPECTED_RUBRIC_VERSION,
    PROMPT_VERSION,
    RUBRIC_ANCHORS,
    SYSTEM_PROMPT,
    build_prompt,
    render_evidence,
    render_output,
    render_rubric,
)
from evaluation.scoring import rubric as scoring_rubric

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUBRIC_DOC = _REPO_ROOT / "docs" / "scoring-rubric.md"

_DIM_LABELS = {
    "Architecture": "architecture",
    "Testing": "testing",
    "Maintainability": "maintainability",
    "Dependencies": "dependencies",
    "Documentation": "documentation",
}


def _parse_doc_anchors() -> dict[str, dict[int, str]]:
    """Re-parse docs/scoring-rubric.md Section 5 anchor tables."""
    text = _RUBRIC_DOC.read_text(encoding="utf-8")
    anchors: dict[str, dict[int, str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = re.match(r"^#### (.+?) - (.+)$", line)
        if match:
            dimension = _DIM_LABELS.get(match.group(1))
            title = match.group(2)
            current = None
            if dimension is None:
                continue
            matches = [
                criterion_id
                for criterion_id, spec in scoring_rubric.CRITERIA.items()
                if spec["dimension"] == dimension and spec["name"] == title
            ]
            if len(matches) == 1:
                current = matches[0]
                anchors.setdefault(current, {})
            continue
        row = re.match(r"^\| (\d) \| (.*) \|$", line)
        if row is not None and current is not None:
            anchors[current][int(row.group(1))] = row.group(2).strip()
    return anchors


def _user(evidence) -> str:
    """Just the user prompt, since tests assert on the prompt body."""
    return build_prompt(evidence)[1]


def test_prompt_construction_is_deterministic() -> None:
    evidence = make_evidence()
    first = build_prompt(evidence)
    second = build_prompt(evidence)
    assert first == second
    assert isinstance(first, tuple) and len(first) == 2


def test_prompt_includes_entire_canonical_rubric() -> None:
    evidence = make_evidence()
    user = _user(evidence)
    rendered = render_rubric()
    assert rendered in user
    for criterion_id, spec in scoring_rubric.CRITERIA.items():
        assert criterion_id in user
        assert spec["dimension"] in user
        assert spec["name"] in user
    for dimension in scoring_rubric.DIMENSIONS:
        assert dimension in user


def test_prompt_includes_statuses_and_bounds() -> None:
    evidence = make_evidence()
    user = _user(evidence)
    for status in ("FOUND", "NOT_FOUND", "UNCERTAIN", "NOT_APPLICABLE"):
        assert status in user
    assert "allowed score: 0-4, per the anchors" in user
    assert "allowed score: 0-2; 0 if the positive evidence is entirely unsupported" in user


def test_prompt_includes_every_evidence_item() -> None:
    evidence = make_evidence()
    user = _user(evidence)
    rendered = render_evidence(evidence)
    assert rendered in user
    for item in evidence.items:
        assert item.evidence_id in user
        assert item.observation in user
    assert evidence.case_id in user
    assert evidence.evidence_identity in user


def test_prompt_rules_cover_the_required_constraints() -> None:
    evidence = make_evidence()
    user = _user(evidence)
    for phrase in (
        "Assess ONLY the evidence",
        "Never fabricate evidence",
        "Cite evidence using the evidence IDs",
        "NOT_FOUND (a deliberate search found no evidence)",
        "Use NOT_APPLICABLE only when",
        "on the 0-4 scale",
        "Do not assign repository quality tiers",
        "exact schema",
    ):
        assert phrase in user or phrase in SYSTEM_PROMPT
    for phrase in (
        "Assess ONLY the evidence",
        "Never fabricate",
        "Do not assign repository quality tiers",
        "structured JSON object",
    ):
        assert phrase in SYSTEM_PROMPT


def test_prompt_embeds_no_runtime_metadata() -> None:
    evidence = make_evidence()
    user = _user(evidence)
    assert "generated_at" not in user
    assert "requested_at" not in user
    assert "latency" not in user


def test_anchors_match_canonical_rubric_document() -> None:
    parsed = _parse_doc_anchors()
    assert set(parsed) == set(scoring_rubric.CRITERIA)
    assert parsed == RUBRIC_ANCHORS
    for anchors in RUBRIC_ANCHORS.values():
        assert set(anchors) == {0, 1, 2, 3, 4}


def test_output_section_is_concrete_json_schema() -> None:
    evidence = make_evidence()
    user = _user(evidence)
    output = render_output()
    assert output in user
    assert "schema_version" in output
    assert "criterion_id" in output
    assert "citations" in output
    assert "{__rubric_version__}" not in output


def test_prompt_versions_are_locked() -> None:
    assert PROMPT_VERSION == "1.0"
    assert EXPECTED_RUBRIC_VERSION == scoring_rubric.RUBRIC_VERSION


def test_rubric_version_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = make_evidence()
    monkeypatch.setattr(scoring_rubric, "RUBRIC_VERSION", "2.0")
    with pytest.raises(BaselineError, match="rubric mismatch"):
        build_prompt(evidence)


def test_rubric_render_rejects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scoring_rubric, "RUBRIC_VERSION", "0.9")
    with pytest.raises(BaselineError):
        render_rubric()
