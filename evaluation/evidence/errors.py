"""Error types for the evidence extraction subsystem."""


class EvidenceError(Exception):
    """Base error for the evidence subsystem."""


class ValidationError(EvidenceError):
    """Raised when an evidence artifact fails validation."""
