"""Finding-based secondary metrics.

Docs/evaluation.md 9.2 defines two finding metrics:

- **Critical finding recall.** The fraction of human-flagged critical
  findings (material problems or risks) that the system reports.
- **False-positive rate.** The fraction of system-reported findings that
  are not supported by snapshot evidence.

The current result artifacts do not record a system "findings" list, and the
consensus artifacts do not record a human "critical findings" list, so these
metrics cannot be computed from a benchmark run alone. They are therefore
reported ``pending`` unless the operator supplies the two finding inputs
(``--gt-findings`` and ``--system-findings``) whose structure is operational
here and documented in docs/metrics.md. Both systems are measured by the
same rules; no category of "critical" is invented by the metrics code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from evaluation.metrics.models import (
    STATE_AVAILABLE,
    STATE_PENDING,
    STATE_UNAVAILABLE,
    MetricValue,
)

_GT_FINDINGS_NOTE = (
    "human-flagged critical findings and system-reported findings are not "
    "recorded by current result/consensus artifacts; this metric is pending "
    "an operationally defined input structure"
)


@dataclass(slots=True)
class Finding:
    """One system-reported or human-flagged finding.

    ``citations`` are evidence ids. Matching (recall) and support
    (false-positive rate) both require at least one citation.
    """

    case_id: str
    claim: str
    citations: list[str]
    severity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "claim": self.claim,
            "citations": list(self.citations),
            "severity": self.severity,
        }


def load_findings(path: Path) -> dict[str, list[Finding]]:
    """Load a findings file: ``case_id -> [finding, ...]``.

    A finding is a mapping with ``claim`` and ``citations`` (list of evidence
    ids); ``severity`` is optional and informational only.
    """
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: findings file must be a mapping keyed by case_id")
    loaded: dict[str, list[Finding]] = {}
    for case_id, entries in raw.items():
        if not isinstance(entries, list):
            raise ValueError(f"{path}: findings for {case_id!r} must be a list")
        findings: list[Finding] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{path}: finding for {case_id!r} must be a mapping")
            claim = entry.get("claim")
            citations = entry.get("citations")
            if not isinstance(claim, str) or not claim:
                raise ValueError(f"{path}: finding for {case_id!r} has no claim")
            if not isinstance(citations, list) or not all(
                isinstance(item, str) for item in citations
            ):
                raise ValueError(f"{path}: finding for {case_id!r} has invalid citations")
            severity = entry.get("severity")
            findings.append(
                Finding(
                    case_id=str(case_id),
                    claim=claim,
                    citations=list(citations),
                    severity=severity if isinstance(severity, str) else None,
                )
            )
        loaded[str(case_id)] = findings
    return loaded


def false_positive_rate_system(
    system_findings: dict[str, list[Finding]] | None,
    evidence_by_case: dict[str, set[str]] | None,
) -> MetricValue:
    """False-positive rate for one system, verified per case against that
    case's own evidence set.

    ``None`` findings means no system-reported-findings input was supplied
    (the current result artifacts do not record findings); ``None`` evidence
    indicates the evidence artifacts were not supplied.
    """
    if system_findings is None:
        return MetricValue(
            STATE_PENDING,
            None,
            note="system-reported findings are not recorded by current result "
            "artifacts; this metric is pending an input structure defining findings",
        )
    if evidence_by_case is None:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="snapshot evidence artifacts were not supplied; finding support "
            "cannot be verified",
        )
    reported = [finding for findings in system_findings.values() for finding in findings]
    if not reported:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="no system-reported findings in the input; false-positive rate is undefined",
        )

    def _supported(finding: Finding) -> bool:
        ids = evidence_by_case.get(finding.case_id)
        return bool(finding.citations and ids and all(c in ids for c in finding.citations))

    unsupported = [finding for finding in reported if not _supported(finding)]
    note = f"{len(unsupported)} finding(s) not supported by snapshot evidence"
    return MetricValue(
        STATE_AVAILABLE,
        len(unsupported) / len(reported),
        unit="fraction",
        covered=len(reported),
        note=note,
    )


def _matched(ground_truth: Finding, system: Finding) -> bool:
    """A system finding matches a human-flagged finding when the claimed
    text and the (non-empty) evidence citation set are identical."""
    return (
        ground_truth.case_id == system.case_id
        and ground_truth.claim == system.claim
        and bool(ground_truth.citations)
        and set(ground_truth.citations) == set(system.citations)
    )


def critical_finding_recall(
    ground_truth_findings: dict[str, list[Finding]] | None,
    system_findings: dict[str, list[Finding]] | None,
) -> MetricValue:
    if ground_truth_findings is None or system_findings is None:
        return MetricValue(STATE_PENDING, None, note=_GT_FINDINGS_NOTE)
    flagged = [finding for findings in ground_truth_findings.values() for finding in findings]
    if not flagged:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="no human-flagged critical findings in the input; recall is undefined",
        )
    reported = [finding for findings in system_findings.values() for finding in findings]
    matched = sum(
        1 for ground_truth in flagged if any(_matched(ground_truth, item) for item in reported)
    )
    return MetricValue(
        STATE_AVAILABLE,
        matched / len(flagged),
        unit="fraction",
        covered=len(flagged),
        note=f"{len(flagged) - matched} human-flagged critical finding(s) not reported",
    )


def false_positive_rate(
    system_findings: dict[str, list[Finding]] | None,
    evidence_ids: set[str] | None,
) -> MetricValue:
    if system_findings is None:
        return MetricValue(
            STATE_PENDING,
            None,
            note="system-reported findings are not recorded by current result "
            "artifacts; this metric is pending an input structure defining findings",
        )
    if evidence_ids is None:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="snapshot evidence artifacts were not supplied; finding support "
            "cannot be verified",
        )
    reported = [finding for findings in system_findings.values() for finding in findings]
    if not reported:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="no system-reported findings in the input; false-positive rate is undefined",
        )
    unsupported = [
        finding
        for finding in reported
        if not finding.citations
        or not all(citation in evidence_ids for citation in finding.citations)
    ]
    return MetricValue(
        STATE_AVAILABLE,
        len(unsupported) / len(reported),
        unit="fraction",
        covered=len(reported),
        note=f"{len(unsupported)} finding(s) not supported by snapshot evidence",
    )
