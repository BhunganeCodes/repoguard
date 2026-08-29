"""Deliberately simple, single-LLM rubric assessment over frozen evidence."""

from evaluation.baseline import cli
from evaluation.baseline._version import __version__

__all__ = ["__version__", "cli"]
