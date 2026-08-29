"""Evidence extractors for the five rubric dimensions.

Each extractor exposes ``NAME``, ``VERSION``, and
``extract(ExtractionContext) -> list[EvidenceItem]``. Items are purely
mechanical observations; they never score or rank quality.
"""

from __future__ import annotations

from collections.abc import Callable

from evaluation.evidence.extractors import (
    architecture,
    dependencies,
    documentation,
    maintainability,
    testing,
)
from evaluation.evidence.extractors.base import ExtractionContext
from evaluation.evidence.models import EvidenceItem

Extractor = Callable[[ExtractionContext], list[EvidenceItem]]


def registry() -> list[tuple[str, str, str, Extractor]]:
    """Return ``(category, extractor_name, version, extract)`` in canonical order."""
    entries: list[tuple[str, str, str, Extractor]] = []
    for module in (
        architecture,
        dependencies,
        documentation,
        maintainability,
        testing,
    ):
        entries.append((module.NAME, module.NAME, module.VERSION, module.extract))
    return entries
