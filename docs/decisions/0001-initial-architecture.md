# ADR 0001: Initial Architecture

## Status

Accepted

## Context

RepoGuard must be developed within a three-day hackathon while remaining
testable, reproducible and extensible.

The final agent architecture is not yet known.

## Decision

We will begin with a modular Python application using:

- FastAPI
- Pydantic
- pytest
- Ruff
- mypy
- Docker

The initial architecture will not depend on a specific agent framework.

We will establish a simple baseline before introducing additional agent
orchestration.

## Rationale

This minimizes premature architectural commitments and allows agent
architecture to evolve according to evaluation results.

## Consequences

Positive:

- Fast initial development
- Small dependency surface
- Easier testing
- Easier experimentation
- Reduced framework lock-in

Negative:

- Some agent infrastructure will need to be implemented later
- Architecture may change as experiments reveal requirements