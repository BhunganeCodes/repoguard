# RepoGuard Candidate Registry

This directory holds the **candidate registry** for the RepoGuard
evaluation.

It contains candidate repositories only. It is **not** the official
evaluation dataset.

## Purpose

The registry tracks repositories being researched for potential inclusion
in the evaluation dataset, as defined in the evaluation protocol
(`docs/evaluation.md`, Section 4). It is the working list used during the
screening phase before official evaluation cases are created.

Official dataset cases, ground truth, and system results are handled in
later stages and must not appear here.

## What This Registry Is Not

This registry must never contain:

- quality scores
- ground-truth scores
- strong / average / weak / challenging classification
- reviewer results
- system results

Those belong to later stages: dataset curation, ground-truth production,
and evaluation runs.

## Entry Schema

Each candidate entry in `registry.yaml` supports the following fields.

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Stable candidate identifier, a slug of the form `<project>-<repo>` (for example `sqlite-sqlite`). |
| `name` | yes | Repository name. |
| `url` | yes | GitHub URL (`https://github.com/<owner>/<repo>`). |
| `ecosystem` | yes | Primary ecosystem/language (for example `python`, `go`, `javascript`). |
| `license` | conditional | SPDX license identifier. Mark `pending` until verified against the repository. |
| `size_category` | conditional | Approximate size category: `small`, `medium`, or `large`. Mark `pending` when unknown. |
| `discovery` | optional | How the candidate was found (source notes). |
| `rationale` | optional | Selection rationale, mapped to the screening criteria in `docs/evaluation.md` Section 4. |
| `screening_status` | yes | One of the statuses below. |
| `screening` | conditional | Screening evidence block, present once screened. See below. |

### Screening Evidence Block

| Field | Description |
|-------|-------------|
| `head_commit` | Full commit SHA of the repository's default-branch HEAD at the screening date. A snapshot candidate, not an official case. |
| `source` | `present` or `absent` (source code in the tracked tree). |
| `tests` | `present` or `absent` (test suites/files in the tracked tree). |
| `documentation` | `present` or `absent` (README/docs in the tracked tree). |
| `dependency_manifests` | `present` or `absent` (manifest such as `go.mod`, `Cargo.toml`, `package.json`, `pyproject.toml`, `pom.xml`). |
| `lockfiles` | `present` or `absent` (locked dependency file when the ecosystem uses one). |
| `ci` | `present` or `absent` (CI/automation config in the tracked tree). |
| `decision` | Concise mechanical reason for the eligibility/rejection decision. |
| `concerns` | Mechanical risks or notes requiring human attention, or `none`. |

Presence fields are facts about the repository tree; they are not quality
judgments.

Only metadata that has been verified may be recorded. Anything unverified
is recorded as `pending` or omitted; no value is invented.

## Metadata Conventions

- `license` is a verified SPDX identifier obtained from the GitHub REST
  API and/or a shallow metadata clone (no full clone required). `null`
  means no license file was detected; `pending` means the value could not
  be verified. When no LICENSE file exists but the repository declares a
  license in its own metadata (for example the README), the declared
  license is recorded and flagged in the `screening.concerns` field for
  human confirmation.
- `size_category` is derived from the GitHub-reported repository size:
  `small` (< 2 MB), `medium` (2-20 MB), `large` (> 20 MB).
- `discovery` and `rationale` contain the engineering team's notes and are
  recorded as `pending` until those notes are available.
- The `registry.yaml` header records the source and date of verified
  metadata.

## Screening Statuses

| Status | Meaning |
|--------|---------|
| `screening` | Being researched; not yet assessed against the selection criteria. |
| `eligible` | Passed preliminary screening; meets the criteria assessed so far. |
| `rejected` | Does not meet the selection criteria or licensing requirements. |
| `shortlisted` | Eligible and selected for closer review as a dataset candidate. |

Status transitions follow the selection procedure in
`docs/evaluation.md` Section 4.

## Current State

Twelve candidates (C001-C012) were mechanically screened on 2026-08-28 via
GitHub metadata and shallow metadata clones. All are marked `eligible`;
none are `rejected`. Screening evidence, including a recorded default-branch
head commit per candidate, is in `registry.yaml`.

No official evaluation cases exist yet. Shortlisting and final dataset
selection are separate, later steps.