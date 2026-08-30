# RepoGuard (Evaluation Version)

RepoGuard is the structured, evidence-first assessment system: the candidate
improvement evaluated against the baseline (`docs/baseline.md`) on the locked
evaluation cases (`docs/evaluation.md` Section 8.2). It consumes frozen
evidence artifacts and produces the exact canonical assessment schema consumed
by the scoring engine (`docs/scoring-engine.md`), but its construction is
deliberately more explicit than the baseline's, and every mechanism exists
**only** because the baseline leaves a measurable gap.

## Goal

The baseline performs one LLM call per case: one prompt, one response, one
validation, one score. RepoGuard's hypothesis is that a *staged* workflow over
the same evidence - explicit relevance planning, per-criterion assessment,
and an active re-check of the model's own scores against the evidence -
reduces unsupported positive claims and lets honest uncertainty surface as
`UNCERTAIN` (rubric Section 3.4) instead of being silently scored.

Like the baseline, RepoGuard is not an agent framework:

- exactly **one** structured provider call per case;
- **no** tools, shell, browsing, multi-agent routing, or self-reflection
  loops;
- **no** repository access and **no** code execution - it reasons only over
  the frozen evidence artifact;
- every stage is deterministic or fail-closed code; nothing is improvised.

## Workflow

RepoGuard runs five explicit, inspectable stages in a fixed order:

```
LOAD -> PLAN -> ASSESS -> CROSS-CHECK -> FINALIZE
```

Each stage is validated before the next begins, and the orchestration is a
single `run_case` call (`evaluation/repoguard/pipeline.py`). Stage order and
transitions are enforced by a small state machine (`state.py`); any invalid
transition is a recorded failure, never a score.

### Transport vs stages

The model sees a single prompt (`prompts.py`) whose response carries three
sections - `plan`, `criteria`, `cross_check` - so the stock provider contract
works end to end and a full run stays one call. RepoGuard treats each section
as a separately validated *stage*: the sections are transported together, but
nothing is believed until its own stage validates it. If evaluation shows
that separate calls materially beat the single call, this transport can
change without changing the stages.

### The stages

1. **LOAD** - the evidence artifact is validated (`validate_evidence`, shared
   with the baseline). Empty, missing-identity, or structurally unusable
   evidence fails closed (`invalid_evidence`); no run proceeds on it.
2. **PLAN** - a deterministic layer
   (`plan.py::build_deterministic_plan`) derives, for each of the 25
   criteria, the pool of evidence items in the criterion's dimension plus the
   pool's status coverage. This is pure code over the artifact. The model's
   `plan` section is then validated structurally (`plan_from_model`): a plan
   that is not a mapping, references a nonexistent evidence id, duplicates or
   omits a criterion fails closed (`invalid_plan`). The audited plan record
   merges the deterministic pool with the model's (validated) relevance
   selection. The model's relevance lists are recorded as context, **never**
   as claim support.
3. **ASSESS** - the model's `criteria` section is reshaped into the exact
   authored assessment mapping the scoring engine consumes
   (`assess.py::build_authored`; values such as `case_id`, `name`,
   `rubric_version`, and `evidence_identity` are always taken from the
   validated artifact, never from unverified model text). The authored
   assessment is then run through the scoring engine's own fail-closed
   validation (`validate_assessment`). Any structural problem (unknown
   criterion, wrong dimension, score outside its status bound, missing
   citations or justification, coordinate limits, missing evidence identity,
   not 25 criteria) fails closed (`invalid_assessment`); nothing is repaired.
4. **CROSS-CHECK** - the deterministic, evidence-grounded re-check
   (`crosscheck.py::detect`). For every criterion row RepoGuard re-reads the
   cited evidence items and forces any row that contradicts its own evidence
   into `UNCERTAIN` (downgrade-only, recorded as a `warning` finding with its
   resolution):
   - `FOUND` row citing **only** non-FOUND evidence: the positive claim is
     unsupported -> `UNCERTAIN`, score 0, `unsupported: true`;
   - `FOUND` row citing a **mix** of FOUND and non-FOUND evidence: support is
     partial -> `UNCERTAIN`, score capped at 2;
   - `NOT_FOUND` row citing FOUND evidence: the negative claim contradicts
     the evidence -> `UNCERTAIN`, score 0.
   
   Scores never increase. The model's own `cross_check` section is validated
   structurally and recorded as `model_reported` context; RepoGuard **never
   acts on** the model's self-reported findings. Structural problems in the
   model's cross-check section fail closed (`invalid_cross_check`).
5. **FINALIZE** - the corrected rows are re-validated, composed through the
   scoring engine (`compose_assessment`), and refused unless complete
   (`require_complete`); any `PENDING` criterion means the artifact is not
   scoreable and the run fails closed (`incomplete_assessment`).

## Failures are recorded, never scored

RepoGuard never converts a failure into a score. Every failure produces a
result artifact with `status: failed`, a recorded `error` (`kind`, `message`,
`details`), the stage trace **up to and including** the failing stage, and -
on response-level failures - the raw `model_response` for the audit record.
Failure kinds are stable and documented:

| kind                     | meaning                                                     |
| ------------------------ | ----------------------------------------------------------- |
| `invalid_evidence`       | input evidence artifact is not usable                       |
| `provider_error`         | provider call raised or returned unusably late              |
| `malformed_response`     | response did not parse, or parsed to the wrong shape        |
| `invalid_plan`           | PLAN section failed structural validation                  |
| `invalid_assessment`     | criteria failed the scoring engine's validation             |
| `invalid_cross_check`    | CROSS-CHECK section failed structural validation           |
| `incomplete_assessment`  | valid assessment with PENDING criteria (not scoreable)     |

Stdin/stdout CLI mirrors the baseline (`one` / `dataset` / `inspect`):

    python -m evaluation.repoguard --version
    python -m evaluation.repoguard one --evidence <evidence.yaml> [--out <file>]
    python -m evaluation.repoguard dataset
    python -m evaluation.repoguard inspect --result <file> [--validate]

`--provider openai-compatible` reuses the baseline HTTP provider contract and
its environment variables; it fails closed when unconfigured.

## Difference from the baseline

| aspect            | baseline                          | RepoGuard                                   |
| ----------------- | --------------------------------- | ------------------------------------------- |
| per-case calls    | 1                                 | 1 (structured, staged)                      |
| relevance plan    | implied inside the prompt         | explicit deterministic pool + validated model selection     |
| criteria output   | validated flat                    | authored reshaping + scoring validation     |
| self-check        | none                              | deterministic evidence re-check; model's own cross-check recorded, never trusted |
| uncertainty       | whatever the model returns        | forced downgrades to UNCERTAIN when evidence contradicts the claim |
| failure handling  | recorded, never scored            | recorded, never scored                      |

The difference is therefore **not** more agents: it is more explicit,
deterministically verified structure around the same single evidence source.
RepoGuard is justified only if it improves ranking agreement on the locked
cases (measured, `docs/evaluation.md` Section 10).

## Provider abstraction

`provider.py` re-exports the baseline's provider namespace
(`LLMProvider`, `LLMRequest`, `LLMResponse`, `MockProvider`,
`build_provider`) so one contract serves both systems and RepoGuard tests
run deterministically with the mock provider. The provider receives the
built prompt and returns text and token/cost metadata; it can never see a
repository.

Real (Gemini) provider configuration is identical to the baseline's
`openai-compatible` provider, including reading the key from
`GEMINI_API_KEY` or `OPENROUTER_API_KEY`
(docs/baseline.md, "Gemini API smoke test" and "OpenRouter API smoke test").
A single-case smoke run uses the same environment and:

```
python -m evaluation.repoguard one \
    --evidence evaluation/snapshots/C001-gosim/evidence.yaml \
    --model gemini-2.5-pro \
    --max-tokens 16384 \
    --out evaluation/results/local/repoguard/C001-repoguard-gemini.yaml
```

## Validation and honesty rules

- Significant claims must be traceable to evidence IDs that exist in the
  artifact (enforced structurally at PLAN and by the scoring engine at
  ASSESS/FINALIZE).
- Unsupported positive claims are downgraded, never repaired upward.
- Nothing that RepoGuard cannot verify is asserted; the honest bucket is
  `UNCERTAIN`, never a number.
- The model's self-reported cross-check is recorded, never acted on.
- Input evidence identity is carried into the authored mapping from the
  artifact, so a mismatch never silently propagates.

## Reproducibility

- The prompt is deterministic and versioned (`PROMPT_VERSION`); its rubric
  block is bound to the rubric version and fails closed on mismatch.
- Stage order is fixed; `RunState` carries no runtime metadata.
- Result identity (`repoguard-v1:<sha-256>`) is computed over every semantic
  field of the result (stages, plan, findings, assessment, scoring, error)
  with runtime facts (timestamp, latency, tokens, cost) excluded - identical
  runs produce identical identities.
- Repeated identical mock runs are compared byte-for-byte in the test suite.

## Security

- Results and redaction reuse the baseline machinery (`sanitize_config`,
  `mask_secrets`): credential-looking model-config keys are dropped and the
  rendered result masks known secrets.
- The system never executes repository code, never shells out, never reaches
  the network except through the pluggable HTTP provider, and never reads
  the benchmark ground truth or dataset.

## Limitations

- One call means the PLAN, criteria, and cross-check are latent in one
  response; the stages are validated post hoc, not independently generated.
- The deterministic cross-check catches evidence-contradictions that fit its
  three rules; it is not a general claim validator.
- `dataset` runs all artifacts in the store with one provider configuration
  (mock by default); a provider run requires a configured endpoint and is a
  benchmark concern outside this documentation's scope.