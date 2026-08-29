"""Canonical RepoGuard prompt construction (versioned, staged).

RepoGuard's prompt is deliberately distinct from the baseline's single-shot
assessment prompt (docs/repoguard.md, "Difference from the baseline"). It
drives one structured model response that instantiates the assessment
workflow stages inside a single call, which the orchestrator
(``evaluation.repoguard.pipeline``) then treats as explicit, separately
validated stages: PLAN (per-criterion evidence relevance), ASSESS (the 25
canonical criterion rows), and CROSS-CHECK (self-reported contradictions and
uncertainties).

The prompt is deterministic: for the same evidence artifact it is
byte-identical, so repeated runs are comparable, and it is versioned
``PROMPT_VERSION``. Everything it contains is drawn from the canonical rubric
(via ``evaluation/scoring/rubric`` and the rubric anchors transcribed in
``evaluation.baseline.prompt.RUBRIC_ANCHORS``, which has a fidelity test
against ``docs/scoring-rubric.md``) and the supplied evidence artifact. No
runtime metadata is embedded.
"""

from __future__ import annotations

from evaluation.baseline.prompt import RUBRIC_ANCHORS
from evaluation.evidence.models import EvidenceArtifact
from evaluation.repoguard.errors import RepoGuardError
from evaluation.scoring import rubric as canonical_rubric

PROMPT_VERSION = "1.0"

# The rubric rendering is bound to this rubric version; reject any mismatch.
EXPECTED_RUBRIC_VERSION = "1.0"

_GENERAL_ANCHORS: tuple[tuple[int, str], ...] = (
    (
        4,
        "Strong. The criterion is met to a high standard. Direct, verifiable evidence is present and there are no material gaps.",
    ),
    (3, "Good. The criterion is met, with minor and documented gaps."),
    (
        2,
        "Partial. The criterion is only partially met; evidence is mixed or covers part of the criterion only.",
    ),
    (1, "Weak. Minimal satisfaction; substantial gaps or mostly negative evidence."),
    (0, "Absent. No evidence the criterion is met, or the supporting claims are unsupported."),
)

_STATUS_MEANINGS: dict[str, str] = {
    "FOUND": "Verifiable evidence located that directly supports the criterion",
    "NOT_FOUND": "A deliberate, documented search produced no evidence for the criterion",
    "UNCERTAIN": "Evidence is partial, ambiguous, inconsistent, or cannot be verified",
    "NOT_APPLICABLE": "The criterion does not apply to this repository",
}
_STATUS_BOUNDS_DISPLAY: dict[str, str] = {
    "FOUND": "0-4, per the anchors",
    "NOT_FOUND": "0",
    "UNCERTAIN": "0-2; 0 if the positive evidence is entirely unsupported",
    "NOT_APPLICABLE": "no numeric score; excluded from the aggregate with justification",
}

SYSTEM_PROMPT = """You are RepoGuard, assessing a software repository's engineering quality from a frozen evidence artifact described in EVIDENCE.
You work in four explicit stages and your output must mirror them.

STAGES:
1. PLAN - for every one of the 25 criteria, decide which EVIDENCE items are relevant to assessing it. Cite only evidence IDs that exist in EVIDENCE.
2. ASSESS - evaluate each criterion, one at a time, against the relevant evidence: choose an evidence status, a score within the status bounds, and citations of the evidence that supports the call.
3. CROSS-CHECK - actively search your own rows for contradictions against EVIDENCE and RUBRIC, and report every contradiction, missing support, or uncertainty you find. Do not restate the rows; find what is wrong or unverifiable.
4. OUTPUT - return only the single structured JSON object described in OUTPUT.

RULES:
- Evidence first. Assess ONLY the evidence supplied in EVIDENCE. Never invent repository facts, files, line numbers, metrics, tests, or behavior that do not appear there.
- Absence is a finding, not a positive. NOT_FOUND records a deliberate search that produced no evidence; it scores 0 and is never reinterpreted as positive evidence for this or any other criterion.
- You have no tools, no shell, and no repository access. Reason only over EVIDENCE; do not execute or inspect anything else.
- Cite at least one evidence ID from EVIDENCE for every scored criterion, and never cite an evidence ID that does not exist there.
- Use only the canonical statuses FOUND, NOT_FOUND, UNCERTAIN, and NOT_APPLICABLE, and respect the status-to-score bounds and anchors in RUBRIC.
- Distinguish NOT_FOUND from UNCERTAIN. UNCERTAIN requires an uncertainty_reason and never scores above 2; when every positive claim is unsupported, set unsupported true and score 0.
- Use NOT_APPLICABLE only when the criterion genuinely does not apply; justify it and cite evidence.
- CROSS-CHECK specifically looks for: a FOUND claim resting only on NOT_FOUND/UNCERTAIN evidence, an unsupported positive claim, a score that conflicts with the status, a claim that is absent from EVIDENCE, and citations that point at evidence for another criterion or case.
- Do not assign repository quality tiers, rankings, or grades beyond the rubric scores.
- Return exactly the structured JSON object specified in OUTPUT, with no prose or markdown outside it."""


def _require_rubric_version() -> None:
    if canonical_rubric.RUBRIC_VERSION != EXPECTED_RUBRIC_VERSION:
        raise RepoGuardError(
            "rubric mismatch in RepoGuard prompt: scoring engine implements "
            f"rubric {canonical_rubric.RUBRIC_VERSION!r}, prompt renders "
            f"rubric {EXPECTED_RUBRIC_VERSION!r}"
        )


def render_rubric() -> str:
    """Render the canonical rubric block (version-gated)."""
    _require_rubric_version()
    lines: list[str] = [f"RUBRIC (version {EXPECTED_RUBRIC_VERSION})"]
    lines.append("Dimensions: " + ", ".join(canonical_rubric.DIMENSIONS))
    lines.append("Each dimension is 20 points: 5 criteria of 4 points each.")
    lines.append("")
    lines.append("Evidence statuses and allowed scores:")
    for status, meaning in _STATUS_MEANINGS.items():
        lines.append(f"- {status}: {meaning} (allowed score: {_STATUS_BOUNDS_DISPLAY[status]})")
    lines.append("")
    lines.append("General 0-4 anchors (Section 4 of the rubric):")
    for score, anchor in _GENERAL_ANCHORS:
        lines.append(f"- {score}: {anchor}")
    lines.append("")
    lines.append(f"The {len(canonical_rubric.CRITERIA)} criteria, grouped by dimension:")
    for dimension in canonical_rubric.DIMENSIONS:
        lines.append("")
        lines.append(f"DIMENSION {dimension}")
        for criterion_id in canonical_rubric.CRITERIA_BY_DIMENSION[dimension]:
            spec = canonical_rubric.CRITERIA[criterion_id]
            lines.append(f"## {criterion_id} [{spec['dimension']}] {spec['name']}")
            for score in (4, 3, 2, 1, 0):
                lines.append(f"  {score}: {RUBRIC_ANCHORS[criterion_id][score]}")
    return "\n".join(lines)


def render_evidence(evidence: EvidenceArtifact) -> str:
    """Render the evidence artifact grouped by dimension/category."""
    lines = [
        "EVIDENCE",
        f"case_id: {evidence.case_id}",
        f"name: {evidence.name}",
        f"repository_url: {evidence.repository_url}",
        f"verified_commit: {evidence.verified_commit}",
        f"snapshot_content_hash: {evidence.snapshot_content_hash}",
        f"evidence identity: {evidence.evidence_identity}",
        "-" * 72,
    ]
    for dimension in canonical_rubric.DIMENSIONS:
        items = [item for item in evidence.items if item.category == dimension]
        lines.append("")
        lines.append(f"## {dimension.upper()}")
        for item in items:
            lines.append(f"{item.evidence_id} status={item.status} type={item.evidence_type}")
            lines.append(f"  observation: {item.observation}")
            if item.source_paths:
                lines.append("  source_paths: " + ", ".join(item.source_paths))
            if item.notes:
                lines.append(f"  notes: {item.notes}")
    return "\n".join(lines)


_OUTPUT_TEMPLATE = """OUTPUT
Respond with ONLY a single JSON object (no prose, no markdown) matching this exact top-level shape:

{
  "plan": {
    "criteria": [
      {
        "criterion_id": "architecture.project_organization",
        "relevant_evidence": ["architecture.top_level_structure"]
      }
    ]
  },
  "criteria": [
    {
      "criterion_id": "architecture.project_organization",
      "dimension": "architecture",
      "status": "FOUND",
      "score": 3,
      "citations": ["architecture.top_level_structure"],
      "rationale": "one or two sentences tying this score to the cited evidence"
    }
  ],
  "cross_check": {
    "findings": [
      {
        "criterion_id": "architecture.coupling_and_complexity",
        "kind": "uncertainty",
        "detail": "one sentence about the contradiction, missing support, or uncertainty found"
      }
    ]
  }
}

Field rules:
- plan.criteria must contain EXACTLY 25 rows, one per criterion id. relevant_evidence lists evidence IDs from EVIDENCE that are relevant to assessing that criterion; list only IDs that exist in EVIDENCE.
- criteria must contain EXACTLY 25 rows, one per criterion id, in any order. criterion_id MUST be one of the 25 ids listed in RUBRIC; dimension MUST match its rubric dimension.
- criteria status MUST be one of FOUND, NOT_FOUND, UNCERTAIN, NOT_APPLICABLE.
- criteria score: an integer within the status bound from RUBRIC. Required for FOUND, NOT_FOUND, and UNCERTAIN. Must be null for NOT_APPLICABLE.
- criteria citations: an array of evidence IDs from EVIDENCE. Every scored criterion needs at least one citation.
- For NOT_APPLICABLE rows add "justification": "<why the criterion does not apply>" with its evidence citations; omit score/rationale.
- For UNCERTAIN rows add "uncertainty_reason": "<why the evidence is partial or ambiguous>"; never score above 2; if every positive claim is unsupported set "unsupported": true and score 0.
- criteria rationale: optional short justification for the chosen score.
- cross_check.findings: the result of your CROSS-CHECK stage. Each finding cites a criterion_id from RUBRIC, a kind, and a one-sentence detail. An empty list is acceptable only when you found no contradictions, no missing support, and no uncertainty worth recording.
- Do not add fields other than those described."""


def render_output() -> str:
    _require_rubric_version()
    return _OUTPUT_TEMPLATE


def build_prompt(evidence: EvidenceArtifact) -> tuple[str, str]:
    """Deterministic ``(system, user)`` prompt pair for an evidence artifact."""
    _require_rubric_version()
    user = "\n\n".join((render_rubric(), render_evidence(evidence), render_output()))
    return SYSTEM_PROMPT, user
