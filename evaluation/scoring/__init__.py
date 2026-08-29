"""Deterministic rubric scoring over evidence artifacts.

Implements the canonical scoring rubric (docs/scoring-rubric.md, version
1.0): five dimensions, 25 criteria, 0-4 criterion scores, dimension and
overall aggregates, N/A normalization, and one-decimal rounding. The engine
provides the deterministic mechanics and validation framework; it never
invents a score for criteria that require human or LLM judgment.
"""

from evaluation.scoring import cli
from evaluation.scoring._version import __version__
from evaluation.scoring.rubric import RUBRIC_VERSION
from evaluation.scoring.validate import validate_assessment

__all__ = ["__version__", "RUBRIC_VERSION", "cli", "validate_assessment"]
