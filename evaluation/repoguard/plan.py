"""The PLAN stage: deterministic evidence relevance planning.

RepoGuard's planning has two layers:

1. A deterministic relevance layer (:func:`build_deterministic_plan`) that
   derives, for each of the 25 criteria, the pool of evidence items that
   could support it (the items whose category matches the criterion's
   dimension) and each pool's status coverage. This is pure code over the
   frozen evidence artifact, so it is reproducible and never trusts the
   model.
2. A validation layer (:func:`plan_from_model`) that consumes the model's
   PLAN section - its own per-criterion list of relevant evidence - and
   verifies it structurally before it is recorded. The model's relevance
   lists are never used to make claims; they are audited context and are
   recorded only after being checked against the evidence artifact.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard.errors import RepoGuardError
from evaluation.scoring.rubric import CRITERIA, criterion_dimension

Coverage = dict[str, int]


class PlanProblem(RepoGuardError):
    """The model's PLAN section is structurally unusable."""


def build_deterministic_plan(evidence: EvidenceArtifact) -> dict[str, dict[str, Any]]:
    """Per-criterion relevance pools derived from the evidence artifact.

    Returns, in canonical criterion order, one mapping per criterion::

        {
          "criterion_id": ...,
          "dimension": ...,
          "evidence_pool": [...evidence ids in the criterion's dimension...],
          "coverage": {"FOUND": n, "NOT_FOUND": n, "UNCERTAIN": n, "NOT_APPLICABLE": n},
        }
    """
    plan: dict[str, dict[str, Any]] = {}
    for criterion_id in CRITERIA:
        dimension = criterion_dimension(criterion_id)
        statuses = Counter(item.status for item in evidence.items if item.category == dimension)
        plan[criterion_id] = {
            "criterion_id": criterion_id,
            "dimension": dimension,
            "evidence_pool": sorted(
                item.evidence_id for item in evidence.items if item.category == dimension
            ),
            "coverage": {
                status: statuses.get(status, 0)
                for status in ("FOUND", "NOT_FOUND", "UNCERTAIN", "NOT_APPLICABLE")
            },
        }
    return plan


def validate_model_plan(raw: Any, evidence: EvidenceArtifact) -> list[str]:
    """Structural validation of the model's PLAN section (fail closed).

    Returns human-readable problems (empty == valid). Nothing here trusts
    the model's judgment; only structure and citation existence are checked.
    """
    problems: list[str] = []
    if not isinstance(raw, dict):
        return ["plan must be a mapping"]
    rows = raw.get("criteria")
    if not isinstance(rows, list):
        return ["plan.criteria must be a list"]
    evidence_ids = {item.evidence_id for item in evidence.items}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"plan.criteria[{index}]"
        if not isinstance(row, dict):
            problems.append(f"{prefix}: not a mapping")
            continue
        criterion_id = row.get("criterion_id")
        if not isinstance(criterion_id, str) or not criterion_id:
            problems.append(f"{prefix}: missing criterion_id")
            continue
        if criterion_id not in CRITERIA:
            problems.append(f"{prefix}: unknown criterion id {criterion_id!r}")
            continue
        if criterion_id in seen:
            problems.append(f"{prefix}: duplicate criterion {criterion_id!r}")
        seen.add(criterion_id)
        relevant = row.get("relevant_evidence")
        if not isinstance(relevant, list):
            problems.append(f"{prefix}: relevant_evidence must be a list")
            continue
        for evidence_id in relevant:
            if not isinstance(evidence_id, str):
                problems.append(f"{prefix}: relevant evidence must be a string")
            elif evidence_id not in evidence_ids:
                problems.append(
                    f"{prefix}: relevant evidence references nonexistent evidence: {evidence_id!r}"
                )
    for criterion_id in sorted(CRITERIA):
        if criterion_id not in seen:
            problems.append(f"plan missing criterion {criterion_id!r}")
    return problems


def plan_from_model(model_plan: Any, evidence: EvidenceArtifact) -> dict[str, list[str]]:
    """Canonical per-criterion relevant-evidence mapping from the model plan.

    Raises :class:`PlanProblem` when the plan is structurally invalid (for
    example a relevant evidence ID that does not exist in the artifact, or a
    missing criterion). On success the mapping is canonical: one entry per
    criterion, evidence IDs de-duplicated and sorted. The returned mapping is
    RepoGuard's audited record of what the model planned; it is recorded as
    context, never as claim support.
    """
    problems = validate_model_plan(raw=model_plan, evidence=evidence)
    if problems:
        raise PlanProblem("invalid model plan: " + "; ".join(problems))
    mapping: dict[str, list[str]] = {}
    for row in model_plan["criteria"]:
        criterion_id = str(row["criterion_id"])
        ids = sorted(set(str(evidence_id) for evidence_id in row.get("relevant_evidence", [])))
        mapping[criterion_id] = ids
    return mapping


def make_plan_record(
    evidence: EvidenceArtifact,
    model_plan: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Compose the canonical plan trace: deterministic pool + model selection."""
    deterministic = build_deterministic_plan(evidence)
    record: list[dict[str, Any]] = []
    for criterion_id in CRITERIA:
        entry = dict(deterministic[criterion_id])
        entry["relevant_evidence"] = list(model_plan.get(criterion_id, []))
        record.append(entry)
    return record
