"""Synthetic fixtures for the RepoGuard unit tests.

These helpers build staged (PLAN / criteria / CROSS-CHECK) model responses
over the same synthetic evidence used by the scoring tests. They are test
fixtures only: never scored repositories, never ground truth, and never
evaluation results.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from scoring_helpers import DEFAULT_CITATION, make_assessment, make_evidence

from evaluation.evidence.models import EvidenceArtifact, EvidenceItem
from evaluation.evidence.serialize import content_identity
from evaluation.repoguard._version import STAGE_ORDER


def plan_rows_for_evidence(evidence: EvidenceArtifact) -> list[dict[str, Any]]:
    """Deterministic 25-row plan citing existing evidence ids."""
    rows: list[dict[str, Any]] = []
    for criterion_id, refs in DEFAULT_CITATION.items():
        existing = [ref for ref in refs if any(item.evidence_id == ref for item in evidence.items)]
        rows.append({"criterion_id": criterion_id, "relevant_evidence": existing})
    return rows


def evidence_with_statuses(statuses: dict[str, str]) -> EvidenceArtifact:
    """Synthetic evidence with specific items forced to a given status."""
    artifact = make_evidence()
    items: list[EvidenceItem] = []
    for item in artifact.items:
        status = statuses.get(item.evidence_id, "FOUND")
        items.append(replace(item, status=status))
    updated: EvidenceArtifact = replace(artifact, items=items)
    updated.evidence_identity = content_identity(updated)
    return updated


def staged_response(
    evidence: EvidenceArtifact,
    *,
    criteria: list[dict[str, Any]] | None = None,
    plan: Any = None,
    cross_check: Any = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> str:
    """A model response JSON string for the staged RepoGuard prompt."""
    if criteria is None:
        criteria = make_assessment(evidence=evidence, overrides=overrides)[0]["criteria"]
    if plan is None:
        plan = {"criteria": plan_rows_for_evidence(evidence)}
    if cross_check is None:
        cross_check = {"findings": []}
    return json.dumps({"plan": plan, "criteria": criteria, "cross_check": cross_check})


def assert_stage_order(process: Any) -> None:
    stages = [trace.get("stage") for trace in process.stages]
    assert stages == list(STAGE_ORDER)
