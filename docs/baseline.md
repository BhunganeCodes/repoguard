# RepoGuard Baseline Evaluator

The baseline is the deliberately simple reference implementation of
`docs/evaluation.md` Section 8: **give an LLM the repository evidence and
ask it to assess the repository against the canonical rubric.**

It is **not** RepoGuard. RepoGuard's added intelligence is only justified if
it beats this baseline on the locked evaluation cases
(`docs/evaluation.md` Section 8.2); the baseline exists to make that
comparison possible.

## Why the baseline exists

Evaluation's primary objective is ranking agreement with human ground truth
(`docs/evaluation.md` Section 2). A single-LLM, prompt-only assessment is the
simplest construction that can produce a rubric-scored assessment, and it is
the natural null hypothesis: any complexity RepoGuard adds must demonstrably
improve outcomes over a plain model call, measured under identical
conditions (`docs/evaluation.md` Section 10).

## What the baseline deliberately does not do

This is not an agent. The baseline has no:

- multi-agent workflows or subagents;
- autonomous planning or self-designed steps;
- iterative self-reflection or self-correction loops;
- tool-use loops or retrieval agents;
- repository modification, code execution, browsing, or shell access;
- sophisticated orchestration.

It performs **exactly one** LLM call per case: one prompt built once, one
response, one validation, one score. Nothing an agent would add is present
because adding it here would defeat the purpose of the baseline.

## Architecture

```
evidence artifact
      |  load + verify identity (fail closed)
      v
canonical rubric (scoring/rubric.py, version 1.0)
      |  rendered into the prompt (versioned)
      v
deterministic prompt  (prompt.py, PROMPT_VERSION)
      |
      v
LLM provider          (provider.py: mock | openai-compatible)
      |
      v
structured assessment (JSON/YAML authored-assessment schema)
      |
      v
scoring validation    (scoring.validate_assessment)
      |  reject anything invalid, never repair
      v
score / result        (serialize.py: deterministic identity + runtime metadata)
```

Code layout:

```
evaluation/baseline/
  __main__.py / cli.py    # python -m evaluation.baseline {one|dataset|inspect}
  _version.py             # version, result identity scheme, system id
  errors.py               # BaselineError / ProviderError / MalformedResponse
  provider.py             # LLMProvider interface, mock + HTTP providers
  prompt.py               # versioned canonical prompt (rubric + evidence + output)
  pipeline.py             # run_case: one prompt -> one LLM call -> validation -> score
  models.py               # BaselineResult / ErrorRecord / RuntimeMetadata
  serialize.py            # deterministic result artifact + identity + redaction
  paths.py                # result storage conventions
```

The pipeline consumes a frozen evidence artifact **read-only**. It never
touches a repository: no cloning, no checkout, no code execution, and no
calls into repository commands.

## Prompt versioning

`prompt.py` defines exactly one canonical prompt (`PROMPT_VERSION = "1.0"`).
It is deterministic: the same evidence artifact always produces the same
system + user byte sequence. No runtime metadata (timestamps, latency, run
ids) is embedded, so repeated runs are comparable.

The prompt has four blocks:

- **SYSTEM** — role and the fixed rules: assess only the supplied evidence;
  never fabricate facts, files, line numbers, metrics, tests, or behavior;
  cite evidence IDs; use only canonical statuses; distinguish `NOT_FOUND`
  from `UNCERTAIN`; use `NOT_APPLICABLE` only with justification; provide
  `uncertainty_reason` for `UNCERTAIN`; keep scores within status bounds;
  do not assign quality tiers (the rubric requires none); return only the
  structured JSON object.
- **RUBRIC** — rubric version, the five dimensions, the evidence-status to
  score-bound mapping, the general 0-4 anchors, and all 25 criteria with
  their canonical IDs and per-score anchor text transcribed from
  `docs/scoring-rubric.md` Section 5.
- **EVIDENCE** — the full evidence artifact: case id, name, repository URL,
  verified commit, snapshot content hash, evidence identity, and every item
  with its ID, category, status, observation, source paths, and notes.
- **OUTPUT** — the exact authored-assessment JSON schema the model must
  return, with per-field rules.

The RUBRIC block is bound to rubric version `1.0`
(`EXPECTED_RUBRIC_VERSION`). If the scoring engine's rubric version ever
diverges, the prompt builder fails closed rather than silently assessing
against a different rubric. A unit test re-parses `docs/scoring-rubric.md`
and fails when the transcribed anchors drift from the canonical document,
which forces a deliberate `PROMPT_VERSION` bump on any rubric or prompt
change.

## Provider interface

`provider.py` defines a minimal contract:

```
LLMProvider
    name: str
    generate(request) -> LLMResponse
    public_config() -> dict        # non-secret facts recorded in results
```

`LLMRequest` carries `system`, `prompt`, `model`, `temperature`, and
`max_tokens`. `LLMResponse` carries the text plus, when the provider exposes
them, `model`, `input_tokens`, `output_tokens`, and `estimated_cost`. Cost
is **never invented**: unknown cost is recorded as `null`.

Two implementations:

- **MockProvider** (`mock`, the default) — deterministic and network-free.
  It returns a canned response (optionally from the
  `REPOGUARD_MOCK_RESPONSE` environment variable for CLI smoke tests),
  writes no data, and is what every unit test uses.
- **HTTPCompatibleProvider** (`openai-compatible`) — a generic
  `/chat/completions` HTTP client. It is an implementation detail of the
  probe, not an endorsement of a vendor: it works with any endpoint speaking
  the de-facto chat-completions JSON shape, including local servers. It is
  configured through environment variables and fails closed when
  unconfigured. It is never exercised by the test suite.

No API key is required for unit tests; no credentials are ever committed.

## Configuration

CLI flags mirror the snapshot/evidence/scoring conventions:

```
python -m evaluation.baseline one \
    --evidence evaluation/snapshots/C001-gosim/evidence.yaml \
    [--out result.yaml] [--provider mock|openai-compatible] \
    [--model <id>] [--temperature 0.0] [--max-tokens N]

python -m evaluation.baseline dataset \
    [--store evaluation/snapshots] [--results-dir <dir>] [--provider ...] ...

python -m evaluation.baseline inspect --result <path> [--validate]
```

Environment variables:

| Variable | Meaning |
|----------|---------|
| `REPOGUARD_LLM_PROVIDER` | provider name (default `mock`) |
| `REPOGUARD_LLM_MODEL` | model id for the HTTP provider / recorded model |
| `REPOGUARD_LLM_BASE_URL` | base URL of the chat-completions endpoint |
| `REPOGUARD_LLM_API_KEY` | optional key for the endpoint (never recorded) |
| `OPENROUTER_API_KEY` | fallback key for OpenRouter endpoints when the above is unset (never recorded) |
| `GEMINI_API_KEY` | fallback key for Google Gemini endpoints when the higher-priority keys are unset (never recorded) |
| `REPOGUARD_LLM_TIMEOUT_S` | optional outbound HTTP timeout in seconds (default 60) |
| `REPOGUARD_MOCK_RESPONSE` | canned mock response (tests / smoke runs) |

The API key is used only for the `Authorization` header of the outbound
request and never appears in result artifacts (see Redaction).

### Gemini API smoke test (single case)

The `openai-compatible` provider talks to Google Gemini's OpenAI-compatible
layer (`https://generativelanguage.googleapis.com/v1beta/openai`), so no
Gemini-specific code is needed and the key is read from `GEMINI_API_KEY`:

```
export REPOGUARD_LLM_PROVIDER=openai-compatible
export REPOGUARD_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export REPOGUARD_LLM_MODEL=gemini-2.5-pro
export GEMINI_API_KEY=<your key>          # or REPOGUARD_LLM_API_KEY
export REPOGUARD_LLM_TIMEOUT_S=600

python -m evaluation.baseline one \
    --evidence evaluation/snapshots/C001-gosim/evidence.yaml \
    --model gemini-2.5-pro \
    --max-tokens 16384 \
    --out evaluation/results/local/baseline/C001-baseline-gemini.yaml
```

### OpenRouter API smoke test (single case)

The same `openai-compatible` provider talks to OpenRouter's OpenAI-compatible
API (`https://openrouter.ai/api/v1`) with the key read from
`OPENROUTER_API_KEY`:

```
export REPOGUARD_LLM_PROVIDER=openai-compatible
export REPOGUARD_LLM_BASE_URL=https://openrouter.ai/api/v1
export REPOGUARD_LLM_MODEL=z-ai/glm-5.2:free
export OPENROUTER_API_KEY=<your key>      # or REPOGUARD_LLM_API_KEY
export REPOGUARD_LLM_TIMEOUT_S=600

python -m evaluation.baseline one \
    --evidence evaluation/snapshots/C001-gosim/evidence.yaml \
    --model z-ai/glm-5.2:free \
    --max-tokens 16384 \
    --out evaluation/results/local/baseline/C001-baseline-openrouter-glm52.yaml
```

A successful run ends when the scoring engine accepts the model's assessment
and the result is written (exit 0); it is never converted into a score on
failure.

## Result schema

Each run produces one result artifact (`schema_version: 1`):

```
schema_version, system: "baseline"
baseline_version, prompt_version, rubric_version
case_id, name, evidence_identity
status: "succeeded" | "failed"
provider: {name, model, config (sanitized)}
assessment: scoring-engine artifact (incl. assessment_identity) | null
scoring:    {complete, earned, possible, score, not_applicable, uncertain, pending} | null
error:      {kind, message, details} | null
model_response: raw model text (recorded on failure)
result_identity: repoguard-baseline-v1:<sha256>
runtime: {requested_at, latency_ms, input_tokens, output_tokens,
          estimated_cost, response_metadata}
```

`one` prints the result YAML to stdout (or `--out`) and exits `0` on a
scored result, `1` on any failure — a failed result is still written/printed
so the audit trail exists. `dataset` runs every evidence artifact under the
snapshot store and exits non-zero if any case failed. Running `dataset` does
not touch the locked benchmark dataset's evidence or ground truth; it is the
capability the evaluation runner will later invoke deliberately.

## Validation

The model response is parsed (JSON or YAML; optional code fences are
stripped — this bounded normalization is the only concession, and is
documented here) and then validated **fail closed** before any score exists:

- evidence input missing, invalid, or with an identity that does not match
  its content;
- rubric missing or mismatched with the prompt's rubric rendering;
- response that does not parse to a mapping (`malformed_response`);
- authored assessment rejected by `scoring.validate_assessment`: unknown or
  missing criteria, invalid statuses, out-of-bounds scores, invalid or
  nonexistent citations, `NOT_APPLICABLE` without justification, `UNCERTAIN`
  without a reason, missing required fields, or a non-reconciling identity;
- an assessment that is valid-but-incomplete (`PENDING` criteria) is treated
  as a failure (`incomplete_assessment`) — the baseline never emits a number
  for criteria it did not finish assessing.

An invalid model response is never converted into a score. Parse or
validation failures become a `failed` result with the recorded error and the
raw model response retained for inspection.

## Reproducibility

Every artifact records baseline version, prompt version, rubric version,
case id, evidence identity, provider name/model, model configuration,
request timestamp, response metadata where available, the assessment
identity, the scoring result, and failure information if any.

Semantic identity is separated from run timing: `result_identity` is a
SHA-256 over every semantic field (baseline/prompt/rubric versions, case and
evidence identity, provider facts, the assessment, scoring, error, and
recorded model response) in canonical sorted YAML. `runtime` timestamps,
latency, token counts, and cost are recorded in the artifact but excluded
from the identity, so identical assessments have identical identities
regardless of when they ran. Repeated identical mock runs over the same
evidence therefore produce identical semantic results.

The identity chain to repository content runs through the evidence artifact:
baseline result → `evidence_identity` → `snapshot_content_hash`. A changed
snapshot or evidence changes the evidence identity and therefore the
assessment and result identities.

## Redaction

Secrets never appear in artifacts:

- model configuration is sanitized recursively before serialization: any
  key matching `key`, `token`, `secret`, `password`, `auth`, or `credential`
  is dropped (`serialize.sanitize_config`);
- as a final safety net, the CLI passes the configured API key value (when
  set) to the renderer, which replaces it with `<redacted>` in the output
  text (`serialize.mask_secrets`);
- the HTTP provider's `public_config()` never includes the API key.

## Cost and runtime metadata

Latency is always measured around the provider call. Token counts and
estimated cost are recorded only when the provider exposes them; `null`
(`~`) otherwise. No cost figure is invented.

## Security

LLM output is untrusted input. It is parsed as a plain data document and
validated against the scoring engine; it is never executed, never treated as
shell input, and never allowed to modify repository snapshots or evidence.
The pipeline requires no network access beyond the explicit provider call.

## Testing

Unit tests in `tests/unit/test_baseline_*.py` (with `baseline_helpers.py`
fixtures) exercise prompt determinism and content, rubric/evidence
inclusion, the mock provider, valid and malformed responses, invalid
citations/scores/missing criteria, evidence identity mismatch, provider
failure, deterministic serialization, metadata handling, and secret
redaction. All tests use the mock provider; no test reaches the network.

A live-end-to-end smoke against a real LLM provider is possible but must be
run manually (configure an `openai-compatible` provider and an evidence
artifact); it is deliberately not part of the automated suite.

## Limitations

- The baseline has no intelligence beyond the model: it cannot search,
  inspect, or verify beyond what is in the evidence artifact.
- It is single-pass and single-model; there is no self-correction.
- It depends on the evidence extractor's quality and complete, unambiguous
  evidence; ambiguous cases may come back `UNCERTAIN` and score low.
- Transcript fidelity depends on the model obeying the structured-output
  instructions; non-compliance is a documented `failed` run, not a coerced
  score.
- Prompt and rubric version are coupled; any rubric change requires a new
  prompt version and a re-run of affected comparisons against the same
  evaluation cases (`docs/evaluation.md` Section 14).