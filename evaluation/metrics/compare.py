"""Paired system-vs-system comparison.

Compares baseline and RepoGuard per case within one benchmark run: score,
score delta, success/failure, runtime facts, cost, and evidence facts. The
comparison is neutral: both systems are read with identical logic, result
artifacts are never modified, and no ground truth is required.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evaluation.metrics.models import SystemCaseRecord


@dataclass(slots=True)
class PairedCase:
    case_id: str
    baseline: SystemCaseRecord | None
    repoguard: SystemCaseRecord | None

    @property
    def score_delta(self) -> float | None:
        """RepoGuard minus baseline score; defined only when both scored."""
        if self.baseline is None or self.repoguard is None:
            return None
        if self.baseline.score is None or self.repoguard.score is None:
            return None
        return round(self.repoguard.score - self.baseline.score, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "repoguard": self.repoguard.to_dict() if self.repoguard else None,
            "score_delta": self.score_delta,
        }


def pair_cases(
    baseline: Mapping[str, SystemCaseRecord],
    repoguard: Mapping[str, SystemCaseRecord],
    case_ids: Sequence[str],
) -> list[PairedCase]:
    """One paired row per run case, ordered by case id."""
    paired: list[PairedCase] = []
    for case_id in sorted(set(case_ids)):
        paired.append(
            PairedCase(
                case_id=case_id,
                baseline=baseline.get(case_id),
                repoguard=repoguard.get(case_id),
            )
        )
    return paired


def compare_summary(paired: Sequence[PairedCase]) -> dict[str, Any]:
    """Neutral counts and score-delta facts across the paired cases."""
    both_scored = sum(
        1
        for entry in paired
        if entry.baseline is not None
        and entry.baseline.score is not None
        and entry.repoguard is not None
        and entry.repoguard.score is not None
    )
    baseline_only = sum(
        1
        for entry in paired
        if entry.baseline is not None
        and entry.baseline.score is not None
        and (entry.repoguard is None or entry.repoguard.score is None)
    )
    repoguard_only = sum(
        1
        for entry in paired
        if entry.repoguard is not None
        and entry.repoguard.score is not None
        and (entry.baseline is None or entry.baseline.score is None)
    )
    neither_scored = len(paired) - both_scored - baseline_only - repoguard_only

    deltas = [entry.score_delta for entry in paired if entry.score_delta is not None]
    mean_abs_delta = round(sum(abs(d) for d in deltas) / len(deltas), 4) if deltas else None
    max_abs_delta = round(max(abs(d) for d in deltas), 4) if deltas else None

    return {
        "paired_cases": len(paired),
        "both_scored": both_scored,
        "baseline_scored_only": baseline_only,
        "repoguard_scored_only": repoguard_only,
        "neither_scored": neither_scored,
        "score_delta_statistics": {
            "n": len(deltas),
            "mean_abs_delta": mean_abs_delta,
            "max_abs_delta": max_abs_delta,
        },
    }
