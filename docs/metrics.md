# Metrics (Issue #17)

This document specifies the metrics layer implemented in
`evaluation/metrics/`: how a benchmark run is turned into evidence-backed
metrics and system comparisons. It is the operational companion to
`docs/evaluation.md` (Section 9) and to `docs/decisions/0002-ranking-agreement.md`
(which records the chosen primary statistic).

## 1. Scope and honesty boundary

The metrics layer is read-only. It consumes baseline results, RepoGuard
results, snapshot evidence, and ground-truth consensus artifacts, and never
modifies any of them. It is neutral: both systems are measured by identical
logic.

A metric is one of three states:

- `available` — computed from recorded data;
- `pending` — the evaluation protocol does not yet define the input structure
  needed to compute it;
- `unavailable` — the input data this run would require was not recorded.

Missing data is never replaced by an estimate or a default. Input problems
that make a report impossible raise `MetricsInputError` (fail closed) before
anything is computed.

## 2. CLI

```
metrics calculate --run <run-dir> [--ground-truth <file-or-dir>] [options]
metrics compare   --run <run-dir>
metrics inspect   --report <report-file> [--validate]
metrics validate  [--run <run-dir>] [--ground-truth <inputs>] [--report <file>]
```

Exit codes: `0` the requested artifact was produced / inputs valid, `1`
fail-closed input problems, `2` usage problems.

`calculate` options:

- `--contested exclude|include` — contested cases in the headline agreement
  (default `exclude`; the contested-inclusive sensitivity is always reported).
- `--metric <name>` — limit secondary metrics (repeatable; default all).
- `--evidence-dir <dir>` — snapshot evidence store used to verify citations.
- `--gt-findings`, `--baseline-findings`, `--repoguard-findings` — finding
  inputs (see Section 4).
- `--review-times <file>` — per-case human review minutes.

Default output is `evaluation/results/metrics/<label>-report.yaml` (and
`...-compare.yaml`), where `<label>` derives from the run identity.

## 3. Primary metric: ranking agreement

Statistic: Spearman rank correlation over the measurable case set
(ADR 0002). Both the system and the ground truth are ranked by normalized
score, descending; ties share the average covered rank. The measurable set
is the intersection of cases with a recorded system score and a valid
ground-truth consensus score.

Excluded cases (failed/`not_present` system, missing ground truth,
contested) are listed per case with their reason; contested cases are
excluded from the headline value and included in the reported sensitivity
`rho_including_contested`. Fewer than 2 measurable cases is `unavailable`.

Inputs: a validated benchmark run and (optional) ground-truth consensus
artifact(s). Without ground truth the agreement is `unavailable` and the
system ranking is still reported.

## 4. Secondary metrics

All secondary metrics are computed per system with identical rules.

- **Evidence accuracy** (`evidence_accuracy`). Fraction of system-cited
  evidence ids that resolve to an item in the case's snapshot evidence
  artifact. Unverifiable citations lower accuracy; they are never silently
  dropped. `unavailable` when `--evidence-dir` is not supplied.
- **Critical finding recall** (`critical_finding_recall`). Fraction of
  human-flagged critical findings reported by the system. `pending` unless
  `--gt-findings` and `--baseline-`/`--repoguard-findings` are supplied. A
  system finding matches a flagged finding when the claim text and the
  (non-empty) evidence citation set are identical.
- **False-positive rate** (`false_positive_rate`). Fraction of a system's
  reported findings that are not supported by snapshot evidence (a finding
  is supported when every citation resolves for that case). `pending`
  without the findings inputs; `unavailable` without `--evidence-dir`.
- **Assessment time** (`assessment_time`). Wall-clock assessment time is
  `unavailable` from a run alone (result artifacts record per-case model
  latency, not span). Model latency (sum of recorded `runtime.latency_ms`)
  is reported as a compute-time proxy. Human review time is `unavailable`
  unless `--review-times` is supplied.
- **Runtime** (`runtime`). Recorded `input_tokens`/`output_tokens` as
  reported by the provider; a case with none stays missing and is disclosed.
- **Approximate cost** (`cost`). Sum of provider-reported
  `runtime.estimated_cost`; no prices are invented or looked up. A run with
  no recorded cost is `unavailable`.

## 5. Comparison (no ground truth required)

`metrics compare` pairs baseline and RepoGuard per case within one run:
score, score delta, success/failure, runtime, cost, and evidence facts. It
reports paired-case counts (`both_scored`, `baseline_scored_only`,
`repoguard_scored_only`, `neither_scored`) and score-delta statistics
(`mean_abs_delta`, `max_abs_delta`). Deltas are defined only when both
systems scored the case.

## 6. Validation (fail closed)

Before any metric is computed the run must pass the benchmark runner's own
validation (`validate_run`: structure, per-case result identities, dataset,
rubric, evidence bindings). Consumed ground truth must match the run's
dataset version, rubric version, case set, per-case evidence identity, and
its own content identity; ground-truth status must be `consensus` or
`contested` and the score must be within 0–100. Any problem aborts the
computation as a `MetricsInputError`.

## 7. Report identity

A metrics report carries `metrics_identity`: a SHA-256 over the canonical,
key-sorted rendering of every semantic field except `metrics_identity` and
`generated_at`. The same run, ground truth, version, and configuration
always produce the same report; timestamps never enter the identity.

## 8. Assumptions and limitations

- Scores and runtime facts are copied from recorded artifacts only; nothing
  is derived from other cases.
- The primary metric measures order, not score magnitude; per-case scores
  and deltas remain available.
- Findings and review-time metrics depend on operator-supplied inputs whose
  structure is operational here; they stay `pending`/`unavailable`
  otherwise.
- Contested-case handling is a policy decision recorded per report; the
  excluded set and the contested-inclusive sensitivity are always visible.