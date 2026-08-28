# RepoGuard Engineering Instructions

## Project

RepoGuard is an evidence-backed AI system for assessing the engineering
quality of unfamiliar software repositories.

The project is being developed for a hackathon and must prioritize:

1. Correctness
2. Evidence-backed analysis
3. Reproducibility
4. Testability
5. Simplicity
6. Measured improvement

## Core Engineering Principle

Do not add complexity unless an experiment or concrete requirement
justifies it.

The number of agents is not a success metric.

## Architecture

The architecture is intentionally evolutionary.

Do not assume the final multi-agent architecture is fixed.

We will establish a baseline first and introduce additional capabilities
only when evaluation demonstrates a need.

## Evidence

Significant assessment claims must be traceable to repository evidence.

Never fabricate:

- files
- line numbers
- metrics
- test results
- evaluation results
- repository characteristics

If evidence cannot be established, represent the finding as uncertain
or unsupported.

## Evaluation

The evaluation framework is a first-class component of the project.

Never modify evaluation cases to improve results.

Never alter ground-truth data to improve reported performance.

Always use the same evaluation cases when comparing system versions.

## Testing

Every production code change should include appropriate tests.

Do not weaken, remove, or bypass tests merely to make CI pass.

## Git

Never work directly on `main`.

Use:

    feature/<description>

or:

    fix/<description>

Use conventional commits.

Examples:

    feat: add repository scanner
    fix: handle unreadable repository files
    test: add repository scoring tests
    docs: document evaluation methodology
    chore: configure CI

## Security

Never commit:

- API keys
- passwords
- tokens
- private repository contents
- credentials
- `.env` files

Use `.env.example` for configuration documentation.

## Experiments

Every meaningful experiment should document:

1. Hypothesis
2. Change
3. Evaluation method
4. Result
5. Decision
6. Learning

## Before Coding

Before implementing a task:

1. Read the relevant issue.
2. Inspect the existing implementation.
3. Identify affected interfaces.
4. Identify existing tests.
5. Prefer extending existing abstractions over creating duplicates.

## After Coding

Before declaring a task complete:

1. Run tests.
2. Run linting.
3. Run type checking where applicable.
4. Verify the affected functionality.
5. Update documentation where necessary.

## Definition of Done

A task is complete when:

- implementation is complete
- tests exist
- tests pass
- lint passes
- type checking passes where applicable
- documentation is updated where appropriate
- no credentials or secrets are introduced