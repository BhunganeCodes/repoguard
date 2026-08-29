"""Synthetic baseline fixtures (mock provider responses).

These are fixtures only: they are not evaluation results, ground truth, or
benchmark scores. The valid response builders hand the mock provider an
authored assessment that the scoring engine accepts, so the pipeline's happy
path is exercised without any LLM or network access (docs/baseline.md,
"Testing").
"""

from __future__ import annotations

import json
from typing import Any

from scoring_helpers import make_assessment

from evaluation.baseline.provider import MockProvider
from evaluation.evidence.models import EvidenceArtifact


def valid_assessment_text(
    evidence: EvidenceArtifact,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> str:
    """JSON text of a structuraily valid authored assessment."""
    data, _ = make_assessment(evidence=evidence, case_id=evidence.case_id, overrides=overrides)
    return json.dumps(data, sort_keys=True)


def mock_valid(evidence: EvidenceArtifact) -> MockProvider:
    """Mock provider whose response is a valid assessment for ``evidence``."""
    return MockProvider(valid_assessment_text(evidence), input_tokens=30, output_tokens=60)
