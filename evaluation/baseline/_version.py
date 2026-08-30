"""Version and identity scheme for the baseline subsystem."""

__version__ = "0.1.0"

# Scheme prefix used when hashing a baseline result's content identity.
RESULT_SCHEME = "repoguard-baseline-v1"

# Schema version of the baseline result artifact.
RESULT_SCHEMA_VERSION = 1

# Immutable identifier of the system producing results (docs/evaluation.md
# Section 8.1). Distinct from RepoGuard's own system id.
SYSTEM_ID = "baseline"
