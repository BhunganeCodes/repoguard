# RepoGuard Snapshot Acquisition

The snapshot subsystem turns a frozen dataset entry (repository URL + pinned
commit SHA) into a deterministic, immutable, evidence-only snapshot plus a
machine-readable repository inventory.

It implements Section 5 of `docs/evaluation.md` (Immutable Snapshots). It is
**not** an evaluator: no quality scores, no ground truth, and no LLM logic
live here.

## Architecture

```
evaluation/
  snapshot/                  # snapshot subsystem (this code)
    __main__.py              # python -m evaluation.snapshot
    cli.py                   # command-line interface
    acquire.py               # acquisition orchestration
    git.py                   # pin-safe git operations (subprocess)
    hashing.py               # deterministic content hash
    inventory.py             # machine-readable inventory generation
    manifest.py              # frozen dataset manifest parsing/validation
    models.py                # dataclasses for records and inventory
    commits.py               # commit SHA validation + identity constant
    errors.py                # typed failures (fail-closed)
    paths.py                 # snapshot store layout
  snapshots/                 # LOCAL snapshot store (gitignored)
    <candidate_id>-<name>/
      snapshot.yaml          # immutable acquisition record
      inventory.yaml         # machine-readable repository inventory
      checkout/              # git worktree at the pinned commit
  datasets/                  # frozen dataset manifests (inputs)
```

The subsystem is a plain Python package importable from the repo root
(`python -m evaluation.snapshot`). It depends only on the standard library
plus PyYAML for manifest/record parsing.

## Snapshot lifecycle

1. **Freeze.** The dataset manifest (`evaluation/datasets/dataset-v1.0.0.yaml`)
   records candidate ID, repository URL, and pinned commit SHA.
2. **Acquire.** The CLI/API fetches exactly the pinned commit, checks it out
   detached, verifies the resolved HEAD strictly equals the requested SHA,
   computes the content hash, and writes `snapshot.yaml` + `inventory.yaml`.
3. **Freeze-in-place.** A completed snapshot is immutable: it is written once
   and never moved. Requesting a different commit for an existing snapshot
   raises `SnapshotExistsError` instead of overwriting. Failed acquisitions
   are removed entirely (no partial directories survive).
4. **Inspect / verify.** `inspect --verify` re-hashes the checked-out tree and
   re-checks HEAD against the recorded commit to confirm the stored snapshot
   is intact.

## CLI usage

Run from the repository root:

```sh
# 1. Snapshot one case from the frozen dataset.
python -m evaluation.snapshot one --manifest evaluation/datasets/dataset-v1.0.0.yaml --case C001

# 2. Snapshot every included repository in the frozen dataset.
python -m evaluation.snapshot dataset --manifest evaluation/datasets/dataset-v1.0.0.yaml

# 3. Inspect an existing snapshot (add --verify to re-hash and re-verify).
python -m evaluation.snapshot inspect --snapshot evaluation/snapshots/C001-gosim --verify
```

The manifest and store arguments default to the frozen dataset and
`evaluation/snapshots/`. Output on stdout is YAML; diagnostics go to stderr.
Exit code is zero on full success and nonzero when any case fails (fail
closed). Excluded candidates in the manifest are skipped.

## Security assumptions

Repositories are untrusted input. During acquisition the subsystem:

- fetches and checks out files only (extraction), never reads their contents
  for execution;
- runs **no** repository code: no package install, no build, no tests, no
  shell scripts, no Makefiles, no Dockerfiles, no arbitrary binaries;
- does not invoke repository git hooks, and git operations are pinned to a
  commit SHA (never a moving branch ref);
- writes only under the local snapshot store; the upstream repositories are
  read-only (fetch only, no push, no ref modification).

## Why repository code is not executed

Executing repository code would be (a) a security risk from untrusted
repositories, and (b) a reproducibility risk because builds depend on the
host environment. A snapshot must be content, not side effects. The hash and
inventory are derived purely from the checked-out files, so any reviewer or
analyzer sees the same bytes with no behavioral surprises.

## Reproducibility guarantees

`URL + commit SHA` deterministically produces the same content hash:

- The content hash is a SHA-256 over, for each tracked file in sorted order,
  its relative path, byte length, and full byte content (symlinks contribute
  their link target).
- Excluded from the hash: `.git` metadata, timestamps, temporary files, and
  all local absolute paths. A timestamp is recorded as metadata in
  `snapshot.yaml` and `inventory.yaml` but never affects the hash.
- The hash is prefixed with the identity scheme
  (`repoguard-snapshot-v1`) so future hash-spec changes are distinguishable.
- Re-running acquisition against a fresh store for the same URL + SHA yields
  the identical content hash (tested).
- A snapshot whose resurgent checkout differs from the requested commit is a
  failure, never a silent adjustment.

## Fail-closed behavior

The subsystem raises/aborts when:

- the manifest is missing required fields or is not valid YAML;
- the requested SHA is not a full 40-character hex commit;
- the repository cannot be reached;
- the requested commit does not exist at the remote;
- the checkout resolves to a different SHA than requested;
- the working tree is dirty after checkout;
- the content hash cannot be computed;
- an existing snapshot already holds a different commit.

None of these conditions ever results in "snapshot a different revision and
continue".

## Inventory

`inventory.yaml` contains raw observations only, never scores:

- repository ID, URL, requested and verified commit, content hash, acquisition timestamp
- declared ecosystem (from the manifest) and detected languages (by file extension)
- tracked / approximate source / test / documentation file counts
- presence flags with evidence paths: dependency manifest, lockfile, CI
  configuration, Docker/container configuration, README, license file
- sorted top-level directory listing

## Limitations

- Test detection and language detection are heuristic (filename-based) and
  documented as approximate.
- `--filter=blob:none` (blob-efficient acquisition) is used for `http(s)`
  remotes that advertise filter support, with automatic, still SHA-pinned
  fallback to shallower or full fetches; local/file transports never use the
  filter.
- Submodules are not recursed into; symlink-to-dir and exotic filesystems are
  not special-cased.
- On Windows, symlinks (and therefore the symlink hash test) may be
  unavailable without developer mode privileges.