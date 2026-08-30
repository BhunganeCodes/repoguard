"""Version and identity scheme for the scoring subsystem."""

__version__ = "0.1.0"

# Scheme prefix used when hashing an assessment's content identity. Change
# this only when the on-disk assessment schema changes incompatibly.
ASSESSMENT_SCHEME = "repoguard-assessment-v1"

# Schema version of the structured assessment artifact.
ASSESSMENT_SCHEMA_VERSION = 1
