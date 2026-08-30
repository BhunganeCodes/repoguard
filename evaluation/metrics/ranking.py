"""Deterministic ranking representation.

A ranking is an ordering of case ids by their scores, descending. Ties keep
equal rank: equal scores receive the average of the positions they cover
(the standard ``rank=1, 2.5, 2.5, 4`` scheme), which assigns the same rank
to tied cases and never changes the ground-truth ordering.

The ranking is a pure representation: it records scores, the computed rank,
and, at the call site, the cases that were excluded from it (missing,
failed, or contested). No statistical significance is attached to a ranking
itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def rank_scores(scores: Mapping[str, float]) -> list[dict[str, Any]]:
    """Rank cases by score descending; ties share the average covered rank.

    The result is deterministic: within a tie, case ids are listed in
    ascending order (the shared rank is identical either way).
    """
    ranked: list[dict[str, Any]] = []
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    position = 1
    index = 0
    while index < len(ordered):
        score = ordered[index][1]
        end = index
        while end < len(ordered) and ordered[end][1] == score:
            end += 1
        average_rank = (position + (position + (end - index) - 1)) / 2.0
        for case_id, _ in ordered[index:end]:
            ranked.append({"case_id": case_id, "score": score, "rank": average_rank})
        position += end - index
        index = end
    return ranked


def rank_map(scored: Mapping[str, float]) -> dict[str, float]:
    """case_id -> rank (average rank for ties) for the scores mapping."""
    return {entry["case_id"]: entry["rank"] for entry in rank_scores(scored)}


def tie_group_count(scored: Mapping[str, float]) -> int:
    """Number of distinct score values shared by more than one case (>= 1)."""
    counts: dict[float, int] = {}
    for score in scored.values():
        counts[score] = counts.get(score, 0) + 1
    return sum(1 for _, count in counts.items() if count > 1)


def render_ranking(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic YAML-ready ordering with ranks (documenting ties)."""
    return list(ranked)
