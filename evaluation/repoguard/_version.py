"""Version and identity scheme for the RepoGuard subsystem."""

__version__ = "0.1.0"

# Scheme prefix used when hashing a RepoGuard result's content identity.
RESULT_SCHEME = "repoguard-v1"

# Schema version of the RepoGuard result artifact.
RESULT_SCHEMA_VERSION = 1

# Immutable identifier of the system producing results (docs/evaluation.md
# Section 8.1 / 13.1). Distinct from the baseline's "baseline" system id.
SYSTEM_ID = "repoguard"

# Explicit, ordered assessment stages (docs/repoguard.md, "Workflow").
STAGE_ORDER: tuple[str, ...] = ("load", "plan", "assess", "cross_check", "finalize")
