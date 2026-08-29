"""Assessment statuses for the scoring subsystem.

The four canonical statuses are inherited from the evidence schema (rubric
Section 3). ``PENDING`` is an additional, deliberately non-score state the
scoring engine uses when a criterion still requires human or LLM judgment
that cannot be mechanically derived from evidence alone.

Status to score bounds are defined by the canonical rubric Section 3.5 and
are enforced by the scorer:

* ``FOUND`` - 0-4 per the anchors
* ``UNCERTAIN`` - 0-2; 0 when the positive evidence is entirely unsupported
* ``NOT_FOUND`` - 0
* ``NOT_APPLICABLE`` - excluded from scoring, must carry justification and
  evidence
* ``PENDING`` - not yet assessed; no score assigned
"""

from __future__ import annotations

from evaluation.evidence.statuses import EVIDENCE_STATUSES
from evaluation.scoring.errors import ScoringError

# Deliberately non-score state: judgment for this criterion has not been
# produced yet. Validation accepts it; scoring refuses to emit a score while
# any criterion is PENDING.
PENDING = "PENDING"

ASSESSMENT_STATUSES: frozenset[str] = frozenset({*EVIDENCE_STATUSES, PENDING})

# Union of "no numeric score" statuses that are not included in any earned
# total.
NO_SCORE_STATUSES: frozenset[str] = frozenset({"NOT_APPLICABLE", PENDING})

# Statuses whose criteria participate in dimension/overall scoring.
SCOREABLE_STATUSES: frozenset[str] = frozenset({"FOUND", "NOT_FOUND", "UNCERTAIN"})

# Per-status allowed integer score range on the 0-4 scale (rubric 3.5).
# ``None`` means the status carries no score at all.
SCORE_BOUNDS: dict[str, tuple[int, int] | None] = {
    "FOUND": (0, 4),
    "UNCERTAIN": (0, 2),
    "NOT_FOUND": (0, 0),
    "NOT_APPLICABLE": None,
    PENDING: None,
}


def validate_assessment_status(status: str) -> None:
    if status not in ASSESSMENT_STATUSES:
        raise ScoringError(
            f"invalid assessment status {status!r}; expected one of "
            + ", ".join(sorted(ASSESSMENT_STATUSES))
        )
