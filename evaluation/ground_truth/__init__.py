"""Human-authored ground truth for frozen evaluation cases.

Independent reviewers score each frozen case against the canonical rubric
using only the frozen evidence artifact and permitted snapshot inspection.
Disagreement between reviewers is detected deterministically, disputed
criteria are adjudicated by a third reviewer, and the final consensus
artifact is produced by the same deterministic scoring engine used for
every assessment in the project.
"""

from evaluation.ground_truth import cli
from evaluation.ground_truth._version import __version__

__all__ = ["__version__", "cli"]
