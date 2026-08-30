"""Validation for ground-truth artifacts (fail closed).

A reviewer assessment, adjudication record, and final consensus artifact are
each validated against the frozen dataset version, the canonical rubric, and
the referenced evidence artifact. Validation never mutates its input and
returns a list of human-readable problems (empty == valid).

Reviewer-specific rules beyond the scoring engine:

* status must be one of the four canonical statuses (``PENDING`` is a
  tool-only state and is rejected in human input)
* the reviewer id must match the pseudonymous pattern
* inspected files must be repository-relative POSIX paths
* unknown top-level fields are rejected so that tiers, ranks, and baseline
  or RepoGuard scores cannot be smuggled into a reviewer assessment
"""

from __future__ import annotations

from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import recompute_identity
from evaluation.evidence.statuses import EVIDENCE_STATUSES
from evaluation.ground_truth._version import (
    ADJUDICATION_SCHEMA_VERSION,
    DATASET_VERSION,
    GROUND_TRUTH_SCHEMA_VERSION,
    REVIEW_SCHEMA_VERSION,
)
from evaluation.ground_truth.schema import (
    DECISIONS_KEYS,
    REVIEW_KEYS,
    REVIEWER_ID,
    _path_problem,
    review_to_assessment,
)
from evaluation.ground_truth.serialize import (
    adjudication_identity,
    ground_truth_identity,
    review_identity,
)
from evaluation.scoring.rubric import CRITERIA, RUBRIC_VERSION
from evaluation.scoring.validate import validate_assessment


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_review(data: Any, evidence: EvidenceArtifact) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["review must be a mapping"]

    if (
        not _is_int(data.get("schema_version"))
        or data.get("schema_version") != REVIEW_SCHEMA_VERSION
    ):
        problems.append(f"missing or unsupported schema_version (expected {REVIEW_SCHEMA_VERSION})")

    hidden = set(data) - set(REVIEW_KEYS)
    for key in sorted(hidden):
        problems.append(f"unexpected field {key!r}")

    reviewer_id = data.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        problems.append("missing reviewer_id")
    elif not REVIEWER_ID.match(reviewer_id):
        problems.append(f"reviewer_id must be a pseudonymous identifier, got {reviewer_id!r}")

    if not isinstance(data.get("case_id"), str) or not data["case_id"]:
        problems.append("missing case_id")

    dataset_version = data.get("dataset_version")
    if dataset_version != DATASET_VERSION:
        problems.append(
            f"review records dataset version {dataset_version!r}; expected {DATASET_VERSION!r}"
        )

    rubric_version = data.get("rubric_version")
    if rubric_version != RUBRIC_VERSION:
        problems.append(
            f"unsupported rubric version {rubric_version!r}; engine implements {RUBRIC_VERSION!r}"
        )

    recorded_identity = data.get("evidence_identity")
    if not isinstance(recorded_identity, str) or not recorded_identity:
        problems.append("missing evidence_identity")
    else:
        expected = recompute_identity(evidence)
        if recorded_identity != expected:
            problems.append("evidence identity does not match the provided evidence artifact")

    recorded_review_identity = data.get("review_identity")
    if recorded_review_identity is not None:
        if not isinstance(recorded_review_identity, str):
            problems.append("review_identity must be a string")
        elif recorded_review_identity != review_identity(data):
            problems.append("review_identity does not match recomputed content")

    inspected = data.get("inspected_files")
    if not isinstance(inspected, list):
        problems.append("missing inspected_files list")
    else:
        for path in inspected:
            if not isinstance(path, str):
                problems.append(f"inspected file entry is not a string: {path!r}")
                continue
            problem = _path_problem(path)
            if problem:
                problems.append(problem)

    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        problems.append("missing criteria list")
    else:
        for index, row in enumerate(criteria):
            if not isinstance(row, dict):
                problems.append(f"criteria[{index}]: criterion is not a mapping")
                continue
            status = row.get("status")
            if status is not None and status not in EVIDENCE_STATUSES:
                problems.append(
                    f"criteria[{index}] ({row.get('criterion_id')!r}): status {status!r} is not a "
                    "canonical status; expected one of " + ", ".join(sorted(EVIDENCE_STATUSES))
                )

    assessment = review_to_assessment(data)
    problems.extend(validate_assessment(assessment, evidence))
    return problems


def validate_decisions(data: Any) -> list[str]:
    """Structural validation of an adjudicator decisions file."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["decisions must be a mapping"]
    hidden = set(data) - set(DECISIONS_KEYS)
    for key in sorted(hidden):
        problems.append(f"unexpected field {key!r}")
    if not _is_int(data.get("schema_version")) or data.get("schema_version") != 1:
        problems.append("missing or unsupported schema_version (expected 1)")
    if not isinstance(data.get("case_id"), str) or not data["case_id"]:
        problems.append("missing case_id")
    adjudicator_id = data.get("adjudicator_id")
    if not isinstance(adjudicator_id, str) or not adjudicator_id.strip():
        problems.append("missing adjudicator_id")
    elif not REVIEWER_ID.match(adjudicator_id):
        problems.append(f"adjudicator_id must be a pseudonymous identifier, got {adjudicator_id!r}")
    if not isinstance(data.get("contested"), bool):
        problems.append("missing contested flag (expected a boolean)")
    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        problems.append("missing decisions list")
    else:
        for index, row in enumerate(decisions):
            if not isinstance(row, dict):
                problems.append(f"decisions[{index}]: decision is not a mapping")
                continue
            if not isinstance(row.get("criterion_id"), str) or row["criterion_id"] not in CRITERIA:
                problems.append(f"decisions[{index}]: missing or unknown criterion_id")
    return problems


def _missing_required(data: dict[str, Any], allowed: frozenset[str], label: str) -> list[str]:
    return [f"{label}: missing {key!r}" for key in sorted(set(allowed) - set(data))]


def validate_record(data: Any, evidence: EvidenceArtifact) -> list[str]:
    """Structural validation of an adjudication record."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["adjudication record must be a mapping"]
    if (
        not _is_int(data.get("schema_version"))
        or data.get("schema_version") != ADJUDICATION_SCHEMA_VERSION
    ):
        problems.append(
            f"missing or unsupported schema_version (expected {ADJUDICATION_SCHEMA_VERSION})"
        )
    recorded = data.get("adjudication_identity")
    if not isinstance(recorded, str) or not recorded:
        problems.append("missing adjudication_identity")
    elif recorded != adjudication_identity(data):
        problems.append("adjudication_identity does not match recomputed content")
    problems.extend(
        _missing_required(
            data, frozenset({"case_id", "adjudicator_id", "reviewer_ids"}), "adjudication"
        )
    )
    if not isinstance(data.get("contested"), bool):
        problems.append("missing contested flag (expected a boolean)")
    if not isinstance(data.get("contested_criteria"), list):
        problems.append("missing contested_criteria list")
    return problems


def validate_ground_truth(data: Any, evidence: EvidenceArtifact) -> list[str]:
    """Structural and scoring validation of the final consensus artifact."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["ground truth artifact must be a mapping"]
    if (
        not _is_int(data.get("schema_version"))
        or data.get("schema_version") != GROUND_TRUTH_SCHEMA_VERSION
    ):
        problems.append(
            f"missing or unsupported schema_version (expected {GROUND_TRUTH_SCHEMA_VERSION})"
        )
    recorded = data.get("ground_truth_identity")
    if not isinstance(recorded, str) or not recorded:
        problems.append("missing ground_truth_identity")
    elif recorded != ground_truth_identity(data):
        problems.append("ground_truth_identity does not match recomputed content")
    if data.get("dataset_version") != DATASET_VERSION:
        problems.append(f"dataset version mismatch: {data.get('dataset_version')!r}")
    if not isinstance(data.get("case_id"), str) or not data["case_id"]:
        problems.append("missing case_id")
    if data.get("rubric_version") != RUBRIC_VERSION:
        problems.append(f"rubric version mismatch: {data.get('rubric_version')!r}")
    evidence_identity = data.get("evidence_identity")
    if evidence_identity != recompute_identity(evidence):
        problems.append("evidence identity does not match the provided evidence artifact")
    if data.get("status") not in ("consensus", "contested"):
        problems.append(f"invalid status {data.get('status')!r}; expected consensus or contested")
    reviewers = data.get("reviewers")
    if not isinstance(reviewers, dict) or not isinstance(reviewers.get("independent"), list):
        problems.append("missing reviewers.independent list")
    adjudicator = reviewers.get("adjudicator") if isinstance(reviewers, dict) else None
    if adjudicator is not None and not isinstance(adjudicator, str):
        problems.append("reviewers.adjudicator must be a string or null")
    provenance = data.get("provenance")
    if not isinstance(provenance, dict):
        problems.append("missing provenance mapping")
    else:
        for criterion_id in sorted(set(CRITERIA) - set(provenance)):
            problems.append(f"provenance missing criterion {criterion_id!r}")
        for criterion_id, entry in provenance.items():
            if not isinstance(entry, dict):
                problems.append(f"provenance.{criterion_id} must be a mapping")
                continue
            if entry.get("basis") not in ("agreement", "tiebreak", "adjudicated"):
                problems.append(f"provenance.{criterion_id}: invalid basis {entry.get('basis')!r}")
            if not isinstance(entry.get("source"), list) or not entry.get("source"):
                problems.append(f"provenance.{criterion_id}: missing source reviewers")
    assessment = data.get("assessment")
    if not isinstance(assessment, dict):
        problems.append("missing assessment artifact")
    else:
        problems.extend(validate_assessment(assessment, evidence))
    return problems


def collected(problems: list[str], label: str = "problems") -> dict[str, Any]:
    return {label: problems, "valid": not problems}


__all__ = [
    "validate_decisions",
    "validate_ground_truth",
    "validate_record",
    "validate_review",
]
