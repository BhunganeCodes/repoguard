"""Ranking and agreement primitives: ties, ordering, exclusions, sensitivity."""

from __future__ import annotations

import pytest

from evaluation.metrics import agreement, ranking


def test_rank_scores_descending_with_average_rank_ties() -> None:
    ranked = ranking.rank_scores({"C001": 80, "C002": 60, "C003": 60, "C004": 40})
    by_id = {entry["case_id"]: entry for entry in ranked}
    assert by_id["C001"]["rank"] == 1.0
    assert by_id["C002"]["rank"] == 2.5
    assert by_id["C003"]["rank"] == 2.5
    assert by_id["C004"]["rank"] == 4.0
    # Deterministic ordering within the tie.
    assert ranked[1]["case_id"] == "C002"
    assert ranked[2]["case_id"] == "C003"


def test_rank_scores_is_deterministic() -> None:
    scores = {"A": 70, "B": 90, "C": 70, "D": 70}
    first = ranking.rank_scores(scores)
    second = ranking.rank_scores(dict(reversed(list(scores.items()))))
    assert first == second


def test_spearman_perfect_and_reverse() -> None:
    assert agreement.spearman(
        {"A": 1.0, "B": 2.0, "C": 3.0}, {"A": 1.0, "B": 2.0, "C": 3.0}
    ) == pytest.approx(1.0)
    assert agreement.spearman(
        {"A": 1.0, "B": 2.0, "C": 3.0}, {"A": 3.0, "B": 2.0, "C": 1.0}
    ) == pytest.approx(-1.0)


def test_spearman_requires_at_least_two_cases() -> None:
    assert agreement.spearman({"A": 1.0}, {"A": 2.0}) is None
    assert agreement.spearman({}, {}) is None


def test_agreement_records_exclusions() -> None:
    result = agreement.agreement(
        run_case_ids=["C001", "C002", "C003"],
        system_scores={"C001": 25.0, "C002": 75.0, "C003": 100.0},
        gt_scores={"C001": 25.0},
    )
    assert result["measurable_cases"] == ["C001"]
    reasons = {entry["case_id"]: entry["reason"] for entry in result["excluded"]}
    assert "no ground-truth consensus for the case" in reasons["C002"]
    assert "no ground-truth consensus for the case" in reasons["C003"]


def test_agreement_excludes_failed_system_case() -> None:
    result = agreement.agreement(
        run_case_ids=["C001", "C002"],
        system_scores={"C001": 50.0},
        gt_scores={"C001": 50.0, "C002": 75.0},
    )
    assert result["measurable_cases"] == ["C001"]
    reasons = {entry["case_id"]: entry["reason"] for entry in result["excluded"]}
    assert reasons["C002"] == "system evaluation failed or did not run"


def test_agreement_contested_e2e() -> None:
    """Contested cases excluded from headline; sensitivity includes them."""
    system_scores = {"C001": 25.0, "C002": 75.0, "C003": 100.0}
    gt_scores = {"C001": 25.0, "C002": 25.0, "C003": 100.0}
    excluded = agreement.agreement(
        run_case_ids=["C001", "C002", "C003"],
        system_scores=system_scores,
        gt_scores=gt_scores,
        contested_case_ids=["C002"],
    )
    assert excluded["measurable_cases"] == ["C001", "C003"]
    assert excluded["rho"] == pytest.approx(1.0)
    assert excluded["rho_including_contested"] is not None
    contested_exclusions = {
        entry["reason"] for entry in excluded["excluded"] if entry["case_id"] == "C002"
    }
    assert any("contested case excluded" in reason for reason in contested_exclusions)

    included = agreement.agreement(
        run_case_ids=["C001", "C002", "C003"],
        system_scores=system_scores,
        gt_scores=gt_scores,
        contested_case_ids=["C002"],
        include_contested=True,
    )
    assert included["measurable_cases"] == ["C001", "C002", "C003"]
    assert included["contested_policy"] == "include"
