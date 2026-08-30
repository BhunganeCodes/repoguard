# RepoGuard Evidence Extraction

The evidence subsystem extracts deterministic, evidence-only observations
from frozen repository snapshots. It feeds the evaluation framework's
evidence layer (see `docs/scoring-rubric.md`): the extracted evidence is what
later stages refer to when reasoning about engineering quality.

It implements the evidence-extraction requirements of the quality-assessment
phase of `docs/evaluation.md`. It is **not** a scorer: no quality scores, no
ranks, no tiers, and no LLM logic live here.

## Architecture

```
evaluation/
  evidence/                  # evidence subsystem (this code)
    __main__.py              # python -m evaluation.evidence
    cli.py                   # command-line interface
    extract.py               # extraction orchestration
    serialize.py             # deterministic YAML + content identity
    validate.py              # artifact validation rules
    models.py                # EvidenceItem / EvidenceArtifact schemas
    statuses.py              # canonical statuses and categories
    paths.py                 # artifact location (next to snapshot)
    errors.py                # typed failures
    _version.py              # version + identity scheme constant
    extractors/              # one module per rubric dimension
      base.py                # shared mechanical helpers
      architecture.py        # architecture evidence
      testing.py             # testing evidence
      maintainability.py     # maintainability evidence
      dependencies.py        # dependencies evidence
      documentation.py       # documentation evidence
  snapshots/                 # LOCAL snapshot store (gitignored)
    <candidate_id>-<name>/
      snapshot.yaml          # acquisition record (input)
      inventory.yaml         # repository inventory (input)
      checkout/              # git worktree at the pinned commit (input)
      evidence.yaml          # derived evidence artifact (this subsystem)
```

The subsystem is a plain Python package importable from the repo root
(`python -m evaluation.evidence`). It depends only on the standard library
plus PyYAML. It reuses `evaluation.snapshot.git` for the tracked-file list
and the snapshot store layout constants; it never modifies snapshot state.

## Evidence model

Every observation is an `EvidenceItem` with at least:

- `evidence_id` — stable id `{category}.{evidence_type}`
- `case_id` — repository/candidate ID (e.g. `C001`)
- `category` — one of `architecture`, `testing`, `maintainability`,
  `dependencies`, `documentation`
- `evidence_type` — semantic type of the observation
- `status` — one of `FOUND`, `NOT_FOUND`, `UNCERTAIN`, `NOT_APPLICABLE`
- `observation` — free-form factual statement (no scoring language)
- `source_paths` — concrete repository-relative paths backing the claim
- `extractor` / `extractor_version` — provenance of the claim

Items optionally carry `notes` and a structured `observed` mapping of counts
and markers. The set of statuses and categories is part of the schema; do not
introduce alternative spellings (`evaluation/evidence/statuses.py`).

## Extractors

Each rubric dimension has one extractor. They are strict observers: they
detect files, directories, config sections, manifest content, and marker
counts; they never judge, score, or rank. Positive claims (`FOUND`) always
cite concrete source paths. Known patterns are confined to explicit constants
in `evaluation/evidence/extractors/`. No claim is based on naming
resemblance alone without also pointing at the files.

Representative facts per dimension include:

- **Architecture** — top-level structure, module-named directories,
  source/test separation, configuration boundaries, architecture/ADR docs,
  explicit visibility-boundary directories such as `internal/`.
- **Testing** — test files and directories, naming conventions, test
  configuration, declared test invocation commands, coverage configuration,
  integration/E2E markers, fixture/mock assets.
- **Maintainability** — formatting, lint, and static-analysis configuration;
  CI workflow files; contribution docs; code-organization markers;
  generated-code markers; raw TODO/FIXME/HACK counts.
- **Dependencies** — dependency manifests and managers, lockfiles, parsed
  direct dependency declarations (bounded), dev/test dependency groups,
  version-specifier shapes, workspace/monorepo markers, vendored content.
- **Documentation** — README, documentation directories, API doc configuration,
  contribution guides, architecture/design docs, changelog/release notes,
  examples/tutorials.

## Status semantics

- `FOUND` — a concrete, source-path-backed observation was made.
- `NOT_FOUND` — the extractor searched for the item and did not find it.
- `UNCERTAIN` — an artifact was present but could not be interpreted
  (example: a dependency manifest that fails to parse). The observation says
  what is uncertain and why.
- `NOT_APPLICABLE` — reserved for observations that genuinely do not apply to
  a repository type. Current extractors avoid it; absence is reported as
  `NOT_FOUND`.

## Sampling

Extractors read repository content only when necessary and always in a bounded,
deterministic order (sorted tracked paths, capped file counts and line counts).
Constants in `extractors/base.py` (`MAX_SAMPLE_FILES`, `MAX_LINES_PER_FILE`,
`MAX_HEADER_LINES`, `MAX_SOURCE_PATHS_PER_ITEM`) limit runtime and artifact
size. Two runs over the same checkout sample the same files in the same order.

## CLI usage

Run from the repository root:

```
# 1. Extract evidence for one existing snapshot directory.
python -m evaluation.evidence one --snapshot evaluation/snapshots/C001-gosim

# 2. Same, resolving the snapshot directory from the frozen dataset.
python -m evaluation.evidence one \
  --manifest evaluation/datasets/dataset-v1.0.0.yaml --case C001

# 3. Extract evidence for every snapshot present in the store.
python -m evaluation.evidence dataset

# 4. Inspect an artifact; --validate exits non-zero on invalid content.
python -m evaluation.evidence inspect \
  --artifact evaluation/snapshots/C001-gosim/evidence.yaml --validate
```

Exit codes, YAML-to-stdout conventions, and error-to-stderr behavior mirror
`evaluation.snapshot`.

## Determinism and identity

The artifact's `evidence_identity` is a SHA-256 of the canonical, key-sorted
YAML rendering of every semantic field (items, snapshot metadata), prefixed
with the scheme `repoguard-evidence-v1`. Runtime metadata (`generated_at`) and
the identity itself are excluded. Consequences:

- Re-extracting the same snapshot always yields equivalent evidence.
- Two runs produce byte-identical artifacts (apart from `generated_at`).
- Any change to the checkout content changes the identity.
- `inspect --validate` recomputes the identity and flags a mismatch.

Output paths are repository-relative POSIX paths. The artifact never contains
absolute local paths, timestamps in item identity fields, or quality verdicts.

## Validation

`evaluation/evidence/validate.py` enforces that:

- schema version, identity scheme, and provenance fields are present;
- every item uses a canonical category and status;
- FOUND items cite at least one source path;
- source paths are relative, POSIX, and never escape or are absolute;
- observations/notes never use rubric tier labels (`excellent`, `average`,
  `weak`, `challenging`, ...) or scoring vocabulary (`score`, `rank`, `tier`,
  ...);
- evidence IDs are unique and every category produced at least one item.

## Security assumptions

The snapshot checkout is treated as untrusted input. Extractors use only
bounded text reads of known text-ish files and never execute repository code,
package managers, builds, tests, Makefiles, scripts, Dockerfiles, or binaries.
The tracked-file list comes from `git ls-files` metadata of the local clone,
not from executing repository tooling.

## Integrity and provenance

Evidence is derived from the immutable snapshot record: `extract.py` reads the
pinned commit, verified commit, content hash, and repository URL from
`snapshot.yaml` and stamps them onto the artifact. The artifact is written
next to the snapshot (`evidence.yaml`) and is regenerable at any time from the
same checkout, so it can be audited or rebuilt rather than trusted.

## Limitations

- Extractor pattern sets are explicit and bounded; novel tooling or layouts
  may be reported as `NOT_FOUND` until patterns are added. Adding a pattern is
  an extractor-version change.
- Dependency declaration parsing is deliberately defensive; exotic or malformed
  manifests produce `UNCERTAIN`, not fabricated lists.
- Bounded sampling means large codebases are inspected representatively, not
  exhaustively.
- `evidence_identity` covers evidence content, not the snapshot itself; the
  chain to repository content runs through the recorded `snapshot_content_hash`.