# Ground Truth (Issue #15)

This document describes how RepoGuard's human ground truth is recorded,
validated, and turned into a final consensus artifact. It implements
`docs/evaluation.md` Section 6 (Ground Truth) and Section 7 (Reviewer
Procedure). Ground truth is the human-produced, rubric-scored reference that
all system rankings are compared against; it is produced by qualified human
reviewers only.

## 1. Principles

- **Humans only.** An LLM is never used to produce ground truth. LLM output
  (baseline, RepoGuard) is always the object of evaluation, never the
  reference (`evaluation.md` 6.1).
- **Independence.** Reviewers record their full scoring sheet for a case
  before seeing any other reviewer's scores or case metadata
  (`evaluation.md` 6.2).
- **Blinding.** Reviewers are identified only by pseudonymous IDs (`R01`,
  `R02`, ...). They are blinded to the intended tier of a case and to all
  system results. Reviewer input schemas reject unknown fields, so a tier,
  rank, baseline score, or RepoGuard score cannot be smuggled into a
  reviewer assessment (`evaluation.md` 6.8).
- **Evidence.** Every criterion carries a status and citations to concrete
  evidence from the frozen evidence artifact (or the permitted snapshot
  inspection procedure). Invented evidence IDs are rejected
  (`evaluation.md` 6.4).
- **Canonical statuses.** Reviewers use only `FOUND`, `NOT_FOUND`,
  `UNCERTAIN`, `NOT_APPLICABLE` from the rubric Section 3. `PENDING` is a
  tool-only state and is rejected in human input.
- **Fail closed.** Any invalid review, decision file, adjudication record, or
  consensus artifact is rejected rather than coerced into a score. Nothing is
  ever overwritten: original reviewer assessments are always retained.

## 2. Reviewer Assessment

Each reviewer produces one assessment per case. The machine-recorded review
contains:

- `reviewer_id` — pseudonymous identifier (e.g. `R01`).
- `case_id`, `dataset_version`, `rubric_version`, `evidence_identity` — the
  frozen case the review binds to. `dataset_version` must equal the frozen
  `1.0.0`; `rubric_version` must equal the implemented `1.0`.
- `inspected_files` — the repository-relative list of files the reviewer
  actually inspected, per the sampling procedure (`evaluation.md` 7.2).
- `criteria` — all 25 canonical criteria. Per criterion: `criterion_id`,
  `status`, `score` (where the status permits), `citations` (evidence IDs,
  all of which must exist in the referenced artifact), `rationale`
  (justification/reason), plus `justification` for `NOT_APPLICABLE`,
  `uncertainty_reason` and `unsupported` for `UNCERTAIN`.
- `review_time_minutes` — optional, excluded from the content identity.

The reviewer does not supply the dimension of a criterion; it is derived from
the canonical rubric by the validator, so the reviewer cannot drift from it.

`review_identity` is optional in hand-authored sheets but is always stamped
by the tooling and is recomputed on inspection. It is a SHA-256 over the
canonical YAML of every semantic field (runtime fields and the identity
itself excluded).

## 3. Disagreement Detection

`compare` compares two or more independent reviews deterministically
(`evaluation/ground_truth/compare.py`) using the thresholds of
`evaluation.md` 6.6 without modification:

- a criterion is **disputed** when the recorded scores differ by **more than
  one point**;
- a criterion is also disputed on **applicability** when one reviewer marks
  it `NOT_APPLICABLE` and another scores it;
- a case **needs discussion** when any criterion is disputed **or** the
  aggregate scores (normalized `score` from rubric Section 6, computed by the
  same deterministic scorer) differ by **more than five points**.

Reports are deterministic: reviewer pairs are sorted by id, criteria are
reported in canonical rubric order, and the exact thresholds (`>1`,
`>5`) are recorded in the report for the reader.

## 4. Adjudication

- When a case needs discussion, reviewers discuss against the cited evidence
  (`evaluation.md` 6.6). If no consensus is reached, a third qualified
  reviewer (the adjudicator, e.g. `R03`) adjudicates, scoring independently
  and citing evidence.
- The decisions file must cover every disputed criterion and must record a
  final `rationale` per criterion. Decisions must use canonical statuses and
  pass the same scoring validation as a review.
- The **adjudication record** captures the disputed criteria, the **original
  reviewer assessments** (never modified), the adjudicator's decision, and
  the final rationale. The adjudicator is validated to be distinct from the
  reviewers.
- The adjudicator records whether the case remains **contested** after
  adjudication. A contested case is flagged in the consensus artifact
  (`status: contested`) and is excluded from primary-metric comparisons only
  when the evaluation runner records that exclusion (`evaluation.md` 6.6).

## 5. Final Consensus Artifact

`build_consensus` composes the ground-truth artifact for the case:

- disputed criteria adopt the adjudicator's decision;
- every other criterion keeps the reviewers' shared value. If reviewers
  differ by at most one point on an uncontested criterion, the value of the
  first reviewer in reviewer-id order is adopted deterministically (this is a
  tie-break for near-agreement only; `evaluation.md` 6.7 keeps reviewer
  agreement as the rule);
- the composed assessment is validated and run through the same deterministic
  scoring engine used for every assessment (`compose_assessment`), producing
  per-dimension totals, `earned`, `possible`, and the normalized `score`, with
  a recomputed assessment identity.

The artifact records:

- `dataset_version`, `case_id`, `name`, `rubric_version`,
  `evidence_identity`;
- `status` — `consensus` or `contested`;
- `reviewers` — the independent reviewer IDs and the adjudicator;
- `adjudication_identity` — linkage to the record it was built from;
- `provenance` — for each criterion, which reviewers/adjudicator determined
  it and whether by agreement, tie-break, or adjudication;
- `assessment` — the scored artifact from the shared scoring engine;
- `ground_truth_identity` — the recomputable content identity.

Ground truth is deterministic: building the same artifact twice produces
byte-identical output.

## 6. Storage and Separation

Ground truth lives under `evaluation/ground_truth/`, entirely separate from
`evaluation/baseline/`, `evaluation/repoguard/`, and `evaluation/results/`
(`evaluation.md` Section 13.2). Reviewer sheets, adjudication records, and
consensus artifacts are stored under the gitignored `local/` tree:

    evaluation/ground_truth/local/reviews/
    evaluation/ground_truth/local/adjudications/
    evaluation/ground_truth/local/consensus/

The ground-truth CLI never reads `evaluation/results/`, never exposes system
scores in reviewer input, and never writes into any system-result tree.
Ground truth is human reference data and is never produced by the baseline or
RepoGuard.

## 7. CLI

    python -m evaluation.ground_truth --version
    python -m evaluation.ground_truth validate --review <R01 review> --evidence <evidence>
    python -m evaluation.ground_truth compare \
        --review <R01 review> --review <R02 review> --evidence <evidence>
    python -m evaluation.ground_truth adjudicate \
        --case C001 --review <R01 review> --review <R02 review> \
        --decisions <decisions file> --evidence <evidence> \
        [--out-record <path>] [--out-consensus <path>]
    python -m evaluation.ground_truth inspect --artifact <path> \
        --evidence <evidence> [--review <R01> --review <R02>] [--validate]

- `validate` exits 0 when the reviewer assessment is valid, 1 otherwise, and
  prints the problems.
- `compare` prints the disagreement report (thresholds, aggregations,
  disputed criteria, discussion flag).
- `adjudicate` validates the decisions file against the reviews, writes the
  adjudication record and the final consensus artifact, and prints both
  locations plus their identities.
- `inspect` reports kind, identity match, and problems; with `--validate` it
  exits non-zero for any invalid or tampered artifact. Review inspection
  needs `--evidence`; adjudication-record inspection needs the reviews too.

Exit codes and YAML conventions mirror the other assessment CLIs.

## 8. Validation Summary

The shared validator rejects, among others:

- missing, duplicate, or unknown criteria;
- invalid status or an out-of-bounds score for a status (rubric 3.5);
- `NOT_APPLICABLE` without justification or with a score;
- `UNCERTAIN` without a reason, or `unsupported` not at score 0;
- citations to nonexistent evidence, or a criterion without citations;
- evidence-identity, dataset-version, rubric-version, or case mismatches;
- unknown top-level fields (system-result isolation);
- tampered content identities.

The final consensus artifact is validated by the same deterministic scoring
engine (`validate_assessment` + `compose_assessment`) that scores baseline
and RepoGuard assessments, so ground truth and system results are measured on
one rubric and one arithmetic.

## 9. Security and Reproducibility

- Reviewers carry pseudonymous IDs only; no names, emails, or personal data
  are recorded.
- No credentials are involved; nothing is ever committed to git.
- Every artifact is content-addressed and independently verifiable.
- Reproducing the workflow from the same reviews, decisions, evidence, and
  dataset version produces identical identities and scores.