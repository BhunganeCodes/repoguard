"""The CROSS-CHECK stage: deterministic contradiction detection."""

from __future__ import annotations

import pytest
from repoguard_helpers import evidence_with_statuses
from scoring_helpers import make_assessment

from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard.crosscheck import (
    CrossCheckError,
    apply_corrections,
    canonicalize_model_cross_check,
    detect,
)

_NON_FOUND = "testing.integration_e2e_indicators"
_FOUND = "testing.test_files"


def _rows_for(evidence: EvidenceArtifact, overrides: dict[str, dict] | None = None):
    return make_assessment(evidence=evidence, overrides=overrides)[0]["criteria"]


def test_detect_unsupported_claim_forced_to_unsupported_uncertain() -> None:
    evidence = evidence_with_statuses({_NON_FOUND: "NOT_FOUND"})
    rows = _rows_for(
        evidence,
        overrides={
            "testing.integration_testing": {
                "status": "FOUND",
                "score": 3,
                "citations": [_NON_FOUND],
            }
        },
    )
    findings = detect(rows, evidence)
    assert any(f.rule == "unsupported_claim" for f in findings)
    finding = next(f for f in findings if f.rule == "unsupported_claim")
    assert finding.criterion_id == "testing.integration_testing"
    assert finding.resolution["status"] == "UNCERTAIN"
    assert finding.resolution["score"] == 0
    assert finding.resolution["unsupported"] is True


def test_detect_partial_support_capped_at_two() -> None:
    evidence = evidence_with_statuses({_NON_FOUND: "UNCERTAIN"})
    rows = _rows_for(
        evidence,
        overrides={
            "testing.integration_testing": {
                "status": "FOUND",
                "score": 4,
                "citations": [_NON_FOUND, _FOUND],
            }
        },
    )
    findings = detect(rows, evidence)
    finding = next(f for f in findings if f.rule == "partial_evidence_contradiction")
    assert finding.resolution["status"] == "UNCERTAIN"
    assert finding.resolution["score"] == 2


def test_detect_not_found_but_found_evidence() -> None:
    evidence = evidence_with_statuses({_FOUND: "FOUND"})
    rows = _rows_for(
        evidence,
        overrides={
            "testing.unit_testing": {
                "status": "NOT_FOUND",
                "score": 0,
                "citations": [_FOUND],
            }
        },
    )
    findings = detect(rows, evidence)
    finding = next(f for f in findings if f.rule == "not_found_but_found_evidence")
    assert finding.resolution["status"] == "UNCERTAIN"
    assert finding.resolution["score"] == 0


def test_detect_clean_rows_no_findings() -> None:
    evidence = evidence_with_statuses({})
    rows = _rows_for(evidence)
    assert detect(rows, evidence) == []


def test_detect_is_deterministic_and_ordered() -> None:
    evidence = evidence_with_statuses({_NON_FOUND: "NOT_FOUND"})
    rows = _rows_for(
        evidence,
        overrides={
            "testing.integration_testing": {
                "status": "FOUND",
                "score": 3,
                "citations": [_NON_FOUND],
            }
        },
    )
    first = [f.to_dict() for f in detect(rows, evidence)]
    second = [f.to_dict() for f in detect(rows, evidence)]
    assert first == second
    keys = [(f["criterion_id"], f["rule"]) for f in first]
    assert keys == sorted(keys)


def test_apply_corrections_only_ever_downgrades() -> None:
    evidence = evidence_with_statuses({_NON_FOUND: "NOT_FOUND"})
    rows = _rows_for(
        evidence,
        overrides={
            "testing.integration_testing": {
                "status": "FOUND",
                "score": 4,
                "citations": [_NON_FOUND],
            }
        },
    )
    corrected = apply_corrections(rows, detect(rows, evidence))
    row = next(r for r in corrected if r["criterion_id"] == "testing.integration_testing")
    assert row["status"] == "UNCERTAIN"
    assert row["score"] == 0
    assert row["unsupported"] is True
    assert "uncertainty_reason" in row
    uncorrected = next(r for r in corrected if r["criterion_id"] == "testing.test_presence")
    assert uncorrected["status"] == "FOUND"


def test_apply_corrections_never_increases_score() -> None:
    rows = [
        {"criterion_id": "testing.unit_testing", "status": "FOUND", "score": 0},
        {"criterion_id": "testing.test_presence", "status": "FOUND", "score": 2},
    ]
    corrected = apply_corrections(
        rows,
        [
            _finding(
                "testing.unit_testing",
                {"status": "UNCERTAIN", "score": 0, "unsupported": True},
            )
        ],
    )
    assert next(r for r in corrected if r["criterion_id"] == "testing.unit_testing")["score"] == 0


def _finding(criterion_id: str, resolution: dict) -> object:
    from evaluation.repoguard.crosscheck import CrossCheckFinding

    return CrossCheckFinding(
        rule="unsupported_claim",
        criterion_id=criterion_id,
        severity="warning",
        message="forced to UNCERTAIN",
        resolution=resolution,
    )


def test_canonicalize_model_cross_check_empty_when_absent() -> None:
    evidence = evidence_with_statuses({})
    assert canonicalize_model_cross_check(None, evidence) == []
    assert canonicalize_model_cross_check({"findings": None}, evidence) == []


def test_canonicalize_model_cross_check_records_findings() -> None:
    evidence = evidence_with_statuses({})
    canonical = canonicalize_model_cross_check(
        {
            "findings": [
                {
                    "criterion_id": "testing.test_presence",
                    "kind": "uncertainty",
                    "detail": "  ambiguous  ",
                }
            ]
        },
        evidence,
    )
    assert canonical == [
        {"criterion_id": "testing.test_presence", "kind": "uncertainty", "detail": "ambiguous"}
    ]


def test_canonicalize_model_cross_check_rejects_malformed() -> None:
    evidence = evidence_with_statuses({})
    cases = [
        "oops",
        {"findings": "oops"},
        {"findings": ["oops"]},
        {"findings": [{"criterion_id": "no.such.criterion", "kind": "x", "detail": "y"}]},
        {"findings": [{"criterion_id": "testing.test_presence", "kind": "", "detail": "y"}]},
        {"findings": [{"criterion_id": "testing.test_presence", "kind": "x", "detail": ""}]},
    ]
    for case in cases:
        with pytest.raises(CrossCheckError):
            canonicalize_model_cross_check(case, evidence)


def test_canonicalize_is_deterministic() -> None:
    evidence = evidence_with_statuses({})
    raw = {
        "findings": [
            {"criterion_id": "testing.unit_testing", "kind": "min", "detail": "a"},
            {"criterion_id": "testing.test_presence", "kind": "max", "detail": "b"},
        ]
    }
    assert canonicalize_model_cross_check(raw, evidence) == [
        {"criterion_id": "testing.test_presence", "kind": "max", "detail": "b"},
        {"criterion_id": "testing.unit_testing", "kind": "min", "detail": "a"},
    ]
