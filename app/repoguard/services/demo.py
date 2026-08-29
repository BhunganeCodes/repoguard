"""Deterministic, network-free DEMO assessment for the product interface.

Demo mode runs RepoGuard's real, unmodified pipeline (plan -> assess ->
cross-check -> finalize, including all fail-closed validation and scoring)
against a synthetic evidence artifact, using the framework's
:class:`evaluation.baseline.provider.MockProvider` instead of any network
provider. There is no repository snapshot in demo mode: evidence and the
model response are both synthetic and deterministic.

The result is a genuine RepoGuard artifact carrying a valid content identity,
but it is always explicitly labeled DEMO and must never be presented as a
real repository assessment.

Nothing here is ever part of the evaluation dataset, ground truth, or
benchmark results.
"""

from __future__ import annotations

import json
from typing import Any

from evaluation.baseline.provider import MockProvider
from evaluation.evidence.models import EvidenceArtifact, EvidenceItem
from evaluation.evidence.serialize import content_identity
from evaluation.scoring.rubric import CRITERIA, criterion_dimension

DEMO_CASE_ID = "DEMO001"
DEMO_NAME = "demo-synthetic-repo"
DEMO_EXTRACTION_VERSION = "demo-v1"
DEMO_SNAPSHOT_HASH = "demo-snapshot-content-hash"
DEMO_GENERATED_AT = "2026-08-29T00:00:00Z"
DEMO_EXTRACTOR = "demo"
DEMO_EXTRACTOR_VERSION = "1"

# status, score per canonical criterion id (rubric 1.0, 25 criteria).
# Scores respect the rubric's per-status bounds: FOUND 0-4, UNCERTAIN 0-2,
# NOT_FOUND 0, NOT_APPLICABLE carries no score.
_DEMO_ROWS: dict[str, tuple[str, int | None]] = {
    "architecture.project_organization": ("FOUND", 4),
    "architecture.separation_of_responsibilities": ("FOUND", 3),
    "architecture.dependency_direction": ("FOUND", 3),
    "architecture.coupling_and_complexity": ("FOUND", 2),
    "architecture.extensibility": ("FOUND", 3),
    "testing.test_presence": ("FOUND", 4),
    "testing.test_organization": ("FOUND", 3),
    "testing.unit_testing": ("FOUND", 3),
    "testing.integration_testing": ("FOUND", 2),
    "testing.failure_path_coverage": ("NOT_FOUND", 0),
    "maintainability.code_readability": ("FOUND", 3),
    "maintainability.complexity": ("FOUND", 2),
    "maintainability.duplication": ("FOUND", 3),
    "maintainability.error_handling": ("FOUND", 2),
    "maintainability.technical_debt": ("UNCERTAIN", 1),
    "dependencies.dependency_hygiene": ("FOUND", 3),
    "dependencies.version_management": ("FOUND", 4),
    "dependencies.dependency_necessity": ("FOUND", 2),
    "dependencies.vulnerability_risk_awareness": ("FOUND", 3),
    "dependencies.supply_chain_discipline": ("UNCERTAIN", 1),
    "documentation.readme": ("FOUND", 4),
    "documentation.installation_and_execution": ("FOUND", 3),
    "documentation.architecture_documentation": ("FOUND", 3),
    "documentation.api_interface_documentation": ("NOT_FOUND", 0),
    "documentation.developer_documentation": ("FOUND", 2),
}


def _evidence_id(criterion_id: str) -> str:
    """Synthetic evidence id for one criterion (never a real extraction)."""
    return f"{criterion_id}_demo"


def build_demo_evidence(
    *,
    repository_url: str,
    requested_commit: str,
    verified_commit: str,
) -> EvidenceArtifact:
    """Synthetic, structurally valid evidence artifact (deterministic)."""
    items: list[EvidenceItem] = []
    for index, (criterion_id, (status, _score)) in enumerate(_DEMO_ROWS.items()):
        dimension = criterion_dimension(criterion_id)
        items.append(
            EvidenceItem(
                evidence_id=_evidence_id(criterion_id),
                case_id=DEMO_CASE_ID,
                category=dimension,
                evidence_type="demo_evidence",
                status=status,
                observation=(
                    f"Demo observation for the '{CRITERIA[criterion_id]['name']}' criterion."
                ),
                source_paths=[f"demo/{dimension}/{index}.txt"] if status == "FOUND" else [],
                extractor=DEMO_EXTRACTOR,
                extractor_version=DEMO_EXTRACTOR_VERSION,
            )
        )
    artifact = EvidenceArtifact(
        schema_version=1,
        case_id=DEMO_CASE_ID,
        name=DEMO_NAME,
        repository_url=repository_url,
        requested_commit=requested_commit,
        verified_commit=verified_commit,
        snapshot_content_hash=DEMO_SNAPSHOT_HASH,
        extraction_version=DEMO_EXTRACTION_VERSION,
        evidence_identity="",
        generated_at=DEMO_GENERATED_AT,
        items=items,
    )
    artifact.evidence_identity = content_identity(artifact)
    return artifact


def build_demo_criteria() -> list[dict[str, Any]]:
    """One canonical criterion row per rubric criterion (all 25)."""
    rows: list[dict[str, Any]] = []
    for criterion_id, (status, score) in _DEMO_ROWS.items():
        row: dict[str, Any] = {
            "criterion_id": criterion_id,
            "dimension": criterion_dimension(criterion_id),
            "status": status,
            "score": score,
            "citations": [_evidence_id(criterion_id)],
        }
        if status == "UNCERTAIN":
            row["uncertainty_reason"] = "demo: supporting evidence is marked UNCERTAIN by design"
        if status == "NOT_APPLICABLE":
            row["justification"] = "demo: criterion does not apply to the synthetic repository"
        rows.append(row)
    return rows


def build_demo_plan() -> list[dict[str, Any]]:
    """Model PLAN section: every criterion citing its synthetic evidence."""
    return [
        {"criterion_id": criterion_id, "relevant_evidence": [_evidence_id(criterion_id)]}
        for criterion_id in _DEMO_ROWS
    ]


def build_demo_response_text() -> str:
    """The staged model response (plan, criteria, cross-check) as JSON."""
    staged: dict[str, Any] = {
        "plan": {"criteria": build_demo_plan()},
        "criteria": build_demo_criteria(),
        "cross_check": {"findings": []},
    }
    return json.dumps(staged)


def build_demo_provider() -> MockProvider:
    """A deterministic mock provider that returns the staged demo response."""
    return MockProvider(
        response_text=build_demo_response_text(),
        input_tokens=950,
        output_tokens=240,
        estimated_cost=0.0,
        metadata={"mode": "demo", "deterministic": True},
    )
