"""Exceptions for the snapshot subsystem.

Every failure path raises a typed error; the CLI maps these to a nonzero
exit. Subsystem errors never silently degrade to a different revision.
"""

from __future__ import annotations


class SnapshotError(Exception):
    """Base class for all snapshot subsystem errors."""


class InvalidShaError(SnapshotError):
    """A commit SHA is not a 40-character lowercase hex string."""


class ManifestError(SnapshotError):
    """The dataset manifest is unreadable, invalid, or missing required fields."""


class AcquisitionError(SnapshotError):
    """Repository acquisition failed (unreachable, corrupt, or git error)."""


class CommitNotFoundError(AcquisitionError):
    """The requested commit SHA does not exist at the remote."""


class CommitMismatchError(SnapshotError):
    """The checked out commit differs from the requested commit."""


class SnapshotExistsError(SnapshotError):
    """A snapshot already exists at the target location with different identity."""


class HashError(SnapshotError):
    """Snapshot content hash could not be computed."""
