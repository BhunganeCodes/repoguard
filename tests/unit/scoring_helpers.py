"""Synthetic evidence and assessment fixtures for the scoring unit tests.

These helpers build small, structurally valid evidence artifacts and authored
assessments against them. They are fixtures only: they are not scored
repositories, not ground truth, and must never be treated as evaluation
results.
"""

from __future__ import annotations

from typing import Any

from evaluation.evidence.models import EvidenceArtifact, EvidenceItem
from evaluation.evidence.serialize import content_identity
from evaluation.scoring.rubric import CRITERIA, RUBRIC_VERSION

# Default evidence citation per criterion. Every cited evidence id must exist
# in the synthetic evidence artifact built by :func:`make_evidence`.
DEFAULT_CITATION: dict[str, list[str]] = {
    "architecture.project_organization": ["architecture.top_level_structure"],
    "architecture.separation_of_responsibilities": ["architecture.module_boundaries"],
    "architecture.dependency_direction": ["architecture.dependency_direction_markers"],
    "architecture.coupling_and_complexity": ["architecture.module_boundaries"],
    "architecture.extensibility": ["architecture.top_level_structure"],
    "testing.test_presence": ["testing.test_files"],
    "testing.test_organization": ["testing.test_directories"],
    "testing.unit_testing": ["testing.test_files"],
    "testing.integration_testing": ["testing.integration_e2e_indicators"],
    "testing.failure_path_coverage": ["testing.coverage_configuration"],
    "maintainability.code_readability": ["maintainability.formatting_config"],
    "maintainability.complexity": ["maintainability.static_analysis_config"],
    "maintainability.duplication": ["maintainability.code_organization"],
    "maintainability.error_handling": ["maintainability.ci_workflows"],
    "maintainability.technical_debt": ["maintainability.todo_fixme_counts"],
    "dependencies.dependency_hygiene": ["dependencies.dependency_manifests"],
    "dependencies.version_management": ["dependencies.lockfiles"],
    "dependencies.dependency_necessity": ["dependencies.dependency_declarations"],
    "dependencies.vulnerability_risk_awareness": ["dependencies.version_pinning"],
    "dependencies.supply_chain_discipline": ["dependencies.vendored_dependencies"],
    "documentation.readme": ["documentation.readme"],
    "documentation.installation_and_execution": ["documentation.readme"],
    "documentation.architecture_documentation": ["documentation.architecture_docs"],
    "documentation.api_interface_documentation": ["documentation.api_docs_config"],
    "documentation.developer_documentation": ["documentation.contribution_guides"],
}

_ALL_EVIDENCE_IDS = tuple(sorted({cid for lst in DEFAULT_CITATION.values() for cid in lst}))


def make_evidence(case_id: str = "C001") -> EvidenceArtifact:
    """A synthetic, structurally valid evidence artifact."""
    items: list[EvidenceItem] = []
    for index, evidence_id in enumerate(_ALL_EVIDENCE_IDS):
        category = evidence_id.split(".", 1)[0]
        items.append(
            EvidenceItem(
                evidence_id=evidence_id,
                case_id=case_id,
                category=category,
                evidence_type=evidence_id.split(".", 1)[1],
                status="FOUND",
                observation=f"{evidence_id} observed.",
                source_paths=[f"path/{index}.txt"],
                extractor=category,
                extractor_version="1",
            )
        )
    artifact = EvidenceArtifact(
        schema_version=1,
        case_id=case_id,
        name="synthetic",
        repository_url="https://example.com/x.git",
        requested_commit="a",
        verified_commit="b",
        snapshot_content_hash="c",
        extraction_version="v1",
        evidence_identity="",
        generated_at="2026-08-28T00:00:00Z",
        items=items,
    )
    artifact.evidence_identity = content_identity(artifact)
    return artifact


def base_criteria() -> list[dict[str, Any]]:
    """25 FOUND criteria scoring 2 each (earned 50/100 if all applicable)."""
    criteria: list[dict[str, Any]] = []
    for criterion_id in CRITERIA:
        criteria.append(
            {
                "criterion_id": criterion_id,
                "dimension": CRITERIA[criterion_id]["dimension"],
                "status": "FOUND",
                "score": 2,
                "citations": list(DEFAULT_CITATION[criterion_id]),
            }
        )
    return criteria


def make_assessment(
    *,
    case_id: str = "C001",
    criteria: list[dict[str, Any]] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
    evidence: EvidenceArtifact | None = None,
) -> tuple[dict[str, Any], EvidenceArtifact]:
    """An authored assessment plus the evidence artifact it references."""
    if evidence is None:
        evidence = make_evidence(case_id)
    rows = base_criteria() if criteria is None else list(criteria)
    if overrides:
        rows = _apply_overrides(rows, overrides)
    data = {
        "schema_version": 1,
        "case_id": case_id,
        "name": "synthetic",
        "rubric_version": RUBRIC_VERSION,
        "evidence_identity": evidence.evidence_identity,
        "criteria": rows,
    }
    return data, evidence


def _apply_overrides(
    criteria: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in criteria:
        patch = overrides.get(row["criterion_id"])
        merged = dict(row)
        if patch:
            merged.update(patch)
        result.append(merged)
    return result
