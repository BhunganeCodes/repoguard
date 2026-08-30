"""Assessment-time metrics (docs/evaluation.md 9.2).

The protocol distinguishes system wall-clock assessment time from human
review time (recording per Section 6.5). The consumed artifacts record
neither: result artifacts record per-case model ``latency_ms`` (a compute
time, reported under runtime) but no wall-clock span for producing an
assessment, and consensus artifacts do not carry ``review_time_minutes``
(that field lives only in the reviewer review artifacts, which this report
does not consume). Both are therefore reported ``unavailable`` unless the
operator supplies the review-time input.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from evaluation.metrics.models import (
    STATE_AVAILABLE,
    STATE_UNAVAILABLE,
    MetricValue,
    SystemCaseRecord,
)


def system_assessment_time(_records: Sequence[SystemCaseRecord]) -> MetricValue:
    """Wall-clock time the system takes to produce an assessment.

    Result artifacts do not record a wall-clock assessment span, so this is
    always ``unavailable`` from a benchmark run alone.
    """
    return MetricValue(
        STATE_UNAVAILABLE,
        None,
        note="result artifacts record per-case model latency but not a wall-clock "
        "assessment span, so wall-clock assessment time is not recorded",
    )


def model_latency(records: Sequence[SystemCaseRecord]) -> MetricValue:
    """Sum of the per-case recorded model latencies (a compute-time proxy)."""
    total = 0.0
    covered = 0
    missing = 0
    for record in records:
        if record.latency_ms is None:
            missing += 1
            continue
        total += float(record.latency_ms)
        covered += 1
    if covered == 0:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note=f"no cases recorded model latency ({missing} case(s) had none)",
        )
    note = "latency is the recorded per-case model latency; it is not wall-clock assessment time"
    if missing:
        note += f"; {missing} case(s) recorded no latency"
    return MetricValue(
        STATE_AVAILABLE,
        round(total, 3),
        unit="ms",
        covered=covered,
        note=note,
    )


def human_review_time(review_minutes: Mapping[str, float] | None) -> MetricValue:
    """Human review time (Section 6.5), only from an explicit ``--review-times`` input."""
    if review_minutes is None:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="human review time is recorded per reviewer in the review artifacts, "
            "which this report does not consume; supply --review-times to include it",
        )
    covered = 0
    total = 0.0
    for minutes in review_minutes.values():
        covered += 1
        total += float(minutes)
    if covered == 0:
        return MetricValue(STATE_UNAVAILABLE, None, note="no review times supplied")
    return MetricValue(
        STATE_AVAILABLE,
        round(total, 1),
        unit="minutes",
        covered=covered,
        note="aggregate of the review minutes supplied by the operator",
    )
