# Benchmark Runner

The benchmark runner executes the frozen evaluation dataset through the two
assessors - the baseline evaluator (`docs/baseline.md`) and RepoGuard
(`docs/repoguard.md`) - under identical conditions, so their outputs can be
compared and measured over time as specified in `docs/evaluation.md`
Section 10.

It is an **orchestrator, not an assessor**. It contains no scoring logic, no
rubric logic, no evidence extraction, no ground truth, and no metrics. It
loads the frozen dataset, verifies the locked snapshot and shared evidence
for each case, runs whichever evaluators are enabled, records their composed
results, and never touches human ground truth.

## Data flow

```
frozen dataset (evaluation/datasets/dataset-v1.0.0.yaml)
      |
      v  select cases (confirmed by default; excluded never allowed)
snapshot store (evaluation/datasets/snapshots/)  --verify identity, commit, content hash--
      |
      v  load bound, valid evidence artifact
shared evidence + shared rubric (version locked)
      |
      v  baseline        v  repoguard
   one LLM call      full RepoGuard pipeline
      |                   |
      +-----------+-------+
                  v
   paired result (baseline + repoguard score, delta)  --recorded, never fabricated--
                  v
   immutable run directory + run manifest (run_identity)
```

One case is a single run of a candidate snapshot through each enabled
evaluator using the **same** evidence artifact and the **same** scoring
rubric version. The runner enforces that both systems see the identical
`evidence_identity` (fail closed otherwise) and that both scored results
reference the locked rubric version.

## What the runner does not do

- It does not score anything itself. Scores are only ever read from the
  evaluators' composed result artifacts; a failed evaluator produces a
  recorded failure, never a substitute score.
- It does not fabricate evidence, line numbers, metrics, or test results.
  Every claim is traceable to the verified snapshot and evidence artifact.
- It never reads `evaluation/ground_truth/`. It does not compute accuracy,
  agreement, or any metric (that is Issue #17 and later).
- It does not clone, modify, or inspect repositories; it only verifies and
  consumes already-acquired snapshots (`docs/snapshot-acquisition.md`).
- It never overwrites or deletes a previous run.

## Running a benchmark

```
python -m evaluation.benchmark --help
```

### `run`

```
python -m evaluation.benchmark run \
  --dataset evaluation/datasets/dataset-v1.0.0.yaml \
  --store evaluation/datasets/snapshots \
  --out evaluation/results/benchmark        # default
```

Options:

- `--dataset` path to the frozen dataset manifest.
- `--store` snapshot store root (contains every case's immutable checkout;
  default is the dataset snapshots dir).
- `--out` output area; the run is written under `<out>/<run-id>/`
  (default `evaluation/results/benchmark/`, gitignored).
- `--run-id` a stable id (default `run-<UTC stamp>-<4 hex>`). A collision with
  an existing run directory is an error; runs are immutable.
- `--case CASE_ID` run only this case (repeatable). By default every
  **confirmed** candidate runs. A licence-pending candidate is allowed only
  with an explicit `--case` and prints a warning; an **excluded** candidate
  is always rejected.
- `--evaluator {all,baseline,repoguard}` which systems to run (default
  `all`).
- `--provider` provider name. The default is `mock`, which never uses the
  network. The real provider is `openai-compatible` and is selected only by
  naming it explicitly; an API key in the environment alone never triggers a
  network call. Configuration is read from the same environment variables as
  the evaluators (`.env.example`), and the runner fails closed if required
  configuration is missing.
- `--model`, `--temperature`, `--max-tokens`, `--timeout-s` provider
  settings.

The run prints a YAML summary (run id, run identity, per-case status and
scores) to stdout and per-case diagnostics to stderr. Exit code is `0` when
every selected case succeeded and non-zero when any case failed or the run
could not start.

```
python -m evaluation.benchmark inspect --run evaluation/results/benchmark/run-...
python -m evaluation.benchmark validate --run evaluation/results/benchmark/run-...
```

`inspect` prints the run manifest (and a case record with `--case`).
`validate` re-verifies an entire run directory - structure, identity, and
every result file - and exits non-zero with a problem list if anything was
tampered with or is missing.

## Result isolation

Each run owns one directory that is created fresh and never rewritten:

```
<out>/<run-id>/
  run-manifest.yaml        # full reproduction record + run_identity
  baseline/<case-id>/result.yaml
  repoguard/<case-id>/result.yaml
  cases/<case-id>.yaml     # per-case failure record
```

The run identity is a content hash of the manifest with `run_identity`,
`run_id`, `created_at`, and `environment` excluded, so **identical inputs
produce identical run identities** regardless of when or where the run
happened. Result files reference each other by relative path, so a run
directory can be moved as a whole without breaking validation.

## Manifest

`run-manifest.yaml` records:

- schema/system/benchmark versions and the synthetic run id;
- dataset name, version, status, and `repoguard-dataset-v1` content identity;
- rubric version (shared by both systems);
- the case list and each evidence `evidence_identity`;
- per-evaluator enablement plus baseline/RepoGuard and prompt versions;
- sanitized provider configuration (secrets redacted);
- per-case outcomes: status, baseline/RepoGuard result identity and score,
  relative result path, and recorded failure details;
- `created_at` and environment (informational only - excluded from identity).

## Failure semantics

Failures are recorded, never silently repaired and never converted into
scores:

- Setup failures (missing/unreadable/mismatched snapshot or evidence) are
  recorded per case with a stable kind and the run continues with the next
  case.
- Evaluator failures (e.g. `provider_error`, `malformed_response`) are
  recorded per system with no score. If an evaluator produced a result for a
  case that later failed, that result is still recorded, but the case status
  is `failed`.
- A case is `succeeded` only when every enabled evaluator produced a valid,
  validated result.
- Unexpected exceptions are recorded as `internal_error`.

## Integrity

- Snapshots are re-verified before each case: identity scheme, raw content
  hash over the checkout, case id binding, pinned/verified commit, and
  dataset binding.
- Evidence must be parseable, valid, identity-consistent, bound to the case,
  and must reference the exact snapshot content hash being used.
- Both evaluators must run against the same evidence identity, and both
  results must reference the locked rubric version.
- `validate` re-checks all of the above plus the secret scan: any key whose
  name looks credential-like (`token`, `key`, `secret`, `password`, `auth`,
  `credential`) with a non-empty value is reported as a problem.

## Deliberate scope limits

- The runner writes result **records**; computing agreement, accuracy, or
  other evaluation metrics against ground truth is out of scope (Issue #17).
- The mock provider returns a deterministic, valid-but-synthetic assessment.
  Mock runs are correct for wiring/integrity/determinism checks only; they
  carry no real engineering signal.
- Real provider runs are single-attempt: there is no retry or fallback, so a
  transient provider failure is recorded rather than hidden.