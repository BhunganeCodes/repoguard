"""The CROSS-CHECK stage: deterministic contradiction detection.

RepoGuard never trusts its own rows until the evidence has been re-checked
against them. This module implements the deterministic cross-check: for each
criterion row it re-reads the cited evidence items and forces any row that
contradicts its own evidence into ``UNCERTAIN`` (the rubric's honesty
mechanism, Section 3.4), rather than silently passing it through.

Two kinds of finding are produced for the audit trail:

* *downgrade findings* (severity ``warning``) - evidence-ground contradictions
  that RepoGuard resolves by forcing the row to ``UNCERTAIN`` with a recorded
  reason and a score that never increases. Application is deterministic and
  drops a row only ever toward ``UNCERTAIN``.
* *model-reported findings* - RepoGuard never acts on these: they are the
  model's own cross-check output, validated structurally and recorded for
  inspection only.

Structural contradictions (nonexistent citations, missing support, invalid
scores) are handled by the scoring engine's fail-closed validation in the
FINALIZE stage; nothing is silently repaired there either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard.errors import RepoGuardError
from evaluation.scoring.rubric import CRITERIA

_NON_FOUND_STATUSES = frozenset({"NOT_FOUND", "UNCERTAIN", "NOT_APPLICABLE"})


class CrossCheckError(RepoGuardError):
    """The model's CROSS-CHECK section is structurally unusable."""


@dataclass(slots=True)
class CrossCheckFinding:
    """One recordable cross-check outcome for a criterion row.

    ``resolution`` is present only for downgrade findings; it is the exact
    change applied to the row (toward ``UNCERTAIN``, never upward).
    """

    rule: str
    criterion_id: str
    severity: str
    message: str
    resolution: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "rule": self.rule,
            "criterion_id": self.criterion_id,
            "severity": self.severity,
            "message": self.message,
        }
        if self.resolution is not None:
            data["resolution"] = dict(self.resolution)
        return data


def _finding(
    rule: str,
    criterion_id: str,
    message: str,
    resolution: dict[str, Any] | None = None,
) -> CrossCheckFinding:
    return CrossCheckFinding(
        rule=rule,
        criterion_id=criterion_id,
        severity="warning",
        message=message,
        resolution=resolution,
    )


def detect(rows: list[dict[str, Any]], evidence: EvidenceArtifact) -> list[CrossCheckFinding]:
    """Evidence-grounded contradiction detection over the authored rows.

    Deterministic: iterates rows in canonical criterion order and emits
    findings in a stable ordering. Never mutates the input rows.
    """
    by_id = {item.evidence_id: item for item in evidence.items}
    findings: list[CrossCheckFinding] = []

    for row in rows:
        criterion_id = row.get("criterion_id")
        status = row.get("status")
        citations = row.get("citations")
        if not isinstance(criterion_id, str) or not isinstance(status, str):
            continue
        if not isinstance(citations, list):
            continue
        cited = [citation for citation in citations if isinstance(citation, str)]
        cited_items = [by_id[citation] for citation in cited if citation in by_id]
        if not cited_items:
            continue

        if status == "FOUND":
            supporting = [item for item in cited_items if item.status == "FOUND"]
            unsupported = [item for item in cited_items if item.status in _NON_FOUND_STATUSES]
            if not supporting:
                unsupported_ids = sorted(item.evidence_id for item in unsupported)
                findings.append(
                    _finding(
                        rule="unsupported_claim",
                        criterion_id=criterion_id,
                        message=(
                            f"criterion is marked FOUND but every cited evidence item has a "
                            f"non-FOUND status; the positive claim is unsupported "
                            f"({', '.join(unsupported_ids)})"
                        ),
                        resolution={
                            "status": "UNCERTAIN",
                            "score": 0,
                            "unsupported": True,
                            "uncertainty_reason": (
                                "cross-check: marked FOUND but all cited evidence has "
                                "non-FOUND status"
                            ),
                        },
                    )
                )
            elif unsupported:
                unsupported_ids = sorted(item.evidence_id for item in unsupported)
                current = row.get("score")
                capped = current if isinstance(current, int) else 0
                capped = min(capped, 2)
                findings.append(
                    _finding(
                        rule="partial_evidence_contradiction",
                        criterion_id=criterion_id,
                        message=(
                            f"criterion is marked FOUND but some cited evidence has a "
                            f"non-FOUND status ({', '.join(unsupported_ids)}); support is only "
                            "partial"
                        ),
                        resolution={
                            "status": "UNCERTAIN",
                            "score": capped,
                            "uncertainty_reason": (
                                "cross-check: support is partial; some cited evidence has "
                                "non-FOUND status"
                            ),
                        },
                    )
                )
        elif status == "NOT_FOUND":
            found_items = [item for item in cited_items if item.status == "FOUND"]
            if found_items:
                found_ids = sorted(item.evidence_id for item in found_items)
                findings.append(
                    _finding(
                        rule="not_found_but_found_evidence",
                        criterion_id=criterion_id,
                        message=(
                            f"criterion is marked NOT_FOUND but cites FOUND evidence "
                            f"({', '.join(found_ids)})"
                        ),
                        resolution={
                            "status": "UNCERTAIN",
                            "score": 0,
                            "uncertainty_reason": (
                                "cross-check: NOT_FOUND claim contradicts the cited FOUND evidence"
                            ),
                        },
                    )
                )

    findings.sort(key=lambda finding: (finding.criterion_id, finding.rule))
    return findings


def apply_corrections(
    rows: list[dict[str, Any]],
    findings: list[CrossCheckFinding],
) -> list[dict[str, Any]]:
    """Apply downgrade resolutions to copies of the rows (deterministic).

    The applied rows are only ever pushed toward ``UNCERTAIN``; a score is
    never increased. Rows without a resolution are returned unchanged.
    """
    resolutions: dict[str, dict[str, Any]] = {}
    for finding in findings:
        if finding.resolution is not None:
            existing = resolutions.setdefault(finding.criterion_id, {})
            existing.update(finding.resolution)
    corrected: list[dict[str, Any]] = []
    for row in rows:
        criterion_id = row.get("criterion_id")
        applied = dict(row)
        if isinstance(criterion_id, str) and criterion_id in resolutions:
            applied.update(resolutions[criterion_id])
        corrected.append(applied)
    return corrected


def canonicalize_model_cross_check(raw: Any, evidence: EvidenceArtifact) -> list[dict[str, Any]]:
    """Validate and canonicalize the model's own CROSS-CHECK section.

    The result is the audited ``model_reported`` list. RepoGuard never acts
    on these findings; it only records them. Structural problems fail closed:
    a response whose cross-check section is malformed is not accepted.
    """
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise CrossCheckError("cross_check section must be a mapping")
    findings = raw.get("findings")
    if findings is None:
        return []
    if not isinstance(findings, list):
        raise CrossCheckError("cross_check.findings must be a list")
    canonical: list[dict[str, Any]] = []
    for index, finding in enumerate(findings):
        prefix = f"cross_check.findings[{index}]"
        if not isinstance(finding, dict):
            raise CrossCheckError(f"{prefix} must be a mapping")
        criterion_id = finding.get("criterion_id")
        if not isinstance(criterion_id, str) or criterion_id not in CRITERIA:
            raise CrossCheckError(f"{prefix} references an unknown criterion id")
        kind = finding.get("kind")
        detail = finding.get("detail")
        if not isinstance(kind, str) or not kind:
            raise CrossCheckError(f"{prefix} missing kind")
        if not isinstance(detail, str) or not detail.strip():
            raise CrossCheckError(f"{prefix} missing detail")
        canonical.append({"criterion_id": criterion_id, "kind": kind, "detail": detail.strip()})
    canonical.sort(key=lambda f: (f["criterion_id"], f["kind"]))
    return canonical
