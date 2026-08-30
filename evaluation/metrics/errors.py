"""Fail-closed errors for the metrics subsystem.

Metric computations never invent values: a measurement whose input data is
missing or undefined is represented as an explicit ``pending``/``unavailable``
state in the report. The errors below are reserved for input problems that
make a report impossible to produce at all (missing/unusable run, invalid
ground truth, mismatched inputs).
"""

from __future__ import annotations


class MetricsError(Exception):
    """Base error for the metrics subsystem."""


class MetricsInputError(MetricsError):
    """The benchmark run or ground-truth inputs are unusable (fail closed)."""
