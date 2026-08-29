"""The ASSESS stage: extract authored criterion rows from the model output.

RepoGuard does not invent an assessment model; it produces the exact authored
assessment shape consumed by ``evaluation.scoring`` (docs/scoring-engine.md,
"CLI usage"). :func:`build_authored` pulls the ``criteria`` section out of a
model response and assembles the authored assessment mapping. Deep
per-criterion validation is left to ``evaluation.scoring.validate`` in the
FINALIZE stage; this module only enforces the structure required to even
attempt that validation.
"""

from __future__ import annotations

from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard.errors import RepoGuardError
from evaluation.scoring._version import ASSESSMENT_SCHEMA_VERSION
from evaluation.scoring.rubric import RUBRIC_VERSION


class AssessmentProblem(RepoGuardError):
    """The model's ASSESS output is structurally unusable."""


def build_authored(assessment_raw: Any, evidence: EvidenceArtifact) -> dict[str, Any]:
    """Assemble the authored assessment mapping from the model's criteria.

    ``assessment_raw`` is the model's ``criteria`` section: a list of rows.
    The authored mapping carries exactly the scoring engine's input fields
    (``schema_version``, ``case_id``, ``name``, ``rubric_version``,
    ``evidence_identity``, ``criteria``). Values are always derived from the
    validated evidence artifact, never copied from unverified model text.
    """
    if not isinstance(assessment_raw, list):
        raise AssessmentProblem("assessment.criteria must be a list")
    if not all(isinstance(row, dict) for row in assessment_raw):
        raise AssessmentProblem("assessment.criteria rows must be mappings")
    return {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "case_id": evidence.case_id,
        "name": evidence.name,
        "rubric_version": RUBRIC_VERSION,
        "evidence_identity": evidence.evidence_identity,
        "criteria": [dict(row) for row in assessment_raw],
    }
