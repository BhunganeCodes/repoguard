"""Canonical rubric data (docs/scoring-rubric.md, version 1.0).

The scoring engine implements the rubric exactly: five equally weighted
dimensions of 20 points, five criteria of 4 points each, and the aggregate
rule of rubric Section 6. The criterion ID set below is authoritative for
validation; an assessment that references any other ID is rejected.

Criterion IDs are stable ``<dimension>.<criterion>`` slugs derived from the
canonical titles. They are distinct from evidence item IDs and must not be
confused with them (e.g. ``documentation.architecture_documentation`` is a
criterion, while ``documentation.architecture_docs`` is a recorded evidence
item).
"""

from __future__ import annotations

from evaluation.scoring.errors import ScoringError
from evaluation.scoring.statuses import SCORE_BOUNDS

RUBRIC_VERSION = "1.0"

DIMENSIONS: tuple[str, ...] = (
    "architecture",
    "testing",
    "maintainability",
    "dependencies",
    "documentation",
)

CRITERIA_PER_DIMENSION = 5
MAX_CRITERION_SCORE = 4
MAX_DIMENSION_SCORE = 20

# criterion_id -> (dimension, canonical rubric title).
_CRITERION_SPECS: dict[str, tuple[str, str]] = {
    "architecture.project_organization": ("architecture", "Project organization"),
    "architecture.separation_of_responsibilities": (
        "architecture",
        "Separation of responsibilities",
    ),
    "architecture.dependency_direction": ("architecture", "Dependency direction"),
    "architecture.coupling_and_complexity": ("architecture", "Coupling and complexity"),
    "architecture.extensibility": ("architecture", "Extensibility"),
    "testing.test_presence": ("testing", "Test presence"),
    "testing.test_organization": ("testing", "Test organization"),
    "testing.unit_testing": ("testing", "Unit testing"),
    "testing.integration_testing": ("testing", "Integration testing"),
    "testing.failure_path_coverage": ("testing", "Failure-path coverage"),
    "maintainability.code_readability": ("maintainability", "Code readability"),
    "maintainability.complexity": ("maintainability", "Complexity"),
    "maintainability.duplication": ("maintainability", "Duplication"),
    "maintainability.error_handling": ("maintainability", "Error handling"),
    "maintainability.technical_debt": ("maintainability", "Technical debt"),
    "dependencies.dependency_hygiene": ("dependencies", "Dependency hygiene"),
    "dependencies.version_management": ("dependencies", "Version management"),
    "dependencies.dependency_necessity": ("dependencies", "Dependency necessity"),
    "dependencies.vulnerability_risk_awareness": (
        "dependencies",
        "Vulnerability and risk awareness",
    ),
    "dependencies.supply_chain_discipline": ("dependencies", "Supply-chain discipline"),
    "documentation.readme": ("documentation", "README"),
    "documentation.installation_and_execution": (
        "documentation",
        "Installation and execution",
    ),
    "documentation.architecture_documentation": (
        "documentation",
        "Architecture documentation",
    ),
    "documentation.api_interface_documentation": (
        "documentation",
        "API or interface documentation",
    ),
    "documentation.developer_documentation": (
        "documentation",
        "Developer documentation",
    ),
}

# Canonical, presentation-order listing of all 25 criterion IDs (dimension
# order, then rubric anchor order -- the insertion order above).
CRITERIA: dict[str, dict[str, str]] = {
    criterion_id: {
        "dimension": dimension,
        "name": name,
    }
    for criterion_id, (dimension, name) in _CRITERION_SPECS.items()
}

CRITERIA_BY_DIMENSION: dict[str, tuple[str, ...]] = {
    dimension: tuple(
        criterion_id for criterion_id, spec in _CRITERION_SPECS.items() if spec[0] == dimension
    )
    for dimension in DIMENSIONS
}

CRITERION_IDS: tuple[str, ...] = tuple(_CRITERION_SPECS)


def validate_dimension(dimension: str) -> None:
    if dimension not in DIMENSIONS:
        raise ScoringError(
            f"invalid dimension {dimension!r}; expected one of " + ", ".join(DIMENSIONS)
        )


def validate_criterion(criterion_id: str) -> None:
    if criterion_id not in CRITERIA:
        raise ScoringError(f"unknown criterion id {criterion_id!r}")


def criterion_dimension(criterion_id: str) -> str:
    spec = CRITERIA.get(criterion_id)
    if spec is None:
        raise ScoringError(f"unknown criterion id {criterion_id!r}")
    return str(spec["dimension"])


def criterion_name(criterion_id: str) -> str:
    spec = CRITERIA.get(criterion_id)
    if spec is None:
        raise ScoringError(f"unknown criterion id {criterion_id!r}")
    return str(spec["name"])


def score_bounds_for_status(status: str) -> tuple[int, int] | None:
    """Required integer score range for ``status`` on the 0-4 scale.

    ``None`` means the status carries no numeric score.
    """
    return SCORE_BOUNDS.get(status)
