"""Metrics subsystem: primary and secondary evaluation metrics.

Provides reproducible, evidence-backed metrics over completed benchmark runs
(docs/metrics.md). All inputs are consumed read-only; every report carries a
content identity bound to the consumed run (and ground truth) identities.
"""

from __future__ import annotations

from evaluation.metrics._version import (
    GROUND_TRUTH_AGGREGATE_SCHEME,
    METRICS_SCHEMA_VERSION,
    METRICS_SCHEME,
    SYSTEM_ID,
    __version__,
)
from evaluation.metrics.report import (
    ALL_METRIC_NAMES,
    ReportOptions,
    calculate_report,
    compare_report,
)

__all__ = [
    "ALL_METRIC_NAMES",
    "GROUND_TRUTH_AGGREGATE_SCHEME",
    "METRICS_SCHEMA_VERSION",
    "METRICS_SCHEME",
    "ReportOptions",
    "SYSTEM_ID",
    "__version__",
    "calculate_report",
    "compare_report",
]
