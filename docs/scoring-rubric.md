# RepoGuard Scoring Rubric

This document is the canonical specification for how RepoGuard scores the
engineering quality of a software repository.

It is a specification only. It does not describe the repository analyzer,
the LLM agents, or any scoring implementation. Those will be built against
this rubric and evaluated separately.

## Status

Canonical, version 1.0.

The five dimensions, their weights, and the per-criterion scoring anchors
are fixed. Any change to this rubric must be approved through a documented
decision record and must be applied consistently to all evaluation cases
used for before/after comparisons.

## 1. Scoring Model

RepoGuard scores repositories on five equally weighted dimensions. Each
dimension contributes 20 points, and each is made up of five criteria worth
4 points each.

| Dimension | Weight | Criteria | Points per criterion | Maximum |
|-----------|--------|----------|----------------------|---------|
| Architecture | 20 | 5 | 4 | 20 |
| Testing | 20 | 5 | 4 | 20 |
| Maintainability | 20 | 5 | 4 | 20 |
| Dependencies | 20 | 5 | 4 | 20 |
| Documentation | 20 | 5 | 4 | 20 |
| **Total** | **100** | **25** | | **100** |

Every criterion is scored on the same fixed 0-4 scale defined in
Section 4.

## 2. General Principles

1. **Evidence-first.** A criterion is scored only from repository evidence.
   Scores are not opinions; they are summaries of cited evidence.
2. **Status-gated.** Every criterion is first assigned an evidence status
   (FOUND, NOT_FOUND, UNCERTAIN, or NOT_APPLICABLE). The status bounds the
   score that the anchors may produce.
3. **Reproducible.** Two assessors examining the same evidence must be able
   to arrive at the same status, score, and rationale.
4. **No fabrication.** Claims without traceable evidence are not admissible
   (see AGENTS.md "Evidence").
5. **Absence is a finding.** Missing evidence is recorded as NOT_FOUND; it
   must never be reinterpreted as positive evidence for the same or any
   other criterion.

## 3. Evidence

### 3.1 What Counts as Evidence

Admissible evidence includes:

- source code and configuration under the repository
- tests and test configuration
- dependency manifests and lockfiles
- build and CI configuration and reproducible CI/branch status
- documentation within the repository
- observed, reproduced behavior (only when reproducible and recorded)
- caretaker-supplied, verifiable external artifacts (for example, a public
  audit report), when the source is identified

Every evidence item must be cited by a concrete reference: a file path and
line range, a command and its output, or an artifact reference. Unlocatable
evidence does not count.

### 3.2 Evidence Statuses

| Status | Meaning | When to use |
|--------|---------|-------------|
| FOUND | Verifiable evidence located that directly supports the criterion | Evidence is present, readable, and consistent |
| NOT_FOUND | A deliberate, documented search produced no evidence for the criterion | The criterion is relevant but no evidence exists in scope |
| UNCERTAIN | Evidence is partial, ambiguous, inconsistent, or cannot be verified | Evidence exists but is insufficient to confirm the criterion confidently |
| NOT_APPLICABLE | The criterion does not apply to this repository | The criterion is genuinely irrelevant; requires justification and evidence |

### 3.3 Handling Missing Evidence

- A criterion assigned **NOT_FOUND** scores 0 and is recorded as such.
- Missing evidence must not be replaced by assumptions.
- If evidence could not be collected within the assessment scope (for
  example, private CI history), the criterion is **UNCERTAIN** with the
  limitation recorded - it is not FOUND and not NOT_FOUND.
- Absence of evidence for one criterion never contributes to the score of
  another criterion.

### 3.4 Handling Unsupported Claims

- An unsupported claim is a positive assertion about the repository that
  cannot be traced to evidence. Unsupported claims are not admissible.
- If every positive claim supporting a criterion is unsupported, the
  criterion scores 0 with status **UNCERTAIN (unsupported)**.
- If only part of the supporting evidence is unsupported, the criterion is
  **UNCERTAIN** and may not score above 2.
- Uncertain or unsupported findings must appear in the assessment report so
  a reader can distinguish them from verified findings.

### 3.5 Status to Score Mapping

| Status | Allowed score |
|--------|---------------|
| FOUND | 0-4, per the anchors |
| UNCERTAIN | 0-2; 0 if the positive evidence is entirely unsupported |
| NOT_FOUND | 0 |
| NOT_APPLICABLE | Excluded from the score calculation, with justification |

## 4. The Four-Point Scale

Each criterion is measured against the same five anchors:

| Score | Anchor |
|-------|--------|
| 4 | **Strong.** The criterion is met to a high standard. Direct, verifiable evidence is present and there are no material gaps. |
| 3 | **Good.** The criterion is met, with minor and documented gaps. |
| 2 | **Partial.** The criterion is only partially met; evidence is mixed or covers part of the criterion only. |
| 1 | **Weak.** Minimal satisfaction; substantial gaps or mostly negative evidence. |
| 0 | **Absent.** No evidence the criterion is met, or the supporting claims are unsupported. |

The dimension-specific tables in Section 5 express each anchor in terms of
the evidence an assessor should look for.

## 5. Dimensions, Criteria, and Anchors

### 5.1 Architecture

#### Architecture - Project organization

| Score | Anchor |
|-------|--------|
| 4 | Layout is conventional and consistent: source, tests, configuration, and documentation are clearly separated; navigation is obvious. |
| 3 | Layout is consistent with minor deviations that are easy to navigate around. |
| 2 | A layout exists but mixes concerns or is internally inconsistent. |
| 1 | Layout is ad hoc; little structure is apparent. |
| 0 | No discernible organization of the repository. |

#### Architecture - Separation of responsibilities

| Score | Anchor |
|-------|--------|
| 4 | Modules and layers have single, distinct responsibilities; responsibilities do not bleed across boundaries. |
| 3 | Clear separation with occasional, small cross-boundary leak. |
| 2 | Some separation, but responsibilities are blurred or oversized modules exist. |
| 1 | Dominant "god" modules or layers that mix unrelated concerns. |
| 0 | Responsibilities are not separated at all. |

#### Architecture - Dependency direction

| Score | Anchor |
|-------|--------|
| 4 | Dependencies flow from high-level toward stable, low-level modules; no dependency cycles. |
| 3 | Generally clean direction with one or two minor exceptions. |
| 2 | Direction is inconsistent; some cycles or high-level modules depending on concrete internals. |
| 1 | Frequent cycles or layers that depend on the wrong side of the boundary. |
| 0 | Dependency structure is tangled; no clear direction. |

#### Architecture - Coupling and complexity

| Score | Anchor |
|-------|--------|
| 4 | Modules/systems are loosely coupled and individually simple; interfaces are narrow and stable. |
| 3 | Low coupling and complexity with minor hotspots. |
| 2 | Noticeable coupling or complexity concentrated in a few modules. |
| 1 | High coupling or large complex modules with few clear seams. |
| 0 | Everything depends on everything; complexity is unbounded. |

#### Architecture - Extensibility

| Score | Anchor |
|-------|--------|
| 4 | Adding or changing behavior is localized; extension points exist and are documented. |
| 3 | Extensible with some effort; seams exist though not documented. |
| 2 | Extension requires touching multiple unrelated places. |
| 1 | The structure resists extension; changes ripple widely. |
| 0 | No discernible way to extend behavior. |

### 5.2 Testing

#### Testing - Test presence

| Score | Anchor |
|-------|--------|
| 4 | Tests exist for the substantial majority of production code paths. |
| 3 | Tests exist for most production modules, with a few gaps. |
| 2 | Tests exist for some modules only. |
| 1 | Few tests relative to the size of the codebase. |
| 0 | No tests found. |

#### Testing - Test organization

| Score | Anchor |
|-------|--------|
| 4 | Tests are structured, named consistently, mirror the source layout, and run via a documented command. |
| 3 | Tests are organized with minor inconsistencies; a documented command exists. |
| 2 | Tests run but organization is inconsistent or not documented. |
| 1 | Tests exist but there is no clear way to discover or run them. |
| 0 | No test organization. |

#### Testing - Unit testing

| Score | Anchor |
|-------|--------|
| 4 | Unit tests isolate components, are fast and deterministic, and cover logic directly. |
| 3 | Unit tests exist and are mostly isolated, with minor coupling to environment. |
| 2 | Tests run against logic but rely on shared state or external services. |
| 1 | Tests are slow, order-dependent, or weakly assert behavior. |
| 0 | No unit-level tests. |

#### Testing - Integration testing

| Score | Anchor |
|-------|--------|
| 4 | Integration tests exercise real workflows across components; any mocks are justified. |
| 3 | Integration tests cover the main workflows, with some paths untested. |
| 2 | Some integration coverage, but shallow or heavily mocked. |
| 1 | Integration tests are nominal and do not exercise real interactions. |
| 0 | No integration tests. |

#### Testing - Failure-path coverage

| Score | Anchor |
|-------|--------|
| 4 | Errors, invalid inputs, and boundary conditions are explicitly tested, not only happy paths. |
| 3 | Failure paths are covered with modest gaps. |
| 2 | A few failure paths are covered; most tests are happy-path only. |
| 1 | Failure handling exists in code but is untested. |
| 0 | No failure-path tests. |

### 5.3 Maintainability

#### Maintainability - Code readability

| Score | Anchor |
|-------|--------|
| 4 | Naming is clear, functions are small, control flow is straightforward, and style is consistent. |
| 3 | Readable with a few unclear spots. |
| 2 | Mixed quality; some names or flows require effort to follow. |
| 1 | Code is generally hard to read; conventions inconsistent. |
| 0 | Code is effectively unreadable. |

#### Maintainability - Complexity

| Score | Anchor |
|-------|--------|
| 4 | Control flow and data structures are simple; complexity is bounded and local. |
| 3 | Generally simple with occasional deep nesting. |
| 2 | Several complex, hard-to-follow sections. |
| 1 | Pervasive complexity; deeply nested or convoluted logic. |
| 0 | Complexity is unbounded. |

#### Maintainability - Duplication

| Score | Anchor |
|-------|--------|
| 4 | Shared logic is extracted; no meaningful duplication. |
| 3 | Minor, acceptable duplication. |
| 2 | Noticeable duplicated logic copied across modules. |
| 1 | Substantial duplication; the same logic appears in many places. |
| 0 | Duplication is pervasive. |

#### Maintainability - Error handling

| Score | Anchor |
|-------|--------|
| 4 | Errors are handled consistently; failure modes are predictable; silent failures are absent. |
| 3 | Consistent handling with minor gaps. |
| 2 | Errors are handled unevenly; some failures are swallowed or obscure. |
| 1 | Most failure paths are unhandled or misreported. |
| 0 | Failure modes are unpredictable or ignored. |

#### Maintainability - Technical debt

| Score | Anchor |
|-------|--------|
| 4 | No accumulating TODO/FIXME/hack markers; debt is tracked and documented if present. |
| 3 | Little debt; markers are few and explained. |
| 2 | Visible markers or shortcuts scattered through the code. |
| 1 | Significant shortcuts with no tracking. |
| 0 | Debt is pervasive and unmanaged. |

### 5.4 Dependencies

#### Dependencies - Dependency hygiene

| Score | Anchor |
|-------|--------|
| 4 | Dependency set is minimal and appropriate for the stack; no unused or duplicated dependencies. |
| 3 | Mostly clean with a few minor extras. |
| 2 | Several unnecessary or duplicated dependencies. |
| 1 | Many dependencies that appear unused or overlapping. |
| 0 | No dependency discipline. |

#### Dependencies - Version management

| Score | Anchor |
|-------|--------|
| 4 | Versions are pinned or locked; installs are reproducible from committed manifests. |
| 3 | Versions specified with minor looseness; installs are practically reproducible. |
| 2 | Versions are loosely specified or the manifest is incomplete. |
| 1 | Versions are unpinned; installs vary. |
| 0 | No version management. |

#### Dependencies - Dependency necessity

| Score | Anchor |
|-------|--------|
| 4 | Each dependency is justified by actual use; no "just in case" additions. |
| 3 | Nearly all dependencies are justified by use. |
| 2 | Some dependencies lack evident justification. |
| 1 | Many dependencies cannot be tied to actual use. |
| 0 | Dependencies are added without justification. |

#### Dependencies - Vulnerability and risk awareness

| Score | Anchor |
|-------|--------|
| 4 | Known vulnerabilities are checked; risks are documented with remediation or a recorded decision. |
| 3 | Checks exist with some findings undocumented. |
| 2 | Checks exist but findings are not assessed. |
| 1 | Risk is never checked. |
| 0 | Dependencies are used with no risk information at all. |

#### Dependencies - Supply-chain discipline

| Score | Anchor |
|-------|--------|
| 4 | Sources are trusted and identified; integrity/pinning is in place; no unvetted fetched code. |
| 3 | Good discipline with minor gaps. |
| 2 | Mixed practices; some untrusted or unvetted sources. |
| 1 | Fetched code is largely unvetted. |
| 0 | No supply-chain discipline. |

### 5.5 Documentation

#### Documentation - README

| Score | Anchor |
|-------|--------|
| 4 | README states the project's purpose, current status, usage, and points to further docs. |
| 3 | README is useful with minor omissions. |
| 2 | README exists but is thin or partly stale. |
| 1 | README exists but is misleading or substantially incomplete. |
| 0 | No README. |

#### Documentation - Installation and execution

| Score | Anchor |
|-------|--------|
| 4 | Setup, install, and run instructions are complete and accurate; defaults match reality. |
| 3 | Instructions are correct with minor gaps. |
| 2 | Instructions are incomplete or partially outdated. |
| 1 | Instructions exist but do not work or are misleading. |
| 0 | No installation or execution instructions. |

#### Documentation - Architecture documentation

| Score | Anchor |
|-------|--------|
| 4 | Design, components, decisions (for example decision records), and key flows are documented and current. |
| 3 | Architecture documented with minor gaps. |
| 2 | Partial documentation; some major components undocumented. |
| 1 | Documentation is nominal or far out of date. |
| 0 | No architecture documentation. |

#### Documentation - API or interface documentation

| Score | Anchor |
|-------|--------|
| 4 | Public interfaces/endpoints are documented with contracts and examples. |
| 3 | Interfaces documented with minor gaps or missing examples. |
| 2 | Some interfaces documented; others undocumented. |
| 1 | Only trivial or inconsistent interface documentation. |
| 0 | No API or interface documentation. |

#### Documentation - Developer documentation

| Score | Anchor |
|-------|--------|
| 4 | Contribution flow, environment setup, testing, and coding standards are documented. |
| 3 | Developer docs exist with minor omissions. |
| 2 | Partial developer docs; key processes undocumented. |
| 1 | Developer documentation is nominal or stale. |
| 0 | No developer documentation. |

## 6. Overall Score Calculation

### 6.1 Dimension Score

Each dimension scores 0-20:

    dimension_score = sum of the scores of its (applicable) criteria

A criterion marked NOT_APPLICABLE is excluded from the dimension sum and
must carry a recorded justification.

### 6.2 Aggregate Score

    earned   = sum of all five dimension scores
    possible = 100 - (4 x number of NOT_APPLICABLE criteria)
    score    = (earned / possible) x 100

- When there are no NOT_APPLICABLE criteria, `possible` is 100 and the
  score equals `earned`.
- The reported score is rounded to one decimal place (0.05 rounds up).
- If `possible` is 0, the repository is not scoreable and no single
  number is reported; the report lists the applicable criteria instead.

### 6.3 Reporting Requirements

The assessment report must record, for every criterion:

- dimension and criterion
- evidence status (FOUND, NOT_FOUND, UNCERTAIN, NOT_APPLICABLE)
- score on the 0-4 scale
- citations of the supporting evidence
- a note when the criterion was limited by missing or unsupported evidence

The report must also record:

- justification and evidence for every NOT_APPLICABLE criterion
- the list of UNCERTAIN criteria and why
- `earned`, `possible`, and the final `score` as defined in 6.2

A reproducible report must include enough citation so a second assessor can
confirm or refute each score without new judgment.

## 7. Relationship to the Evaluation Framework

Evaluation cases (under `evaluation/cases/`) will be scored against this
canonical rubric. Ground truth used for measuring RepoGuard performance must
use this rubric and must not be altered to improve results (see AGENTS.md
"Evaluation"). Changes to the rubric therefore invalidate prior evaluation
comparisons and require re-scoring the affected cases with the same rubric
version.