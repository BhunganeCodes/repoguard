"""Version and identity schemes for the ground-truth subsystem.

Ground truth is the human-produced, rubric-scored reference for each frozen
case (docs/evaluation.md Section 6 and docs/ground-truth.md). Its identities
distinguish reviewer assessments, adjudication records, and the final
consensus artifact so every artifact is independently verifiable and no
system result can be confused with human judgment.
"""

__version__ = "0.1.0"

# Scheme prefixes used when hashing content identities. Change them only when
# the corresponding on-disk schema changes incompatibly.
REVIEW_SCHEME = "repoguard-review-v1"
REVIEW_SCHEMA_VERSION = 1

ADJUDICATION_SCHEME = "repoguard-adjudication-v1"
ADJUDICATION_SCHEMA_VERSION = 1

GROUND_TRUTH_SCHEME = "repoguard-ground-truth-v1"
GROUND_TRUTH_SCHEMA_VERSION = 1

# Frozen evaluation dataset this workflow records against
# (evaluation/datasets/dataset-v1.0.0.yaml). Reviewer assessments, adjudication
# records, and consensus artifacts all bind to it.
DATASET_VERSION = "1.0.0"

# Protocol disagreement thresholds (docs/evaluation.md Section 6.6). A
# criterion is disputed when the score difference is *more than* one point;
# a case requires discussion when the aggregate score difference is *more
# than* five points. These thresholds come from the evaluation protocol and
# must not be tuned here.
CRITERION_DISAGREEMENT_POINTS = 1
AGGREGATE_DISAGREEMENT_POINTS = 5
