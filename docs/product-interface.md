# RepoGuard Product Interface

The product interface is a small, polished web layer on top of the existing
evidence-backed evaluation engine (`evaluation/`). It exposes RepoGuard as a
synchronous API plus a dependency-free browser UI (static HTML/JS served by the
FastAPI app), and it deliberately reuses the framework's canonical
subsystems — snapshot acquisition, evidence extraction, the RepoGuard
pipeline, and the scoring engine — without reimplementing or weakening any of
them.

> Status: demonstration/demo interface for the project. It is not a SaaS
> product: there is no user system, queue, or billed API (see
> "Deliberately not implemented").

## Quick start

### Local (no Docker)

```powershell
# one-time setup (creates .venv and installs the package editable)
.\scripts\setup.ps1
# or: pip install -e ".[dev]"

# run the API + UI on http://127.0.0.1:8000
.\scripts\run.ps1
```

Open `http://127.0.0.1:8000/`, submit any URL with **Demo** mode, and you get
a completed DEMO assessment within a second — no network, no model, no keys.

**Live** mode snapshots the given repository, extracts evidence, and calls the
configured model provider (see `docs/baseline.md` for the environment
variables). Without a configured provider it fails closed (recorded as a
`failed` result) rather than inventing a score — matching the framework's
fail-closed contract.

### Docker

```bash
docker compose up --build     # builds the image and serves on :8000
```

* `app/` is bind-mounted so API/UI changes hot-reload during development.
* `data/` is bind-mounted for the runtime result store (snapshots, evidence,
  results); it is excluded from the image and from git.
* Hash of the image import path: `repoguard.main:app`, port `8000`.

> Note: if another service already listens on `:8000`, start this container on
> another host port, e.g.
> `docker run -p 8015:8000 repoguard-api`.

## API

All endpoints return JSON. **No endpoint computes a score** — every value is
read from the canonical, identity-bearing artifact produced by the evaluation
engine.

### `GET /health`

Synthetic liveness probe.

```json
{"status": "healthy"}
```

### `POST /api/assess`

Runs one assessment end-to-end (synchronous). Returns `201` with the completed
assessment, its evidence, and the content identity.

Request body:

| field | type | notes |
| --- | --- | --- |
| `repository_url` | string | required; `http`, `https`, or `file` scheme. Untrusted input; only ever used as a git remote (no code is executed). |
| `commit` | string? | optional full 40-hex SHA. Omitted ⇒ default-branch HEAD is resolved and **pinned** for the snapshot. |
| `mode` | `"live" | "demo"` | required; `demo` is the deterministic synthetic path. |

Response (abridged):

```json
{
  "assessment_id": "repoguard-v1:<sha256>",
  "mode": "demo",
  "demo": true,
  "status": "succeeded",
  "result": {
    "system": "repoguard",
    "repoguard_version": "0.1.0",
    "rubric_version": "1.0",
    "case_id": "DEMO001",
    "name": "demo-synthetic-repo",
    "evidence_identity": "repoguard-evidence-v1:<sha256>",
    "status": "succeeded",
    "provider": {"name": "mock", "model": "mock"},
    "process": {"stages": [{"stage": "load", "status": "ok"}, "…"]},
    "assessment": {"criteria": [25 rows], "dimensions": [5 rows], "summary": {"score": 63.0}, "assessment_identity": "repoguard-assessment-v1:<sha256>"},
    "scoring": {"complete": true, "earned": 63, "possible": 100, "score": 63.0, "not_applicable": 0, "uncertain": 2, "pending": []},
    "result_identity": "repoguard-v1:<sha256>"
  },
  "evidence": {"evidence_identity": "…", "items": [25 items]}
}
```

Failures are reported honestly through the shape described under
[Error handling](#error-handling): client problems return `400`, acquisition/
snapshot/evidence problems return `502`, and model problems return `201` with a
persisted `failed` result (`scoring: null`) — never a `500`, never a traceback,
never a guess.

### `GET /api/assess/{assessment_id}`

Fetch a persisted assessment by its content identity. The id may be the full
`repoguard-v1:<sha>` or the bare 64-hex digest. `404` for unknown ids.

### `GET /api/assess/{assessment_id}/evidence`

The evidence artifact behind the assessment (items, statuses, source paths,
provenance).

### `GET /api/assess/{assessment_id}/report`

The canonical result artifact: assessment, scoring, workflow trace, and audit
metadata.

### `GET /api/assess/{assessment_id}/download`

Downloads the canonical assessment artifact **exactly as persisted** — the
stored YAML bytes, served unchanged with `Content-Disposition: attachment`
(the framework's serialization already masks secrets). Nothing is re-composed
on the way out.

## Lifecycle

The interface is synchronous (no job queue): `POST /api/assess` returns only
after the run finishes or records a failure. The **lifecycle is still honest
and inspectable**: every result embeds the real workflow trace
(`result.process.stages`) recorded by the framework's state machine:

| state | meaning |
| --- | --- |
| `queued` | request accepted; not yet started |
| `snapshotting` | git repository pinned and fetched to an immutable snapshot |
| `extracting` | deterministic evidence extracted from the checkout |
| `assessing` | RepoGuard LOAD → PLAN → ASSESS → CROSS-CHECK → FINALIZE |
| `scoring` | canonical scoring over the 25 rubric criteria |
| `completed` / `failed` | result persisted; `failed` carries an `error.kind` and details and **never** a score |

The UI shows an indeterminate, non-fabricated running indicator while a
request is in flight (the interface is synchronous, so no fake stage
progress is animated) and then always renders the recorded `process.stages`
trace (each annotated `ok`/`failed`), so a partial or failed run is displayed
as such.

## Results presentation

The UI renders only already-computed data:

* **Overall score** (`example: 63.0 / 100`) from `assessment.summary.score`.
* **Five dimensions** — Architecture, Testing, Maintainability, Dependencies,
  Documentation — each with `earned / maximum` (20) from
  `assessment.dimensions`.
* **Findings** grouped by dimension: criterion id, canonical status
  (`FOUND` / `NOT_FOUND` / `UNCERTAIN` / `NOT_APPLICABLE`), integer score,
  citations, and any `uncertainty_reason` / `justification`. Findings stay the
  primary content; the finding-to-evidence copy notes that each finding links to
  its extracted evidence.
* **Evidence** and **Audit trail** are collapsible technical sections,
  collapsed by default so they never crowd the scorecard. The evidence table
  shows evidence id, category, status, source paths, and the raw observation;
  each row carries an `id` anchor. The audit trail exposes only canonical
  metadata: case id, repository, requested/verified commit, snapshot content
  hash, evidence identity, rubric version, assessment identity, result identity,
  RepoGuard/prompt versions, model/provider, runtime facts (timestamp, latency),
  and the recorded workflow trace.
* **Finding → evidence navigation**: clicking a citation opens the evidence
  section (if collapsed), scrolls to the cited row, and gives it a non-color-only
  target treatment (outline + inset bar) plus keyboard/screen-reader focus.
* **Audit download**: the Audit trail section links to the
  `GET .../download` endpoint above, making the canonical artifact easy to
  save without ever rendering secrets.

There is **no scoring logic in JavaScript**; the frontend merely lays out the
authoritative DTOs.

## Demo mode

`mode=demo` runs the real pipeline (plan, assess, cross-check, scoring, all
fail-closed validation) against:

* a **synthetic, deterministic evidence artifact** (`DEMO001`,
  `demo-synthetic-repo`) with 25 items — one per rubric criterion — covering
  all five dimensions with mixed statuses, and
* the framework's **`MockProvider`**, which returns a staged model response
  citing exactly those evidence items.

The result is a genuine RepoGuard artifact with a valid content identity
illustrating a balanced scorecard (e.g. `63.0 / 100`), a couple of `UNCERTAIN`
rows, and two `NOT_FOUND` findings. It is **always** labeled a DEMO
ASSESSMENT in the UI payload and is never presented as a real repository
assessment, and it lives only in the runtime store — never in the evaluation
dataset, ground truth, or benchmark surface.

## Live mode

`mode=live`:

1. resolves the pinned commit (provided or default-branch HEAD via
   `git ls-remote`),
2. acquires an immutable, verified snapshot (reuses `acquire_case`; writes
   `snapshot.yaml`, `inventory.yaml`, `checkout/` under `data/snapshots/`),
3. extracts evidence via the standard extractors (`extract_snapshot_directory`),
4. runs `evaluation.repoguard.pipeline.run_case` with the env-configured
   provider,
5. persists `data/results/<digest>.yaml` and `.evidence.yaml`.

Live mode is intentionally strict: an LLM that fails, hallucinates, or returns
unparseable output produces a `failed` artifact with `error.kind` ∈
`provider_error | malformed_response | invalid_plan | invalid_cross_check |
invalid_assessment | incomplete_assessment` — the same fail-closed behavior as
the evaluation suite. Expect manually-configured provider latency; the model
call is the dominant cost.

Provider/model resolution mirrors the CLI exactly: an HTTP provider
(`REPOGUARD_LLM_PROVIDER`) uses `REPOGUARD_LLM_MODEL` (falling back to `mock`
as the CLI does); any other provider resolves to `mock`. Live mode never
implicitly falls back to `MockProvider`: an unset `REPOGUARD_LLM_PROVIDER` is a
controlled product error, not a silently mocked assessment.

## Error handling

Client-visible failures share one structured shape (FastAPI `detail`):

```json
{
  "error": "repository_invalid",
  "message": "That commit does not exist in the repository.",
  "details": []
}
```

The `error` code is stable and machine-readable so the UI can classify a
failure without parsing prose. The `message` is stable, human copy — never a
Python traceback, filesystem path, or git stderr dump.

| code | HTTP | meaning |
| --- | --- | --- |
| `repository_invalid` | 400 | URL/commit input is invalid, unsupported, or the pinned commit does not exist |
| `repository_unavailable` | 502 | commit resolution or snapshot acquisition could not reach the repository |
| `snapshot_error` | 502 | the snapshot could not be recorded (cannot be completed by editing inputs) |
| `evidence_error` | 502 | evidence extraction failed after a successful snapshot |
| `provider_unavailable` | 400 | Live Assessment is not configured (no `REPOGUARD_LLM_PROVIDER`) or the provider cannot be built |
| `internal_error` | 500 | last-resort guard: an unexpected exception was logged and turned into a JSON body without a traceback |

Provider/model failures during a run are **not** HTTP errors: the request
succeeds (201) and returns a persisted `failed` result artifact with
`result.error.kind` plus `scoring: null` — a failed run never produces a score.

The static UI renders these failures with human-readable primary copy (e.g.
"RepoGuard couldn't access that repository or commit. Check the URL and commit
SHA and try again. No score was produced."). Raw evaluation kind strings and
details stay available only inside a collapsed "Technical details" surface, and
provider failures offer a **Try Demo** button that runs the genuine Demo flow.
RepoGuard never renders a score for a failed run, and error bodies are
guaranteed free of credentials and key material (asserted by tests).

## Storage, identity, and reproducibility

* Runtime outputs live under `data/` (configurable with `REPOGUARD_DATA_DIR`),
  out of the frozen evaluation stores.
* Result/evidence artifacts are written with the framework's canonical
  serializers, so every file has a verifiable SHA-256 identity
  (`repoguard-v1:`, `repoguard-evidence-v1:`, `repoguard-assessment-v1:`).
* Identical inputs + identical model output ⇒ identical identities (runtime
  metadata is excluded from identities), so assessments are reproducible.
* Repeat demo calls produce byte-identical identities by construction.

## Security

* Repository URLs are **untrusted**: validated to `http`/`https`/`file` before
  use, passed to git only as argument lists (no shell), and repository code is
  never executed.
* Assessment ids are validated as bare 64-hex digests before any file access;
  path traversal is impossible.
* Provider API keys are never serialized or returned: all artifacts go through
  the framework's `sanitize_config`/`mask_secrets` machinery, and the UI
  displays only model/provider name and (non-secret) base URL.
* Error responses (controlled 400/502 and the last-resort 500) never include
  tracebacks, filesystem paths, keys, or `Authorization` headers; tests assert
  no secret material appears in any error body.
* No credentials, `.env` files, or `data/` content are committed or shipped in
  the image.

## Tests and quality gates

```powershell
.\scripts\test.ps1            # or: python -m pytest
ruff check .
ruff format --check .
python -m mypy app evaluation
docker compose up --build     # then GET /health returns {"status":"healthy"}
```

Coverage of the product layer (`tests/api/test_product_api.py`):

* demo end-to-end success + determinism,
* all lookup endpoints and id normalization (full identity vs bare digest),
* 404s for unknown/traversal/malformed ids,
* invalid URL schemes, missing host, malformed commits → 400,
* no secret material (deliberately-set fake keys) leaks in any response,
* live mode: real snapshot + extraction wiring and fail-closed recorded
  results,
* live mode success through the executor against a real local checkout.

## File map

* `app/repoguard/main.py` — FastAPI app: `/health`, API router, static mount.
* `app/repoguard/api/routes.py` — the four assessment endpoints + validation.
* `app/repoguard/services/executor.py` — orchestrates snapshot → evidence →
  RepoGuard → persist.
* `app/repoguard/services/demo.py` — deterministic synthetic demo (evidence +
  staged response + `MockProvider`).
* `app/repoguard/services/store.py` — runtime data store (paths, lookups).
* `app/repoguard/static/` — dependency-free UI (HTML/CSS/JS; no build step).
* `evaluation/snapshot/git.py` — added `ls_remote_head` (default-branch pinning).
* `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `pyproject.toml`
  (static package-data) — containerization.
* `tests/api/test_product_api.py` — API/live/demo/security tests.

Deliberately not implemented (out of scope, would add complexity without a
demonstrated need):

* user accounts, authentication, multi-tenancy, billing/quotas,
* durable job queue / background workers (synchronous by design),
* a database (content-addressed files only),
* GitHub App/webhooks, CI badge, or API clients in other languages,
* editing/submitting assessments back into evaluation results — the product
  layer is strictly read-only with respect to the evaluation suite.