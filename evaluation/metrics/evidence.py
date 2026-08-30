"""Evidence-related secondary metrics.

Evidence accuracy (docs/evaluation.md 9.2) is the fraction of system-cited
evidence claims that verify against the recorded snapshot evidence. A claim
*verifies* when the cited evidence id resolves to an item in the case's
evidence artifact (the snapshot-backed evidence set recorded for the case).
Unverifiable citations lower accuracy; they are never silently dropped.

The metric is computable only when the evidence artifacts are supplied as
input (``--evidence-dir``); when they are not, it is reported ``unavailable``
rather than estimated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from evaluation.metrics.models import (
    STATE_AVAILABLE,
    STATE_UNAVAILABLE,
    MetricValue,
    SystemCaseRecord,
)


def collect_citations(records: Sequence[SystemCaseRecord]) -> list[str]:
    """Every unique evidence id cited across the system's cases, sorted."""
    return sorted({citation for record in records for citation in record.citations})


def resolve_citations(citations: Sequence[str], evidence_ids: set[str]) -> dict[str, bool]:
    """Per-citation verification: does the cited id exist in the evidence set?"""
    return {citation: citation in evidence_ids for citation in sorted(set(citations))}


def evidence_accuracy(
    citations: list[str],
    evidence_ids: set[str] | None,
) -> MetricValue:
    if evidence_ids is None:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="snapshot evidence artifacts were not supplied; "
            "verification against the snapshot is not possible",
        )
    if not citations:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="the system recorded no evidence citations for the case",
        )
    verified = sum(1 for citation in citations if citation in evidence_ids)
    return MetricValue(
        STATE_AVAILABLE,
        verified / len(citations),
        unit="fraction",
        covered=len(citations),
        note=f"{len(citations) - verified} unverifiable citation(s) counted as inaccurate",
    )


def system_evidence_accuracy(
    records: Sequence[SystemCaseRecord],
    evidence_by_case: Mapping[str, set[str]] | None,
) -> MetricValue:
    """Evidence accuracy pooled across a system's cases, each citation
    verified against its own case's evidence set.

    Citations in cases whose evidence artifact was not supplied are not
    counted; the number of cases actually verified is disclosed.
    """
    if evidence_by_case is None:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="snapshot evidence artifacts were not supplied; "
            "verification against the snapshot is not possible",
        )
    verified = 0
    total = 0
    covered_cases = 0
    for record in records:
        ids = evidence_by_case.get(record.case_id)
        if ids is None:
            continue
        covered_cases += 1
        for citation in record.citations:
            total += 1
            if citation in ids:
                verified += 1
    if total == 0:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="no system citations could be verified; evidence artifacts "
            "were missing for the cases that produced citations",
        )
    note = f"verified against evidence artifacts for {covered_cases} case(s)"
    if covered_cases != len(records):
        note += f" of {len(records)} succeeded case(s)"
    return MetricValue(
        STATE_AVAILABLE,
        verified / total,
        unit="fraction",
        covered=total,
        note=note,
    )


def evidence_summary(
    records: Sequence[SystemCaseRecord],
    evidence_by_case: Mapping[str, set[str]] | None,
) -> dict[str, Any]:
    """Diagnostic view: per-case citation counts and resolvability.

    This is not a protocol metric; it exists so per-case evidence facts can
    be recorded next to scores in the report.
    """
    rows: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: item.case_id):
        evidence_ids = evidence_by_case.get(record.case_id) if evidence_by_case else None
        resolvable = 0
        if evidence_ids is not None:
            resolvable = sum(1 for citation in record.citations if citation in evidence_ids)
        rows.append(
            {
                "case_id": record.case_id,
                "citations": len(record.citations),
                "resolvable": resolvable,
                "verifiable": evidence_ids is not None,
            }
        )
    return {"cases": rows}
