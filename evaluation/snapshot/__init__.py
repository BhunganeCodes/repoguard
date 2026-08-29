"""Reproducible evaluation snapshot acquisition.

The snapshot subsystem turns a repository URL plus a frozen commit SHA into
a deterministic local snapshot, a machine-readable repository inventory,
and an immutable snapshot record. See docs/snapshot-acquisition.md.
"""

from evaluation.snapshot._version import __version__

__all__ = ["__version__"]
