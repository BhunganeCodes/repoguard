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
- Docker (optional; required for the Docker Compose workflow)
- Git

### Setup

Install the project with dev dependencies into a virtual environment:

```bash
./scripts/setup.sh        # bash / Linux / macOS
.\scripts\setup.ps1       # Windows PowerShell
```

or:

```bash
make install
```

### Run the API

The run scripts detect whether Docker is available. If it is, the
application starts via Docker Compose. Otherwise it runs locally with
uvicorn.

```bash
./scripts/run.sh          # bash / Linux / macOS
.\scripts\run.ps1         # Windows PowerShell
```

or:

```bash
make run                  # local
make docker-up            # Docker Compose
```

The API listens on port 8000. Health check:

    GET /health

Expected response:

```json
{
  "status": "healthy"
}
```

### Tests

```bash
./scripts/test.sh         # bash / Linux / macOS
.\scripts\test.ps1        # Windows PowerShell
```

or:

```bash
make test
```

### Quality gates

```bash
make lint          # Ruff lint
make format-check  # Ruff format check
make typecheck     # mypy
make test          # pytest
```

## Project Structure

```text
app/repoguard/    FastAPI application
  api/            HTTP layer
  agents/         agent orchestration (future)
  analysis/       repository analysis (future)
  evaluation/     evaluation framework (future)
  models/         data models
  services/       domain services
tests/            unit and integration tests
evaluation/       evaluation cases, datasets, results
docs/decisions/   architecture decision records
scripts/          cross-platform development scripts
.github/          CI and issue templates
```