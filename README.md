# RepoGuard

> Evidence before opinion.

RepoGuard is an **evidence-first software engineering assessment system**. It
does not simply ask an LLM to "review this repository" and print the verdict.
It takes a repository through a pinned, immutable pipeline — snapshot,
evidence extraction, a structured five-stage assessment, validation,
deterministic scoring — and emits a canonical, auditable result with a
reproducible content identity.

> Demo mode validates product functionality and reproducibility. It is **not
> benchmark evidence**.

## What RepoGuard is

RepoGuard turns repositories into evidence, evidence into a structured
assessment, and that assessment into a deterministic score:

```text
Repository
    → pinned snapshot
    → extracted evidence (frozen artifact)
    → structured assessment (LOAD → PLAN → ASSESS → CROSS-CHECK → FINALIZE)
    → validation
    → deterministic scoring
    → auditable result (repoguard-v1:<sha256>)
```

The assessment is scored by the canonical deterministic scoring engine; the
result carries evidence citations that are checked against the frozen
artifact, so every significant claim is traceable — or it is honestly marked
`UNCERTAIN` / left unscored.

## Why this matters

An LLM can produce persuasive engineering-review prose without producing a
reproducible or evidence-backed evaluation. RepoGuard is designed to
constrain that behavior:

* **Frozen evidence** — the artifact an assessment reasons over is immutable
  and identity-bearing; reasoning never reads past it.
* **Structured assessment** — 25 rubric criteria across five dimensions
  (Architecture, Testing, Maintainability, Dependencies, Documentation),
  each with a canonical status and integer score.
* **Canonical rubric** — one versioned rubric (`rubric_version: 1.0`) is the
  single source of truth for criteria and score bounds.
* **Evidence citations** — every finding cites evidence IDs that must exist in
  the frozen artifact.
* **Fail-closed validation** — malformed or unverifiable output is a recorded
  failure, never a guess.
* **Deterministic scoring** — identical inputs and model output produce
  identical scores and identities.
* **Audit artifacts** — results preserve the workflow trace, evidence
  identity, and reproducibility metadata.
* **Reproducible identities** — results are content-addressed over every
  semantic field; runtime metadata is excluded.

RepoGuard does **not** claim a score when it cannot verify one.

## Architecture

```text
Repository
    ↓  snapshot acquisition (acquire_case)
Snapshot
    ↓  evidence extraction (extract_snapshot_directory)
Frozen evidence artifact
    ↓  RepoGuard assessment pipeline (run_case: LOAD → PLAN → ASSESS → CROSS-CHECK → FINALIZE)
Structured, validated assessment
    ↓  canonical deterministic scoring engine (evaluation/scoring)
Canonical result (identity-bearing, auditable)
    ↓  audit / benchmark / metrics layers
```

The implementation is in `evaluation/`: datasets, snapshot acquisition,
evidence extraction, the baseline evaluator, the RepoGuard pipeline, the
scoring engine, ground truth, benchmark runner, and metrics.

**Product UI ≠ scoring engine.** The web interface
(`app/repoguard/`) is a thin read-only layer over the evaluation engine. It
executes the engine's pipeline and renders the artifact it produced; it
contains no scoring logic and reimplements none of the validation. Scores are
computed once, by the canonical engine.

## The RepoGuard pipeline (five stages)

The pipeline is implemented in `evaluation/repoguard/` with exactly five
explicit stages, enforced by a small state machine
(`evaluation/repoguard/pipeline.py`):

```text
LOAD → PLAN → ASSESS → CROSS-CHECK → FINALIZE
```

1. **LOAD** — validate the input evidence artifact. Unusable evidence fails
   closed (`invalid_evidence`).
2. **PLAN** — derive a deterministic relevance pool per criterion and validate
   the model's plan section (`invalid_plan` if structurally broken). The
   model's relevance lists are recorded as context, never as claim support.
3. **ASSESS** — reshape the model's criteria into the exact authored mapping
   the scoring engine consumes and run it through the engine's own
   validation (unknown criterion, wrong score bound, missing citations →
   fail closed as `invalid_assessment`).
4. **CROSS-CHECK** — deterministically re-read the cited evidence and force
   any row that contradicts its own evidence into `UNCERTAIN`
   (downgrade-only; scores never increase). The model's self-reported
   cross-check is structurally validated and **recorded, never acted on**
   (`invalid_cross_check` on structural failure).
5. **FINALIZE** — revalidate the corrected rows and refuse incomplete
   results; any `PENDING` criterion means the run fails closed
   (`incomplete_assessment`).

The rules that matter:

* stages are fixed and transitions are enforced;
* failures are recorded — a failed run is never given a score;
* malformed model output does not become a score;
* the deterministic cross-check can downgrade findings/scores but never
  increase them;
* finalization refuses incomplete/`PENDING` assessments.

## Demo vs Live vs Benchmark

| | Demo | Live | Benchmark |
| --- | --- | --- | --- |
| Provider | deterministic `MockProvider` | configured provider | configured provider |
| Repository | synthetic (`DEMO001`) | real, snapshotted | frozen dataset cases |
| Credentials | none | required | required |
| Network | none | required | required |
| Result | real canonical artifact | real canonical artifact | measured against ground truth |
| Purpose | judge-facing reproducibility demo | real repository assessment | comparative evaluation |

**Demo** is a local, deterministic demonstration: no credentials, no network,
no external LLM — but it runs the genuine pipeline and produces a real
canonical artifact. It is suitable for hackathon judges and proves
functionality + reproducibility. It is **not benchmark evidence**.

**Live** snapshots and extracts a real repository with the configured
provider. Provider/model must be explicitly configured; provider failures
**fail closed** (a failed live assessment never receives a score); a live run
can take several minutes; there is no automatic retry or silent fallback.

**Benchmark** uses the frozen dataset, snapshot/evidence store, and the
benchmark orchestration layer to compare baseline and RepoGuard outputs
against human ground truth. It is the only path on which system performance
is claimed, and only from runs actually recorded per `docs/evaluation.md`
(section 10). Do not confuse it with Demo; no benchmark performance is claimed
here.

## Reproducibility (verified)

Demo mode was verified in a clean environment (all provider variables and
keys absent) and inside a Docker container with the network **disabled**:

* three clean-environment Demo runs: score **63.0 / 63.0 / 63.0**;
* all three share one canonical result identity —
  `repoguard-v1:5750ed642ef79aba87b94cd17431a79ab0ec23c5a62131e06c7b6107f66e1d2d`
  (as observed during verification);
* Docker (`--network none`): health succeeds, Demo succeeds at 63.0, identity
  identical, persisted result validated;
* runtime metadata (timestamp, latency, tokens) is intentionally **excluded**
  from semantic identity.

Identical inputs + identical model output ⇒ identical identity by
construction (content-addressed serialization).

## Evaluation methodology

The three things are deliberately different:

```text
LLM-generated assessment  ≠  validated RepoGuard assessment  ≠  deterministic score
```

The model **proposes** structured findings. RepoGuard validates them —
schema, case binding, evidence identity, citations, rubric compatibility,
completeness, and the deterministic cross-check constraints — and only then
does the canonical scoring engine **produce** the score. The model does not
directly determine the final score; an invalid or incomplete assessment is
never scored. The human ground-truth layer (`docs/ground-truth.md`) records
reviewer scores by humans only, and the benchmark/metrics layers
comparatively measure systems against that reference.

## Security and failure behavior

* Provider/model failures **fail closed** — no score for failed assessments.
* Malformed, incomplete, or contradicting assessments are rejected or
  downgraded, never repaired upward.
* Secrets are sanitized/masked in every artifact and error body; API keys are
  never logged or returned.
* Assessment ids are validated as strict content digests; repository URLs are
  scheme-checked; repository code is never executed (git runs as argument
  lists, never a shell).
* No automatic retries, no silent provider fallback.
* Technical errors are separated from user-facing messages (stable `error`
  codes; no tracebacks leak to clients).

Intentional, documented limitations: no authentication, no rate limiting,
synchronous live execution, and a public-demo assumption — provider/network
availability affects **Live** mode only. Details:
`docs/product-interface.md`.

## Quickstart

### Docker (recommended for judges)

```bash
docker compose up --build        # builds and serves on http://localhost:8000/
```

or, with an explicit image:

```bash
docker build -t repoguard .
docker run -p 8000:8000 repoguard
```

If port 8000 is taken, use another host port, e.g. `docker run -p 8015:8000
repoguard`.

Open **http://localhost:8000/** and click **Try Demo**.

Expected:

* the assessment succeeds (real pipeline, no credentials, no network);
* a DEMO ASSESSMENT scorecard at **63.0 / 100**;
* evidence-backed findings across the five dimensions;
* an Evidence and Audit trail with a downloadable canonical artifact.

### Local

```powershell
.\scripts\setup.ps1              # one-time: creates .venv, installs editable dev deps
.\scripts\run.ps1                # starts API + UI on http://127.0.0.1:8000
```

bash/macOS: `./scripts/setup.sh` and `./scripts/run.sh`. `scripts/run.ps1`
detects Docker and prefers Docker Compose, falling back to local uvicorn.

Health check: `GET /health` → `{"status":"healthy"}`.

## Development

### Tests and quality gates

```bash
pytest -q
ruff check .
ruff format --check .
python -m mypy app evaluation
```

Test suites: unit tests for the evaluation framework under `tests/unit/`, plus
API/product tests under `tests/api/` (demo determinism, live wiring,
fail-closed behavior, structured errors, and no-secret-leak assertions).

### Project structure

```text
app/repoguard/        FastAPI product layer
  api/                HTTP endpoints + validation
  services/           demo, executor, store
  static/             dependency-free UI (HTML/CSS/JS, no build step)
evaluation/           evaluation framework
  datasets/           frozen dataset
  snapshot/           repository snapshot acquisition + hashing
  evidence/           evidence extraction + serialization
  baseline/           baseline evaluator (single-LLM reference)
  repoguard/          the five-stage assessment pipeline
  scoring/            canonical deterministic scoring engine
  ground_truth/       human ground truth + consensus
  benchmark/          benchmark orchestration
  metrics/            comparison metrics (read-only)
docs/                 documentation (+ decisions/)
tests/                unit and API tests
scripts/              cross-platform dev scripts
data/                 runtime product store (gitignored)
```

### Documentation index

* `docs/evaluation.md` — evaluation protocol and methodology
* `docs/product-interface.md` — the web interface, Demo/Live, error handling
* `docs/repoguard.md` — the five-stage pipeline in detail
* `docs/baseline.md` — the baseline evaluator
* `docs/scoring-engine.md`, `docs/scoring-rubric.md` — scoring design
* `docs/evidence-extraction.md`, `docs/snapshot-acquisition.md` — evidence
* `docs/ground-truth.md`, `docs/metrics.md`, `docs/benchmark-runner.md` — evaluation layers

## Status

Active development for a hackathon submission. The evaluation engine, frozen
dataset, ground truth, and benchmark/metrics layers are intact; the evaluation
protocol is documented in `docs/evaluation.md`. No benchmark performance is
claimed here — measured system comparisons follow that protocol and live in
the evaluation layer, not in this readme.