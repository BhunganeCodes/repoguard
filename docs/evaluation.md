# RepoGuard Evaluation Protocol

This document defines the evaluation methodology for RepoGuard: how
repositories are selected, snapshotted, judged by humans, and compared
against system output.

It is a specification only. It does not select repositories, and it does
not implement the evaluation runner, the baseline, or RepoGuard agent
logic. Those are separate issues built against this protocol.

The protocol is aligned with the canonical scoring rubric
(`docs/scoring-rubric.md`, version 1.0) and with the engineering principles
in AGENTS.md: correctness, evidence-backed analysis, reproducibility,
testability, simplicity, and measured improvement.

## Status

Initial protocol, version 1.0.

## 1. Purpose and Scope

- Define the evaluation dataset shape and selection criteria.
- Define immutable repository snapshots.
- Define how human ground truth is produced with the canonical rubric.
- Define the baseline and the comparison rules.
- Define primary and secondary metrics.
- Define the reproducibility and result requirements.

Repository selection, the evaluation runner, and any agent/analyzer
implementation are out of scope for this document and are tracked
separately (Section 15).

## 2. Evaluation Objectives

The objectives of evaluation are:

1. Measure agreement between RepoGuard's repository ranking and human
   ground-truth ranking (primary objective).
2. Measure evidence quality, finding quality, and resource usage of the
   system (secondary objectives).
3. Compare RepoGuard against a deliberately simple baseline under
   identical conditions.

Evaluation exists to support measured improvement: a change is adopted only
if it demonstrably improves outcomes on the locked evaluation cases.

## 3. Evaluation Dataset

### 3.1 Target Size and Distribution

The initial dataset targets **12 repositories**, distributed as:

| Tier | Count | Description |
|------|-------|-------------|
| Strong / well-engineered | 3 | High quality across most rubric dimensions |
| Average / mixed quality | 3 | Some strengths, clear weaknesses |
| Weak / problematic | 3 | Significant problems across most dimensions |
| Challenging / deceptive | 3 | Positive/misleading surface signals with deeper problems |

This is a **target distribution, not a quota**. If a repository does not
belong in a tier on merit, it must not be forced into that tier. Selection
balances toward the target where practical, and the final distribution is
recorded in the dataset metadata.

### 3.2 Ecosystem Diversity

The dataset should contain multiple programming ecosystems where practical.
Preference goes to ecosystems the baseline and RepoGuard can inspect with
comparable fidelity (for example, ecosystem-specific manifests and tests
should not systematically disadvantage one ecosystem). Ecosystem diversity
must not be pursued at the expense of the quality-tier target.

### 3.3 Dataset Locking

Once selected, the dataset is fixed for any comparison. Adding, removing,
or replacing a case is a dataset change (Section 14) and invalidates
comparisons that mix old and new case sets.

## 4. Repository Selection Criteria

Selection uses the following criteria. Candidates are screened against each
criterion and the result is recorded.

### 4.1 Engineering-Quality Diversity

Candidates must span the quality range of the rubric, from strong to weak,
so the ranking metric can distinguish the system's behavior across the full
scale. A dataset containing only similar-quality repositories cannot measure
ranking agreement meaningfully.

### 4.2 Language / Ecosystem Diversity

Candidates should span multiple ecosystems with mature tooling (manifests,
lockfiles, test frameworks, CI). Each ecosystem must be represented by more
than one candidate where possible, so quality differences are not confused
with ecosystem differences.

### 4.3 Repository Size Diversity

Include small, medium, and large repositories. Large repositories test
evidence sampling and risk assessment under partial inspection; small
repositories test precision. Size is measured in files and lines of code at
the snapshot commit.

### 4.4 Architectural Diversity

Include different architectures: layered, modular, monolith, service-based,
framework-driven, and low-level/system code, so Architecture criteria are
exercised broadly rather than in one style.

### 4.5 Test Maturity

Include repositories ranging from no tests to disciplined test suites, so
the Testing dimension covers the full anchor range.

### 4.6 Documentation Maturity

Include repositories ranging from undocumented to well documented,
covering the Documentation dimension's full range (README, installation,
architecture, interfaces, developer docs).

### 4.7 Dependency-Management Maturity

Include repositories with disciplined dependency hygiene (locked, pinned,
minimal) and repositories with poor hygiene, so the Dependencies dimension
is exercised on both ends.

### 4.8 Challenging Cases

Include cases whose surface signals (badges, active history, extensive
manifests, large README) do not match their deeper engineering state.
Section 11 defines the challenging-case criteria. The dataset must contain
at least one intentionally challenging case.

### 4.9 Licensing

Candidates must have licenses compatible with our evaluation use: cloning,
inspecting, and deriving assessment evidence. Candidates with unclear or
restrictive licenses are excluded. The recorded license and its evaluated
compatibility are part of the case metadata.

### 4.10 Selection Procedure

- Identify candidates satisfying 4.1 to 4.9.
- Record the tier intent, the screening outcome for each criterion, and the
  licensing check for every selected and rejected candidate.
- Select the final 12 and record the actual tier distribution.
- Selection decisions are documented so replacement and review are
  possible.

## 5. Repository Snapshots

### 5.1 Immutable Snapshots

Every evaluation case references an **immutable snapshot** of the
repository at a fixed point, preferably a specific Git commit SHA.

- Moving heads (branch heads, `main`, `master`) must never be evaluated.
- Each case pins one commit; that commit is the complete source of
  evidence for the case.
- The snapshot must be reproducible: cloning the recorded repository at the
  recorded commit must yield the assessed content.

### 5.2 Snapshot Metadata

Each snapshot record contains:

- repository URL and hosting platform
- full commit SHA (the short SHA may be recorded additionally for
  readability, but the full SHA is authoritative)
- branch or tag from which the commit was taken (informational only)
- date the snapshot was created
- repository archive/hash of the snapshot content where practical
- intent of the match (snapshot-to-commit pinning) and any deviations
- rubric version and evaluation protocol version in force at snapshot time

### 5.3 Snapshot Change Policy

If a repository's snapshot must change (for example, the source becomes
unavailable), a new case with a new snapshot is created; the original case
is archived and kept for result traceability. Existing results must retain
their link to the exact snapshot they were produced from.

## 6. Ground Truth

Ground truth is the human-produced, rubric-scored assessment of each
snapshot. It is the reference that system rankings are compared against.

### 6.1 Human Reviewers Only

Ground truth is produced **by qualified human reviewers** using the
canonical rubric. An LLM is never used to produce ground truth. LLM output
is always the object of evaluation, never the reference.

### 6.2 Reviewer Qualification and Independence

- Reviewers are practicing engineers with software maintenance/review
  experience.
- Before scoring cases, each reviewer must complete a rubric calibration
  pass on a pilot snapshot so that rubric-anchor usage is consistent.
- Reviewers score independently: each reviewer records their full scoring
  for a case **before** seeing other reviewers' scores or case metadata.
- Reviewers do not select the repositories they are asked to score, and
  they are not told the intended tier of a case.

### 6.3 Review Procedure

Reviewers follow the Repeatable Reviewer Procedure (Section 7) for each
case and score every criterion of the rubric with the evidence statuses
FOUND, NOT_FOUND, UNCERTAIN, NOT_APPLICABLE from the rubric's Section 3.

### 6.4 Evidence Requirements

Reviewer scores must satisfy the rubric's evidence requirements:
- every criterion score carries a status and citations to concrete
  evidence (path and line range, command output, or artifact reference);
- scores are status-bounded as defined in the rubric (`rubric 3.5`);
- missing evidence is recorded as NOT_FOUND and never re-interpreted as
  positive evidence;
- unsupported claims are recorded as UNCERTAIN and never raise a score.

### 6.5 Scoring Procedure

- Score every applicable criterion of all five dimensions on the 0-4
  scale.
- Compute dimension scores and the aggregate as defined in the rubric
  Section 6 (`earned`, `possible`, `score`).
- Produce a per-criterion scoring sheet with evidence citations.
- Record review time spent; this is the human review time referenced in
  the secondary metrics (Section 9.2), measured without a target or
  limit.

### 6.6 Handling Disagreement

- After independent scoring, reviewers compare sheets for a case.
- Disagreement is defined as: a difference of more than 1 point on any
  criterion, or a difference of more than 5 points in the aggregate score.
- Disputed criteria are discussed against the cited evidence. If the
  discussion surfaces new evidence, both reviewers re-check their score;
  the recorded evidence may be extended but existing citations may not be
  deleted to force agreement.
- If no consensus is reached, a third qualified reviewer adjudicates, also
  scoring independently and citing evidence.
- If disagreement remains after adjudication, the case is recorded as
  **contested** and kept in the dataset with all individual scores
  retained; a contested case is flagged in results. It is excluded from
  primary-metric comparisons only when its inclusion could change the
  measured agreement, and the exclusion decision is itself recorded.

### 6.7 Aggregation and Consensus

- The consensus score is the ground truth for the case. When reviewers
  agree on a criterion, that score stands; when adjudicated, the
  adjudicator's score stands.
- Individual reviewer scores are retained alongside the consensus for
  auditability.
- The ground-truth ranking of the dataset is derived from consensus total
  scores, ordered descending. Ties keep equal rank; the exact tie handling
  in the primary metric is specified by the evaluation runner.

### 6.8 Reviewer Anonymity and Blinding

- Reviewers are identified only by anonymous reviewer IDs in stored data
  and results.
- Reviewers are blinded to: the intended tier of a case, the set of other
  repositories in the dataset where practical, and all system results.
- Published or shared results do not attribute individual reviewers.

## 7. Reviewer Procedure

This is the repeatable inspection procedure a reviewer follows for every
case. It inspects representative evidence; it does not require reading
every line of large repositories.

### 7.1 Inspection Stages

1. **Snapshot orientation.** Confirm the snapshot identity (Section 5.2)
   and the rubric version in use.
2. **Top-level structure.** Read the directory tree; note organization,
   separation of concerns, and where source, tests, docs, and
   configuration live (Architecture - Project organization).
3. **README and status.** Read the README and any top-level status
   documents (Documentation criteria).
4. **Dependency manifests and lockfiles.** Inspect manifests and lockfiles
   for hygiene, version management, and necessity. Record any claimed
   vulnerability checks and supply-chain signals (Dependencies criteria).
5. **Build, CI, and configuration.** Inspect build files, CI workflows, and
   configuration for reproducibility and consistency with the README.
6. **Representative source.** Inspect entry points, core domain logic, and
   a representative sample of modules (Section 7.2). Assess Architecture
   and Maintainability criteria from this evidence.
7. **Tests.** Inspect test presence, organization, unit vs integration, and
   failure-path coverage (Testing criteria).
8. **Documentation beyond README.** Inspect architecture docs, interface
   docs, and developer docs (remaining Documentation criteria).
9. **Score and record.** Produce the scoring sheet with statuses and
   evidence citations, following Section 6.5.

### 7.2 Sampling Large Repositories

- Small repositories may be inspected thoroughly.
- For large repositories, the reviewer samples systematically rather than
  exhaustively: first inspect breadth (structure, manifests, CI, docs),
  then select representative modules that include the entry point, the
  core domain logic, and modules chosen to span the top-level layout.
- The reviewer records the list of files actually inspected so the sample
  is reproducible and auditable.
- A reviewer must not be required to read every line of a repository; the
  recorded evidence reflects the sample inspected.

### 7.3 Recording

Every review records the reviewer ID, snapshot identity, rubric version,
inspection stage results, inspected-file list, per-criterion scores with
statuses and citations, aggregate values, time spent, and any uncertainties
or contested criteria.

## 8. Baseline

### 8.1 Definition

The baseline is a deliberately simple **single-LLM assessment** that scores
the same canonical rubric (version 1.0) over the same evaluation
repositories as RepoGuard.

- It is a single-pass model assessment using the rubric and the snapshot
  evidence; it is not an agent and has no multi-stage orchestration.
- Its design intent is fixed here; its exact configuration (model, prompt)
  is recorded per run like any other system (Section 12).

### 8.2 Deliberate Simplicity

The baseline exists to answer one question: does RepoGuard's added
complexity improve outcomes over a plain, single-LLM rubric scoring? It must
therefore be held to the simplest reasonable construction that can produce
a rubric-scored assessment.

### 8.3 Same Conditions as RepoGuard

The baseline must run under the same conditions as RepoGuard (Section 10):
same snapshots, same rubric version, same cases, and comparable repository
evidence. Its results are recorded separately from RepoGuard's.

## 9. Metrics

### 9.1 Primary Metric

The primary evaluation objective is **agreement between the system's
ranking and the human ground-truth ranking** of the evaluation cases.

- The system produces a ranking; the ground truth produces a ranking
  (Section 6.7).
- Agreement is measured by a rank-correlation-style statistic over the
  dataset.
- The exact statistical implementation (statistic choice, tie handling,
  confidence treatment, and any per-tier breakdown) is **specified by the
  evaluation runner**, not by this protocol, so the choice is made where
  the measurement code lives and can itself be evaluated.

### 9.2 Secondary Metrics

Six secondary metrics are recorded. They are measurements; no target
performance numbers are set here.

- **Evidence accuracy.** The fraction of system-cited evidence claims that
  verify against the snapshot. Unverifiable citations lower accuracy.
- **Critical finding recall.** The fraction of human-flagged critical
  findings (material problems or risks) that the system reports.
- **False-positive rate.** The fraction of system-reported findings that
  are not supported by snapshot evidence.
- **Assessment time.** Wall-clock time the system takes to produce an
  assessment (and, separately, human review time, recorded per Section
  6.5).
- **Runtime.** Compute resources consumed by the evaluation run.
- **Approximate cost.** The estimated model/API cost of the run.

### 9.3 No Invented Targets

This protocol sets no target values for any metric. Thresholds and
accept/reject decisions are produced by measuring actual runs, starting
with the baseline, on the locked dataset.

## 10. Fair Comparison

Baseline and RepoGuard must be compared under identical conditions:

1. **Same repository snapshots.** Both systems evaluate the same pinned
   commits (Section 5).
2. **Same rubric version.** Both use the same canonical rubric version for
   scoring.
3. **Same evaluation cases.** Both run over the identical case set.
4. **Comparable repository evidence.** Both receive the same snapshot
   content; neither receives ground truth, other system's output, or
   privileged information.
5. **Results recorded separately.** Baseline and RepoGuard results are
   stored in separate, clearly labeled artifacts.
6. **No modification based on results.** Evaluation cases and ground truth
   are never modified to improve results (AGENTS.md "Evaluation").

## 11. Challenging Case

An intentionally challenging case is one whose **superficial positive
signals mask deeper engineering problems**. Signals that can mislead
include:

- a polished README and active commit history despite absent or misleading
  documentation elsewhere;
- heavy dependency and configuration presence that hides dependency
  hygiene or necessity problems;
- a large test suite that does not cover the core logic or failure paths;
- a well-structured front or entry surface around a tangled core.

Rules:

- At least one case in the dataset is intentionally challenging.
- Reviewers are not told that a case is challenging, and scoring remains
  rubric- and evidence-based.
- A case is deceptively challenging only in the sense defined here; no
  case is constructed to be unassessable.

## 12. Reproducibility

Every evaluation run must record a **run manifest** that allows the run to
be reproduced:

- repository commit (full SHA) per case
- rubric version
- model identifiers and model configuration used
- prompts/configuration used (prompt text or references to prompt artifacts)
- environment: runner/package versions, Python version, OS
- evaluation timestamp
- result artifact locations

The manifest is stored with the results and is considered part of the
result (Section 13). A run without a complete manifest is not considered
published.

## 13. Results

### 13.1 Result Structure

Results are defined so that an automated runner can consume them later; the
runner is not implemented by this protocol. Each run produces artifacts
containing:

- run identity: system id (`repoGuard` or `baseline`), run id, timestamp,
  manifest reference (Section 12)
- per-case outcome: snapshot identity, rubric version, per-criterion
  scores with statuses, aggregate `earned`/`possible`/`score` (rubric
  Section 6), system ranking
- findings: each finding with claim text, evidence citation, and severity
- metrics: primary statistic as defined by the runner, and the secondary
  metrics of Section 9.2
- ground-truth reference: case ids and consensus scores used (read-only
  reference; ground truth is never modified by a run)

### 13.2 Storage

- Ground truth lives under `evaluation/` and is stored separately from
  system results so runs can never mutate it.
- System results live under `evaluation/results/`, one directory per run,
  with baseline and RepoGuard outputs separated.
- Local/in-progress artifacts are not committed (see `.gitignore`); only
  finalized, manifest-complete results enter the repository.

## 14. Protocol Changes

This protocol is versioned. Any change that affects comparison validity
(rubric version, snapshot set, ground truth, metric definition, or evidence
rules) requires:

1. a decision record documenting the change;
2. re-affirmation or re-run of affected comparisons against the same
   evaluation cases;
3. recording of the protocol version in every affected artifact.

## 15. Out of Scope

The following are deliberately out of scope for this document:

- selection of actual repositories (a future dataset issue, using
  Section 4);
- implementation of the evaluation runner (a future issue, using Sections
  9 and 13);
- implementation of the baseline (a future issue, using Section 8);
- implementation of RepoGuard analysis or agent logic (a future issue,
  using the rubric and this protocol).

Each of these must reproduce the conditions defined here and never modify
evaluation cases or ground truth to improve results.