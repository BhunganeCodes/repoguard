"""The ASSESS stage assembly: extracting authored criterion rows."""

from __future__ import annotations

import pytest
from repoguard_helpers import evidence_with_statuses
from scoring_helpers import make_assessment, make_evidence

from evaluation.repoguard.assess import AssessmentProblem, build_authored
from evaluation.scoring._version import ASSESSMENT_SCHEMA_VERSION
from evaluation.scoring.rubric import RUBRIC_VERSION


def test_build_authored_shape() -> None:
    evidence = make_evidence()
    rows, _ = make_assessment(evidence=evidence)
    authored = build_authored(rows["criteria"], evidence)
    assert authored["schema_version"] == ASSESSMENT_SCHEMA_VERSION
    assert authored["case_id"] == evidence.case_id
    assert authored["name"] == evidence.name
    assert authored["rubric_version"] == RUBRIC_VERSION
    assert authored["evidence_identity"] == evidence.evidence_identity
    assert len(authored["criteria"]) == 25


def test_build_authored_rejects_non_list() -> None:
    with pytest.raises(AssessmentProblem):
        build_authored({"criteria": []}, make_evidence())


def test_build_authored_rejects_non_row_mapping() -> None:
    with pytest.raises(AssessmentProblem):
        build_authored([{"criterion_id": "x"}, 42], make_evidence())


def test_build_authored_copies_rows() -> None:
    evidence = make_evidence()
    rows, _ = make_assessment(evidence=evidence)
    authored = build_authored(rows["criteria"], evidence)
    authored["criteria"][0]["score"] = 99
    assert rows["criteria"][0]["score"] != 99


def test_build_authored_accepts_empty_list() -> None:
    authored = build_authored([], make_evidence())
    assert authored["criteria"] == []


def test_build_authored_overrides_identity_nothing() -> None:
    evidence = evidence_with_statuses({"testing.test_files": "NOT_FOUND"})
    rows, _ = make_assessment(evidence=evidence)
    authored = build_authored(rows["criteria"], evidence)
    assert authored["evidence_identity"] == evidence.evidence_identity
