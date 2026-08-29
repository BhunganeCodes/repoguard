"""The primary metric: agreement between system and ground-truth rankings.

The evaluation protocol defers the exact statistic to the evaluation runner
(docs/evaluation.md 9.1). This module is that decision point; the decision is
recorded in docs/decisions/0002-ranking-agreement.md.

Implementation: Spearman rank correlation (Pearson on the average ranks of
each ranking) over the measurable case set. Both systems and the ground
truth are ranked by normalized score, descending, with ties holding average
rank. Cases with a failed/missing system score or a missing ground-truth
consensus are excluded and reported. Contested cases (ground-truth.md
"contested") are excluded from the headline value per the recorded decision
and are additionally reported through a sensitivity value that includes
them, so the exclusion decision is always visible in the data.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from evaluation.metrics.ranking import rank_map, tie_group_count


def _pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = len(a)
    if n < 2:
        return None
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    centered_a = [value - mean_a for value in a]
    centered_b = [value - mean_b for value in b]
    numerator = sum(x * y for x, y in zip(centered_a, centered_b, strict=True))
    denominator = math.sqrt(sum(x * x for x in centered_a) * sum(y * y for y in centered_b))
    if denominator == 0.0:
        return None
    return numerator / denominator


def spearman(rank_a: Mapping[str, float], rank_b: Mapping[str, float]) -> float | None:
    """Rank correlation over the shared case ids (average ranks supplied)."""
    shared = sorted(set(rank_a) & set(rank_b))
    if len(shared) < 2:
        return None
    return _pearson(
        [rank_a[case_id] for case_id in shared], [rank_b[case_id] for case_id in shared]
    )


def relevant_exclusions(
    run_case_ids: Sequence[str],
    system_scores: Mapping[str, float],
    gt_scores: Mapping[str, float],
) -> list[dict[str, Any]]:
    """One recorded exclusion per case, with the reason (never silent)."""
    exclusions: list[dict[str, Any]] = []
    for case_id in sorted(set(run_case_ids)):
        has_system = case_id in system_scores
        has_ground_truth = case_id in gt_scores
        if has_system and has_ground_truth:
            continue
        if not has_system and has_ground_truth:
            reason = "system evaluation failed or did not run"
        elif has_system and not has_ground_truth:
            reason = "no ground-truth consensus for the case"
        else:
            reason = "no system score and no ground-truth consensus"
        exclusions.append({"case_id": case_id, "reason": reason})
    return exclusions


def agreement(
    *,
    run_case_ids: Sequence[str],
    system_scores: Mapping[str, float],
    gt_scores: Mapping[str, float],
    contested_case_ids: Sequence[str] = (),
    include_contested: bool = False,
) -> dict[str, Any]:
    """The primary-metric measurement for one system against the ground truth.

    ``system_scores``/``gt_scores`` contain only cases with a score (failed
    and missing cases are represented by their absence). Returns a dict with
    ``rho``, ``n``, the measurable set, ties, all exclusions, and the
    contested-inclusive sensitivity value.
    """
    contested = set(contested_case_ids)
    excluded_contested = contestable(
        set(system_scores), set(gt_scores), contested, include=include_contested
    )

    measurable = sorted(set(system_scores) & set(gt_scores) - excluded_contested)
    system_ranks = rank_map(system_scores)
    gt_ranks = rank_map(gt_scores)
    paired = [
        {
            "case_id": case_id,
            "system_score": system_scores[case_id],
            "ground_truth_score": gt_scores[case_id],
            "system_rank": system_ranks[case_id],
            "ground_truth_rank": gt_ranks[case_id],
        }
        for case_id in measurable
    ]

    exclusions = relevant_exclusions(run_case_ids, system_scores, gt_scores)
    if not include_contested:
        for case_id in sorted(excluded_contested):
            exclusions.append(
                {
                    "case_id": case_id,
                    "reason": "contested case excluded from the primary metric (recorded decision)",
                }
            )

    unavailable_reason: str | None
    if len(measurable) < 2:
        rho: float | None = None
        unavailable_reason = "fewer than 2 measurable cases; the statistic is undefined"
    else:
        rho = _pearson(
            [system_ranks[case_id] for case_id in measurable],
            [gt_ranks[case_id] for case_id in measurable],
        )
        unavailable_reason = (
            "correlation is undefined (a ranking is constant)" if rho is None else None
        )

    sensitivity: float | None = None
    sensitivity_n: int | None = None
    if not include_contested:
        inclusive = sorted(set(system_scores) & set(gt_scores))
        if len(inclusive) >= 2:
            sensitivity = _pearson(
                [system_ranks[case_id] for case_id in inclusive],
                [gt_ranks[case_id] for case_id in inclusive],
            )
            sensitivity_n = len(inclusive)

    result: dict[str, Any] = {
        "statistic": "spearman-rank-correlation",
        "tie_method": "average-rank",
        "state": "available" if rho is not None else "unavailable",
        "unavailable_reason": unavailable_reason,
        "rho": rho if rho is not None else None,
        "n": len(measurable),
        "measurable_cases": measurable,
        "system_rank": [pair["case_id"] for pair in paired],
        "ground_truth_rank": [pair["case_id"] for pair in paired],
        "paired": paired,
        "system_tie_groups": tie_group_count(system_scores),
        "ground_truth_tie_groups": tie_group_count(gt_scores),
        "excluded": exclusions,
        "contested_policy": "exclude" if not include_contested else "include",
        "rho_including_contested": sensitivity,
        "n_including_contested": sensitivity_n,
    }
    return result


def contestable(
    system_ids: set[str],
    gt_ids: set[str],
    contested: set[str],
    *,
    include: bool,
) -> set[str]:
    """Contested cases that are measurable on both sides.

    ``include=True`` keeps them in the measurable set; the reported
    exclusion applies only when ``include=False``.
    """
    both = system_ids & gt_ids
    if include:
        return set()
    return both & contested
