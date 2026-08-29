"""Prompt construction for the RepoGuard staged workflow."""

from __future__ import annotations

import pytest
from repoguard_helpers import evidence_with_statuses
from scoring_helpers import make_evidence

from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard.errors import RepoGuardError
from evaluation.repoguard.prompts import (
    EXPECTED_RUBRIC_VERSION,
    build_prompt,
    render_output,
)
from evaluation.scoring.rubric import CRITERIA, RUBRIC_VERSION


def _prompt(evidence: EvidenceArtifact) -> tuple[str, str]:
    return build_prompt(evidence)


def test_build_prompt_shape() -> None:
    system, user = _prompt(make_evidence())
    assert isinstance(system, str) and system
    assert isinstance(user, str) and user
    assert "OUTPUT" in user


def test_build_prompt_embeds_versions() -> None:
    system, user = _prompt(make_evidence())
    assert "RepoGuard" in system
    assert f"(version {EXPECTED_RUBRIC_VERSION})" in user
    assert f"{EXPECTED_RUBRIC_VERSION}" in user


def test_build_prompt_renders_all_criterion_ids() -> None:
    _, user = _prompt(make_evidence())
    for criterion_id in CRITERIA:
        assert criterion_id in user


def test_build_prompt_renders_evidence_with_observed_markers() -> None:
    _, user = _prompt(make_evidence())
    sample = make_evidence().items[0]
    assert sample.evidence_id in user


def test_build_prompt_marks_non_found_evidence() -> None:
    missing = "testing.integration_e2e_indicators"
    evidence = evidence_with_statuses({missing: "NOT_FOUND"})
    _, user = _prompt(evidence)
    assert missing in user
    assert "NOT_FOUND" in user


def test_render_output_contains_all_sections() -> None:
    output = render_output()
    assert '"plan"' in output
    assert '"criteria"' in output
    assert '"cross_check"' in output
    assert output.count("<{__") == 0


def test_render_output_parses_as_json_template_shapes() -> None:
    output = render_output()
    assert "criterion_id" in output
    assert "relevant_evidence" in output
    assert "citations" in output


def test_prompt_version_guard_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evaluation.repoguard import prompts as prompts_module

    monkeypatch.setattr(prompts_module, "EXPECTED_RUBRIC_VERSION", "9.9")
    with pytest.raises(RepoGuardError):
        build_prompt(make_evidence())


def test_expected_prompt_rubric_version_matches_current_rubric() -> None:
    assert EXPECTED_RUBRIC_VERSION == RUBRIC_VERSION
