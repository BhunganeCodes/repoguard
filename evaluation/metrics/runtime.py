"""Runtime (compute resources) metrics (docs/evaluation.md 9.2).

Compute resources are the recorded token usage per result artifact
(``runtime.input_tokens`` / ``runtime.output_tokens``); per-case model
latency is reported by ``model_latency`` under assessment time. Missing
fields stay missing and are always disclosed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from evaluation.metrics.models import (
    STATE_AVAILABLE,
    STATE_UNAVAILABLE,
    MetricValue,
    SystemCaseRecord,
)


def _token_metric(
    records: Sequence[SystemCaseRecord],
    kind: str,
    extract: Callable[[SystemCaseRecord], int | None],
) -> MetricValue:
    total = 0
    covered = 0
    missing = 0
    for record in records:
        value = extract(record)
        if value is None:
            missing += 1
            continue
        total += value
        covered += 1
    if covered == 0:
        return MetricValue(STATE_UNAVAILABLE, None, note=f"no case recorded {kind} tokens")
    note = f"recorded {kind} tokens across succeeded cases"
    if missing:
        note += f"; {missing} case(s) recorded no {kind} tokens"
    return MetricValue(
        STATE_AVAILABLE,
        total,
        unit="tokens",
        covered=covered,
        note=note,
    )


def input_tokens(records: Sequence[SystemCaseRecord]) -> MetricValue:
    """Total recorded input tokens (provider-reported)."""
    return _token_metric(records, "input", lambda record: record.input_tokens)


def output_tokens(records: Sequence[SystemCaseRecord]) -> MetricValue:
    """Total recorded output tokens (provider-reported)."""
    return _token_metric(records, "output", lambda record: record.output_tokens)
