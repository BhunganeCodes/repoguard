"""Evidence artifact locations within the snapshot store.

Evidence artifacts are derived from a snapshot checkout and stored alongside
the immutable snapshot (which lives under the gitignored ``evaluation/snapshots``
store). Original evidence is never written into git-tracked source directories.
"""

from __future__ import annotations

from pathlib import Path

EVIDENCE_FILE = "evidence.yaml"


def evidence_file(snapshot_dir: Path) -> Path:
    """Path of the evidence artifact inside a snapshot directory."""
    return snapshot_dir / EVIDENCE_FILE
