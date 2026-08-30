"""Version and identity scheme for the benchmark runner.

The benchmark runner is the orchestration layer (docs/benchmark-runner.md):
it runs the frozen dataset through the baseline and RepoGuard evaluators,
records results in an isolated, reproducible layout, and never computes
final evaluation metrics (Issue #17).
"""

from __future__ import annotations

__version__ = "0.1.0"

# Scheme prefix used when hashing the dataset content identity (bound to
# every run manifest).
DATASET_SCHEME = "repoguard-dataset-v1"

# Scheme prefix used when hashing a run manifest's content identity.
BENCHMARK_SCHEME = "repoguard-benchmark-v1"

# Schema version of the run manifest artifact.
BENCHMARK_SCHEMA_VERSION = 1

# Immutable identifier of the system producing run manifests. Distinct from
# the baseline and RepoGuard system ids (docs/evaluation.md Section 8.1).
SYSTEM_ID = "benchmark"
