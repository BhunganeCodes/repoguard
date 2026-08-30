"""Version and identity schemes for the metrics subsystem.

The metrics subsystem consumes completed benchmark runs and, when present,
human ground-truth consensus artifacts, and computes the primary and
secondary metrics of docs/evaluation.md Section 9 (docs/metrics.md). It is
read-only: it never modifies benchmark results, evidence, the rubric, or
ground truth.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Scheme prefix for a metrics report's content identity.
METRICS_SCHEME = "repoguard-metrics-v1"

# Schema version of the metrics report artifact.
METRICS_SCHEMA_VERSION = 1

# Scheme prefix for an aggregate identity over every ground-truth artifact
# consumed by one report.
GROUND_TRUTH_AGGREGATE_SCHEME = "repoguard-metrics-gt-v1"

# Immutable identifier of the system producing metrics reports.
SYSTEM_ID = "metrics"
