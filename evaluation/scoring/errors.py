"""Error types for the deterministic scoring subsystem."""


class ScoringError(Exception):
    """Base error for the scoring subsystem."""


class ValidationError(ScoringError):
    """Raised when an assessment fails scoring validation."""
