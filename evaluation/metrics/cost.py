"""Approximate cost metric (docs/evaluation.md 9.2).

Approximate cost is taken strictly from the provider-reported
``runtime.estimated_cost`` recorded per case in the result artifacts. Prices
are never invented, inferred, or looked up: any case without a recorded cost
stays missing (reported in the note), and a run with no recorded cost at all
is ``unavailable``.
"""

from __future__ import annotations

from collections.abc import Sequence

from evaluation.metrics.models import (
    STATE_AVAILABLE,
    STATE_UNAVAILABLE,
    MetricValue,
    SystemCaseRecord,
)


def approximate_cost(records: Sequence[SystemCaseRecord]) -> MetricValue:
    total = 0.0
    covered = 0
    missing = 0
    for record in records:
        if record.estimated_cost is None:
            missing += 1
            continue
        total += float(record.estimated_cost)
        covered += 1
    if covered == 0:
        return MetricValue(
            STATE_UNAVAILABLE,
            None,
            note="no case recorded a provider-reported estimated cost",
        )
    note = "sum of provider-reported estimated_cost; no prices are invented"
    if missing:
        note += f"; {missing} case(s) recorded no cost"
    return MetricValue(
        STATE_AVAILABLE,
        round(total, 6),
        unit="estimated-cost units (provider-reported)",
        covered=covered,
        note=note,
    )
