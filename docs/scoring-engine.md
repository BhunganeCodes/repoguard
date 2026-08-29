# RepoGuard Scoring Engine

The scoring engine provides the deterministic mechanics and validation
framework that turn extracted evidence into an assessment against the
canonical scoring rubric (`docs/scoring-rubric.md`, version 1.0).

It is **not** a judge. The engine cannot assign a score to a criterion from
raw evidence alone where the rubric requires qualitative judgment. Those
scores are produced by a human reviewer (ground truth, per
`docs/evaluation.md` Section 6) or, later, by an LLM assessor. The engine
validates those authored criteria, computes the rubric's arithmetic
(dimension totals, `earned`/`possible`/`score`, N/A normalization, rounding),
and emits a reproducible structured assessment artifact.

## Architecture

```
evaluation/
  scoring/                  # scoring subsystem (this code)
    __main__.py             # python -m evaluation.scoring
    cli.py                  # command-line interface
    rubric.py               # canonical rubric data (25 criteria, versioning)
    statuses.py             # assessment statuses incl. PENDING, score bounds
    models.py               # typed assessment models
    compute.py              # dimension/aggregate arithmetic + rounding
    validate.py             # fail-closed assessment validation
    serialize.py            # deterministic artifact composition + identity
    _version.py             # version + assessment identity scheme
  evidence/                 # consumed evidence artifacts (read-only)
```

## Data flow

```
evidence artifact (evidence.yaml)
      |
      v
criterion assessment (authored: status + score + citations + rationale)
      |
      v
dimension score (computed: earned / maximum / scored / status breakdown)
      |
      v
overall score (computed: earned / possible / normalized 1-decimal score)
      |
      v
structured assessment artifact (criterion rows + dimensions + summary +
                                assessment_identity)
```

Only the **criterion rows** are authored. Every number below the criterion
level is recomputed deterministically by the engine and is never copied from
the input, so a stale or falsified aggregate cannot propagate.

The engine consumes the evidence artifact read-only. It never inspects a
repository, clones anything, executes repository code, calls an LLM, infers
facts absent from evidence, modifies evidence, or discovers new evidence.

## Scope and honesty boundary

The scorer never pretends that raw evidence equals human judgment. A
criterion whose qualitative assessment cannot be mechanically derived from
evidence is represented as:

* **`PENDING`** (a non-score state), when the criterion has not yet been
  assessed by a human or LLM; or
* a score with status `FOUND` / `NOT_FOUND` / `UNCERTAIN`, authored by an
  assessor and bounded by the rubric's status-to-score mapping.

No score is invented merely because evidence exists. An assessment with any
`PENDING` criterion is *valid* (it may be stored and reviewed) but is not
*scoreable*: the engine refuses to emit `earned`/`score` until every
criterion has a terminal status.

## Rubric and versioning

`evaluation/scoring/rubric.py` is the machine-readable encoding of the
canonical rubric:

* rubric version `1.0` (matches `docs/scoring-rubric.md`);
* five dimensions (matching the evidence categories): architecture, testing,
  maintainability, dependencies, documentation;
* 25 criterion IDs, five per dimension, e.g.
  `architecture.project_organization`, `testing.failure_path_coverage`,
  `dependencies.supply_chain_discipline`,
  `documentation.architecture_documentation`;
* dimension maximum 20, criterion maximum 4.

Criterion IDs are stable `dimension.criterion` slugs and are distinct from
evidence item IDs (e.g. the `documentation.architecture_documentation`
criterion cites the `documentation.architecture_docs` evidence item).

An assessment that references an unknown criterion or dimension is rejected.
An assessment whose `rubric_version` is missing or not `1.0` is rejected:
the engine implements exactly the canonical rubric.

## Assessment statuses

The four canonical statuses from the rubric (`docs/scoring-rubric.md`
Section 3) are inherited from the evidence schema:

| Status | Meaning | Allowed score |
|--------|---------|---------------|
| FOUND | verifiable evidence supports the criterion | 0-4, per the anchors |
| NOT_FOUND | a deliberate search found no evidence | 0 |
| UNCERTAIN | evidence is partial/ambiguous; reason required | 0-2 (0 if entirely unsupported) |
| NOT_APPLICABLE | criterion does not apply; justification + evidence required | none (excluded) |
| PENDING | not yet assessed by a human/LLM | none (blocks scoring) |

The status-to-score bounds are exactly rubric Section 3.5. The `PENDING`
status is the engine's supported non-score state.

## Scoring calculation (rubric Section 6)

Dimensions and the aggregate are computed from the authored criterion rows:

    dimension_score = sum of the scores of the dimension's applicable criteria
    earned          = sum of all five dimension scores
    possible        = 100 - (4 x number of NOT_APPLICABLE criteria)
    score           = (earned / possible) x 100, rounded to one decimal

* N/A normalization is exact per the rubric: only NOT_APPLICABLE criteria
  reduce `possible` by 4 each.
* Rounding uses half-up (`ROUND_HALF_UP`): 0.05 rounds up. The arithmetic is
  done with exact `Decimal` rationals, so repeated runs are bit-identical.
* If `possible <= 0`, the assessment is rejected (fail closed; the rubric
  says such a repository is not scoreable).
* `UNCERTAIN` criteria count toward `earned` with their bounded score, never
  above 2. `NOT_FOUND` contributes 0. `NOT_APPLICABLE` contributes nothing
  and `PENDING` blocks scoring entirely.

## Evidence linkage

Every scored / non-pending criterion must carry at least one `citations`
entry. Each citation is an `evidence_id` that must exist in the referenced
evidence artifact; a citation to nonexistent evidence is a validation error.
Evidence items may be cited across categories (e.g. a Documentation
criterion may cite the `architecture.architecture_docs` evidence item); only
existence is enforced, because cross-category citations are legitimate.

The assessment records the referenced artifact's `evidence_identity`. The
engine recomputes the identity of the supplied evidence artifact and
rejects the assessment on mismatch. The evidence artifact is passed
separately (`--evidence <path>`); an assessment therefore never embeds
evidence items and never claims a link it cannot verify.

## Validation (fail closed)

`evaluation/scoring/validate.py` returns problems (empty == valid) and
rejects any assessment that:

* is missing its `rubric_version`, `case_id`, `schema_version`,
  `evidence_identity`, or criteria list;
* uses an unsupported rubric version (anything other than `1.0`);
* does not match the supplied evidence's recomputed identity or case ID;
* references an unknown criterion ID, an unknown/incorrect dimension, or an
  evidence ID that does not exist in the artifact;
* has duplicate, missing, or unknown criteria (exactly the 25 canonical
  criteria must be present);
* has a non-integer score or a score outside the status-bound range
  (e.g. 5 on `FOUND`, 3 on `UNCERTAIN`, non-zero on `NOT_FOUND`, or any score
  on `NOT_APPLICABLE`/`PENDING`);
* has `NOT_APPLICABLE` without justification, without supporting evidence
  citations, or with a score;
* has `UNCERTAIN` without an `uncertainty_reason`, or marks `unsupported`
  without a zero score;
* yields `possible <= 0`;
* provides `dimensions`, `summary`, or `assessment_identity` that do not
  reconcile with the arithmetic recomputed from the criteria.

Reconciliation means: provided per-dimension `earned`/`maximum`/`scored`/
`status_counts`, all summary fields, and the `assessment_identity` must equal
what the engine recomputes. Validating a previously scored artifact therefore
checks it end to end.

## Assessment identity

The composed artifact carries `assessment_identity`, a SHA-256 over the
canonical, key-sorted YAML rendering of every semantic field, prefixed with
`repoguard-assessment-v1`. The identity itself is excluded. The artifact
contains no runtime metadata, so:

* scoring the same authored assessment twice yields byte-identical output
  and the same identity;
* any change to criteria (score, status, citations) changes the identity;
* an authored assessment is only accepted if its recorded identity matches
  when one is present.

## CLI usage

Run from the repository root (no network access required):

```
# 1. Validate an assessment against the rubric + evidence artifact.
python -m evaluation.scoring validate \
  --assessment assessment.yaml \
  --evidence evaluation/snapshots/C001-gosim/evidence.yaml

# 2. Score a complete assessment; emit the structured artifact.
python -m evaluation.scoring score \
  --assessment assessment.yaml \
  --evidence evaluation/snapshots/C001-gosim/evidence.yaml \
  --out scored.yaml

# 3. Inspect an assessment; --validate exits non-zero on invalid content.
python -m evaluation.scoring inspect \
  --assessment assessment.yaml \
  --evidence evaluation/snapshots/C001-gosim/evidence.yaml --validate
```

`validate` and `inspect` print YAML to stdout and exit non-zero on problems;
`score` refuses to emit a number while any criterion is `PENDING`. Exit
codes, YAML-to-stdout, and error-to-stderr conventions mirror the snapshot
and evidence subsystems.

An assessment is a plain YAML file:

```yaml
schema_version: 1
case_id: C001
name: gosim
rubric_version: "1.0"
evidence_identity: repoguard-evidence-v1:...
criteria:
  - criterion_id: architecture.project_organization
    dimension: architecture
    status: FOUND
    score: 3
    citations: [architecture.top_level_structure]
    rationale: Top-level layout is conventional and navigable.
  - criterion_id: documentation.architecture_documentation
    dimension: documentation
    status: NOT_APPLICABLE
    score: null
    citations: [documentation.architecture_docs]
    justification: Single-file program; no architecture documentation applies.
  - criterion_id: dependencies.supply_chain_discipline
    dimension: dependencies
    status: UNCERTAIN
    score: 1
    citations: [dependencies.vendored_dependencies]
    uncertainty_reason: Vendored content was only sampled.
  - criterion_id: maintainability.technical_debt
    dimension: maintainability
    status: PENDING
    score: null
    citations: []
  # ... 25 criteria total
```

The `score` command appends `dimensions`, `summary`, and
`assessment_identity`.

## Relationship to future human and LLM assessments

* **Human ground truth** (`docs/evaluation.md` Section 6): a reviewer authors
  the 25 criterion rows with statuses, scores, and citations. The engine
  validates and aggregates them, guaranteeing the reported `earned`,
  `possible`, and `score` follow the canonical rubric exactly and reconcile
  with the criterion rows.
* **System/LLM assessments**: an LLM assessor (or the evaluation runner or
  baseline) produces criterion rows the same way. The engine applies the
  identical validation and arithmetic, so human and system assessments are
  comparable under the same rubric version.
* `PENDING` is the mechanism for the engine to *not* invent judgment: rows a
  human/LLM has not yet filled remain pending, and no overall score is
  emitted until they are terminal.

The engine creates no ground truth of its own. It never scores benchmark
repositories by default and produces no reviewer scores or
strong/average/weak/challenging classifications.

## Security assumptions

The engine reads YAML assessment and evidence files only. It does not
execute repository code, tools, or scripts, and requires no network access.

## Limitations

* The engine's authority is mechanical: validation and arithmetic. Anything
  qualitative (the 0-4 anchor judgment per criterion) comes from an authored
  assessment.
* Only rubric version `1.0` is supported; assessments on other versions are
  rejected rather than silently reinterpreted.
* An assessment with `PENDING` criteria cannot be scored, by design.
* The engine's identity chain covers the authored criteria and computed
  aggregates; the chain to repository content runs through the evidence
  artifact's `snapshot_content_hash`.