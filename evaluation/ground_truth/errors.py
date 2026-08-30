"""Error types for the ground-truth subsystem."""


class GroundTruthError(Exception):
    """Failure in a ground-truth workflow operation."""


class ConsensusError(GroundTruthError):
    """Raised when a final consensus artifact cannot be produced."""
