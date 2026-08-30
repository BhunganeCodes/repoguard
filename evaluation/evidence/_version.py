"""Version and identity scheme for the evidence subsystem."""

__version__ = "0.1.0"

# Scheme prefix used when hashing evidence content identity. Change this only
# when the on-disk evidence schema changes incompatibly.
EXTRACTION_SCHEME = "repoguard-evidence-v1"

# Aggregate extractor release reported on each artifact. Each individual
# extractor also carries its own identifier and version.
EVIDENCE_EXTRACTION_VERSION = "v1"
