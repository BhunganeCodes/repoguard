# ADR 0002: Ranking Agreement Statistic

## Status

Accepted

## Context

The evaluation protocol (docs/evaluation.md 9.1) defines the primary
objective as agreement between the system's ranking and the human
ground-truth ranking, but it deliberately defers the exact statistical
implementation (statistic choice, tie handling, confidence treatment,
per-tier breakdown) to the evaluation runner so the choice is made where the
measurement code lives and can itself be evaluated.

The metrics subsystem (`evaluation/metrics/`) is that measurement code. It
must therefore specify and record the statistic, its tie handling, and its
treatment of contested and missing cases.

## Decision

We adopt **Spearman rank correlation** (Pearson correlation of the average
ranks) over the **measurable case set** as the primary metric.

1. **Ranking.** Both the system and the ground truth are ranked by
   normalized score, descending.
2. **Ties.** Equal scores receive the **average of the positions they cover**
   (the `rank = 1, 2.5, 2.5, 4` scheme). This is deterministic: within a
   tie, case ids are listed in ascending order, and tied cases always share
   exactly the same rank on both sides, so the scheme never invents an
   ordering the data does not support.
3. **Measurable set.** The correlation is computed only over the
   intersection of cases with a recorded system score and a valid
   ground-truth consensus score (listwise deletion). Failed, `not_present`,
   and ground-truth-missing cases are excluded and **reported per case with
   a reason**; they are never estimated.
4. **Contested cases.** Cases whose ground-truth status is `contested`
   (docs/ground-truth.md) are excluded from the headline value. The
   contested-inclusive value (`rho_including_contested`) is always computed
   and reported alongside it, so the exclusion decision is visible in the
   data. The operator may instead keep contested cases in the headline via
   the `--contested include` flag, and the report records which policy was
   applied.
5. **Minimum size.** With fewer than 2 measurable cases the statistic is
   undefined and reported `unavailable` with that reason; it is never
   reported as a fabricatable default.

## Alternatives considered

- **Kendall's tau.** Robust to outliers but less interpretable as a
  correlation and harder to report alongside a familiar coefficient; we
  report ties directly so tau's advantage is not needed.
- **Top-*k* agreement (e.g., union of the top half).** Requires choosing a
  cutoff and loses information from the full ordering; the protocol asks for
  agreement over the dataset ranking as a whole.
- **Exact rank, no tie handling (competition ranking).** Would require
  breaking ties arbitrarily, which would invent an ordering and hurt
  reproducibility.
- **Discarding contested cases silently.** Rejected: exclusions must be
  visible and auditable, which is why per-case exclusions and the
  contested-inclusive sensitivity are both reported.

## Consequences

Positive:

- Standard, interpretable statistic taught by every statistics text.
- Tie handling is deterministic and provably same-rank for equal scores.
- The measurable set is explicit; missing and contested data are surfaced,
  not hidden.
- A single decision point (`evaluation/metrics/agreement.py`) that can
  itself be measured and changed under the same evaluation discipline.

Negative:

- Spearman is insensitive to the magnitude of score differences, only their
  order; per-case scores and deltas remain available in the report.
- Contested-case exclusion changes what is measured depending on the
  dataset; the sensitivity value and the recorded policy make the choice
  auditable.