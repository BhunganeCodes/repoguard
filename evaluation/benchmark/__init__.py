"""Deterministic benchmark runner (orchestration layer).

Runs the frozen dataset through the baseline and RepoGuard evaluators over
identical snapshot evidence and rubric, isolates results per run, and
records an immutable run manifest (docs/benchmark-runner.md). It never
scores, extracts evidence, or produces ground truth itself.
"""

from evaluation.benchmark._version import __version__

__all__ = ["__version__"]
