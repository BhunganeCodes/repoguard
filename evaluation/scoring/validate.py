"""Validation for scoring assessments (fail closed).

The scorer validates an authored assessment against the canonical rubric and
the referenced evidence artifact. It rejects anything it cannot score with
full provenance. Validation never mutates its input and returns a list of
human-readable problems (empty == valid).

Fail-closed conditions (from the scoring engine spec):

* rubric version missing or unsupported
* evidence identity missing or not matching the referenced artifact
* evidence artifact for a different case
* criterion or dimension ID unknown
* integer score outside the status-bounded 0-4 range
* NOT_FOUND carrying a non-zero score
* NOT_APPLICABLE without justification, without supporting evidence, or with
  a score
* UNCERTAIN without a recorded reason, or scored above 2
* citation referencing nonexistent evidence
* duplicate, missing, or unknown criteria
* possible <= 0
* provided aggregates (dimensions, summary, identity) not reconciling
"""

from __future__ import annotations

from collections import Counter
from math import isclose
from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import recompute_identity
from evaluation.scoring._version import ASSESSMENT_SCHEMA_VERSION
from evaluation.scoring.errors import ScoringError
from evaluation.scoring.rubric import CRITERIA, DIMENSIONS, RUBRIC_VERSION, criterion_dimension
from evaluation.scoring.serialize import compose_payload
from evaluation.scoring.statuses import (
    ASSESSMENT_STATUSES,
    NO_SCORE_STATUSES,
    PENDING,
    SCORE_BOUNDS,
    SCOREABLE_STATUSES,
)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_assessment(data: Any, evidence: EvidenceArtifact) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["assessment must be a mapping"]

    if (
        not _is_int(data.get("schema_version"))
        or data.get("schema_version") != ASSESSMENT_SCHEMA_VERSION
    ):
        problems.append(
            f"missing or unsupported schema_version (expected {ASSESSMENT_SCHEMA_VERSION})"
        )

    case_id = data.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        problems.append("missing case_id")

    rubric_version = data.get("rubric_version")
    if not isinstance(rubric_version, str) or not rubric_version:
        problems.append("missing rubric version")
    elif rubric_version != RUBRIC_VERSION:
        problems.append(
            "unsupported rubric version "
            f"{rubric_version!r}; engine implements rubric {RUBRIC_VERSION!r}"
        )

    recorded_identity = data.get("evidence_identity")
    if not isinstance(recorded_identity, str) or not recorded_identity:
        problems.append("missing evidence_identity")
    else:
        expected_identity = recompute_identity(evidence)
        if recorded_identity != expected_identity:
            problems.append("evidence identity does not match the provided evidence artifact")

    if isinstance(case_id, str) and case_id and evidence.case_id != case_id:
        problems.append(
            f"assessment case_id {case_id!r} does not match evidence case_id {evidence.case_id!r}"
        )

    criteria_raw = data.get("criteria")
    if not isinstance(criteria_raw, list):
        problems.append("missing criteria list")
        return problems

    criteria_problems, aggregatable = _validate_criteria(criteria_raw, evidence)
    problems.extend(criteria_problems)

    if not problems and aggregatable:
        not_applicable = sum(
            1
            for row in criteria_raw
            if isinstance(row, dict) and row.get("status") == "NOT_APPLICABLE"
        )
        if 100 - 4 * not_applicable <= 0:
            problems.append("overall possible is not positive; repository is not scoreable")
            return problems
        try:
            _payload, expected_identity = compose_payload(data, evidence)
        except ScoringError as exc:
            problems.append(f"assessment cannot be aggregated: {exc}")
            return problems
        summary = _payload.get("summary")
        if not isinstance(summary, dict) or summary["possible"] <= 0:
            problems.append("overall possible is not positive; repository is not scoreable")
        problems.extend(_reconcile_dimensions(data.get("dimensions"), _payload["dimensions"]))
        problems.extend(_reconcile_summary(data.get("summary"), _payload["summary"]))
        recorded_identity_field = data.get("assessment_identity")
        if recorded_identity_field is not None:
            if not isinstance(recorded_identity_field, str):
                problems.append("assessment_identity must be a string")
            elif recorded_identity_field != expected_identity:
                problems.append("assessment_identity does not match recomputed content")
    return problems


def _validate_criteria(
    criteria_raw: list[Any], evidence: EvidenceArtifact
) -> tuple[list[str], bool]:
    problems: list[str] = []
    aggregatable = True
    seen: list[str] = []
    evidence_ids = {item.evidence_id for item in evidence.items}

    for index, raw in enumerate(criteria_raw):
        prefix = f"criteria[{index}]"
        if not isinstance(raw, dict):
            problems.append(f"{prefix}: criterion is not a mapping")
            aggregatable = False
            continue

        criterion_id = raw.get("criterion_id")
        if not isinstance(criterion_id, str) or not criterion_id:
            problems.append(f"{prefix}: missing criterion_id")
            aggregatable = False
            continue
        seen.append(criterion_id)

        status = raw.get("status")
        if not isinstance(status, str) or not status:
            problems.append(f"{prefix} ({criterion_id}): missing status")
            aggregatable = False
            continue
        if status not in ASSESSMENT_STATUSES:
            problems.append(
                f"{prefix} ({criterion_id}): invalid status {status!r}; expected one of "
                + ", ".join(sorted(ASSESSMENT_STATUSES))
            )
            aggregatable = False
            continue

        dimension = raw.get("dimension")
        if not isinstance(dimension, str) or not dimension:
            problems.append(f"{prefix}: missing dimension")
            aggregatable = False
            continue
        if criterion_id in CRITERIA and dimension != criterion_dimension(criterion_id):
            problems.append(
                f"{prefix}: dimension mismatch for {criterion_id}: recorded {dimension!r}, "
                f"rubric expects {criterion_dimension(criterion_id)!r}"
            )
            aggregatable = False
            continue

        score = raw.get("score")
        if score is not None and not _is_int(score):
            problems.append(f"{prefix}: score must be an integer or null")
            aggregatable = False
            continue

        bounds = SCORE_BOUNDS.get(status)
        if status in SCOREABLE_STATUSES:
            if score is None:
                problems.append(f"{prefix}: missing score for status {status}")
                aggregatable = False
                continue
            assert bounds is not None
            low, high = bounds
            if not low <= score <= high:
                problems.append(
                    f"{prefix}: score {score} outside allowed range {low}-{high} for {status}"
                )
                aggregatable = False
                continue
        elif status in NO_SCORE_STATUSES:
            if score is not None:
                problems.append(f"{prefix}: {status} must not carry a score")
                aggregatable = False
                continue

        justification = raw.get("justification")
        if status == "NOT_APPLICABLE":
            if not isinstance(justification, str) or not justification.strip():
                problems.append(f"{prefix}: NOT_APPLICABLE lacks justification")
        elif justification is not None:
            problems.append(f"{prefix}: justification only valid for NOT_APPLICABLE status")

        uncertainty = raw.get("uncertainty_reason")
        if status == "UNCERTAIN":
            if not isinstance(uncertainty, str) or not uncertainty.strip():
                problems.append(f"{prefix}: UNCERTAIN criterion lacks uncertainty_reason")
        elif uncertainty is not None:
            problems.append(f"{prefix}: uncertainty_reason only valid for UNCERTAIN status")

        unsupported = raw.get("unsupported")
        if unsupported is not None:
            if status != "UNCERTAIN":
                problems.append(f"{prefix}: unsupported only valid for UNCERTAIN status")
            elif not isinstance(unsupported, bool):
                problems.append(f"{prefix}: unsupported must be a boolean")
            elif unsupported and score != 0:
                problems.append(f"{prefix}: unsupported requires an UNCERTAIN score of 0")

        citations = raw.get("citations")
        if not isinstance(citations, list):
            problems.append(f"{prefix}: citations must be a list")
            aggregatable = False
            continue
        for citation in citations:
            if not isinstance(citation, str):
                problems.append(f"{prefix}: citation must be a string")
                aggregatable = False
            elif citation not in evidence_ids:
                problems.append(f"{prefix}: citation references nonexistent evidence: {citation!r}")
        if status != PENDING and not citations:
            problems.append(f"{prefix}: status {status} requires at least one evidence citation")

    unknown = set(seen) - set(CRITERIA)
    for criterion_id in sorted(unknown):
        problems.append(f"unknown criterion id {criterion_id!r}")
    for criterion_id in sorted(set(CRITERIA) - set(seen)):
        problems.append(f"missing required criterion {criterion_id!r}")
    for criterion_id, count in Counter(seen).items():
        if count > 1:
            problems.append(f"duplicate criterion {criterion_id!r}")

    complete_ids = len(seen) == 25 and set(seen) == set(CRITERIA) and len(set(seen)) == len(seen)
    if not complete_ids:
        aggregatable = False
    return problems, aggregatable


def _reconcile_dimensions(provided: Any, expected: list[dict[str, Any]]) -> list[str]:
    if provided is None:
        return []
    problems: list[str] = []
    if not isinstance(provided, list):
        return ["dimensions must be a list"]
    expected_by_dim = {row["dimension"]: row for row in expected}
    seen: set[str] = set()
    for index, row in enumerate(provided):
        prefix = f"dimensions[{index}]"
        if not isinstance(row, dict):
            problems.append(f"{prefix}: not a mapping")
            continue
        dimension = row.get("dimension")
        if not isinstance(dimension, str) or not dimension:
            problems.append(f"{prefix}: missing dimension")
            continue
        if dimension not in DIMENSIONS:
            problems.append(f"{prefix}: unknown dimension {dimension!r}")
            continue
        if dimension in seen:
            problems.append(f"duplicate dimension row {dimension!r}")
            continue
        seen.add(dimension)
        expected_row = expected_by_dim[dimension]
        for key in ("earned", "maximum", "scored"):
            if row.get(key) != expected_row[key]:
                problems.append(
                    f"dimensions[{dimension}].{key} does not reconcile: "
                    f"recorded {row.get(key)!r}, expected {expected_row[key]}"
                )
        if row.get("status_counts") != expected_row.get("status_counts"):
            problems.append(
                f"dimensions[{dimension}].status_counts does not reconcile: "
                "recorded "
                f"{row.get('status_counts')!r}, expected {expected_row.get('status_counts')}"
            )
    for expected_dim in expected_by_dim:
        if expected_dim not in seen:
            problems.append(f"dimensions missing row for {expected_dim!r}")
    return problems


def _reconcile_summary(provided: Any, expected: dict[str, Any]) -> list[str]:
    if provided is None:
        return []
    if not isinstance(provided, dict):
        return ["summary must be a mapping"]
    problems: list[str] = []
    for key, expected_value in expected.items():
        if key not in provided:
            problems.append(f"summary missing {key}")
            continue
        recorded_value = provided[key]
        if isinstance(expected_value, float):
            if (
                not isinstance(recorded_value, (int, float))
                or isinstance(recorded_value, bool)
                or not isclose(float(recorded_value), expected_value, abs_tol=1e-9, rel_tol=1e-9)
            ):
                problems.append(
                    f"summary.{key} does not reconcile: recorded {recorded_value!r}, "
                    f"expected {expected_value}"
                )
        elif recorded_value != expected_value:
            problems.append(
                f"summary.{key} does not reconcile: recorded {recorded_value!r}, "
                f"expected {expected_value}"
            )
    return problems
