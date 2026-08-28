# RepoGuard

> Understand an unfamiliar codebase before you trust it.

RepoGuard is an evidence-backed AI system for assessing the engineering
quality of software repositories.

## Status

🚧 Active hackathon development

The project is currently in the foundation and baseline phase.

## Problem

Evaluating an unfamiliar repository requires engineers to manually inspect
source code, tests, dependencies, documentation, configuration and other
engineering signals.

This process can be slow and inconsistent.

RepoGuard aims to turn this evidence into a structured engineering
assessment that can be reviewed and verified by a human.

## Planned Assessment Areas

- Architecture
- Testing
- Maintainability
- Dependencies
- Documentation

## Engineering Approach

RepoGuard is being developed iteratively.

We will establish a simple baseline first and measure its performance
before introducing additional agent capabilities.

Every meaningful architectural change will be evaluated against the same
test cases.

## Development

### Requirements

- Python 3.12+
- Docker (optional)
- Git

### Install

```bash
make install