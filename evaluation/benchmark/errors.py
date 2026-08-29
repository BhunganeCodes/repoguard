"""Fail-closed errors for the benchmark runner.

Benchmark failures are structured into case-level records rather than
propagated: a single failing case never corrupts the other cases, and a
failed system evaluation is written as a failed result (never converted into
a score). The errors below are reserved for orchestration problems that
cannot be represented as a case outcome (misconfiguration, an unusable run
output directory).
"""

from __future__ import annotations


class BenchmarkError(Exception):
    """Base error for the benchmark subsystem."""


class BenchmarkConfigError(BenchmarkError):
    """Invalid benchmark configuration (unknown provider, bad evaluator)."""


class BenchmarkDatasetError(BenchmarkError):
    """The dataset manifest cannot be loaded or does not match expectations."""


class BenchmarkArtifactError(BenchmarkError):
    """A snapshot or evidence artifact is missing or fails identity checks.

    ``kind`` is a stable failure word (``snapshot_missing``,
    ``evidence_mismatch``, ...) recorded in the per-case outcome.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class BenchmarkRunError(BenchmarkError):
    """A run cannot be written (existing run id, unusable output directory)."""


class RunExistsError(BenchmarkRunError):
    """The requested run id already has an output directory; runs never overwrite."""
