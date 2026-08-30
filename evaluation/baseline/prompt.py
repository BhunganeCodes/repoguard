"""Canonical baseline prompt construction (versioned).

The baseline sends the model a single system + user prompt pair. The prompt
is deterministic: for the same evidence artifact it is byte-identical, so
repeated runs are comparable. Everything in the prompt is drawn from the
canonical rubric (via ``evaluation/scoring/rubric``) and the supplied
evidence artifact; no runtime metadata is embedded.

``PROMPT_VERSION`` identifies this exact prompt definition. The rubric block
is rendered for rubric version ``EXPECTED_RUBRIC_VERSION`` and the builder
fails closed if the scoring engine's rubric version ever diverges.

The per-criterion anchors in ``RUBRIC_ANCHORS`` transcribe
``docs/scoring-rubric.md`` Section 5 verbatim (rubric version 1.0). A unit
test re-parses that document and fails if the transcription drifts from the
canonical rubric.
"""

from __future__ import annotations

from evaluation.baseline.errors import BaselineError
from evaluation.evidence.models import EvidenceArtifact
from evaluation.scoring import rubric as canonical_rubric

PROMPT_VERSION = "1.0"

# The rubric rendering is bound to this rubric version; reject any mismatch.
EXPECTED_RUBRIC_VERSION = "1.0"

SYSTEM_PROMPT = """You are evaluating a software repository for engineering quality against a fixed rubric.

RULES:
- Assess ONLY the evidence supplied in the EVIDENCE block. Never invent repository facts, files, line numbers, metrics, tests, or behavior that do not appear there.
- Never fabricate evidence. If evidence for a criterion is missing, record status NOT_FOUND with score 0; a documented NOT_FOUND is preferable to a guess.
- Cite evidence using the evidence IDs from the EVIDENCE block. Every scored criterion must cite at least one evidence ID that exists there.
- Use only the canonical statuses FOUND, NOT_FOUND, UNCERTAIN, and NOT_APPLICABLE, and respect the status-to-score bounds in the RUBRIC.
- Distinguish NOT_FOUND (a deliberate search found no evidence) from UNCERTAIN (evidence is partial, ambiguous, or unverifiable). When a criterion is UNCERTAIN, provide an uncertainty_reason and do not score above 2.
- Use NOT_APPLICABLE only when the criterion genuinely does not apply to this repository; justify it and cite evidence.
- Score each criterion on the 0-4 scale using the anchors in the RUBRIC.
- Do not assign repository quality tiers, rankings, or grades beyond the rubric scores; the rubric does not require tiers.
- Return exactly the single structured JSON object specified in OUTPUT, with no prose or markdown outside it."""

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

# status: (meaning, allowed score as displayed)
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

# Per-criterion anchors transcribed verbatim from docs/scoring-rubric.md
# Section 5 (rubric version 1.0). score -> anchor text.
RUBRIC_ANCHORS: dict[str, dict[int, str]] = {
    "architecture.project_organization": {
        4: "Layout is conventional and consistent: source, tests, configuration, and documentation are clearly separated; navigation is obvious.",
        3: "Layout is consistent with minor deviations that are easy to navigate around.",
        2: "A layout exists but mixes concerns or is internally inconsistent.",
        1: "Layout is ad hoc; little structure is apparent.",
        0: "No discernible organization of the repository.",
    },
    "architecture.separation_of_responsibilities": {
        4: "Modules and layers have single, distinct responsibilities; responsibilities do not bleed across boundaries.",
        3: "Clear separation with occasional, small cross-boundary leak.",
        2: "Some separation, but responsibilities are blurred or oversized modules exist.",
        1: 'Dominant "god" modules or layers that mix unrelated concerns.',
        0: "Responsibilities are not separated at all.",
    },
    "architecture.dependency_direction": {
        4: "Dependencies flow from high-level toward stable, low-level modules; no dependency cycles.",
        3: "Generally clean direction with one or two minor exceptions.",
        2: "Direction is inconsistent; some cycles or high-level modules depending on concrete internals.",
        1: "Frequent cycles or layers that depend on the wrong side of the boundary.",
        0: "Dependency structure is tangled; no clear direction.",
    },
    "architecture.coupling_and_complexity": {
        4: "Modules/systems are loosely coupled and individually simple; interfaces are narrow and stable.",
        3: "Low coupling and complexity with minor hotspots.",
        2: "Noticeable coupling or complexity concentrated in a few modules.",
        1: "High coupling or large complex modules with few clear seams.",
        0: "Everything depends on everything; complexity is unbounded.",
    },
    "architecture.extensibility": {
        4: "Adding or changing behavior is localized; extension points exist and are documented.",
        3: "Extensible with some effort; seams exist though not documented.",
        2: "Extension requires touching multiple unrelated places.",
        1: "The structure resists extension; changes ripple widely.",
        0: "No discernible way to extend behavior.",
    },
    "testing.test_presence": {
        4: "Tests exist for the substantial majority of production code paths.",
        3: "Tests exist for most production modules, with a few gaps.",
        2: "Tests exist for some modules only.",
        1: "Few tests relative to the size of the codebase.",
        0: "No tests found.",
    },
    "testing.test_organization": {
        4: "Tests are structured, named consistently, mirror the source layout, and run via a documented command.",
        3: "Tests are organized with minor inconsistencies; a documented command exists.",
        2: "Tests run but organization is inconsistent or not documented.",
        1: "Tests exist but there is no clear way to discover or run them.",
        0: "No test organization.",
    },
    "testing.unit_testing": {
        4: "Unit tests isolate components, are fast and deterministic, and cover logic directly.",
        3: "Unit tests exist and are mostly isolated, with minor coupling to environment.",
        2: "Tests run against logic but rely on shared state or external services.",
        1: "Tests are slow, order-dependent, or weakly assert behavior.",
        0: "No unit-level tests.",
    },
    "testing.integration_testing": {
        4: "Integration tests exercise real workflows across components; any mocks are justified.",
        3: "Integration tests cover the main workflows, with some paths untested.",
        2: "Some integration coverage, but shallow or heavily mocked.",
        1: "Integration tests are nominal and do not exercise real interactions.",
        0: "No integration tests.",
    },
    "testing.failure_path_coverage": {
        4: "Errors, invalid inputs, and boundary conditions are explicitly tested, not only happy paths.",
        3: "Failure paths are covered with modest gaps.",
        2: "A few failure paths are covered; most tests are happy-path only.",
        1: "Failure handling exists in code but is untested.",
        0: "No failure-path tests.",
    },
    "maintainability.code_readability": {
        4: "Naming is clear, functions are small, control flow is straightforward, and style is consistent.",
        3: "Readable with a few unclear spots.",
        2: "Mixed quality; some names or flows require effort to follow.",
        1: "Code is generally hard to read; conventions inconsistent.",
        0: "Code is effectively unreadable.",
    },
    "maintainability.complexity": {
        4: "Control flow and data structures are simple; complexity is bounded and local.",
        3: "Generally simple with occasional deep nesting.",
        2: "Several complex, hard-to-follow sections.",
        1: "Pervasive complexity; deeply nested or convoluted logic.",
        0: "Complexity is unbounded.",
    },
    "maintainability.duplication": {
        4: "Shared logic is extracted; no meaningful duplication.",
        3: "Minor, acceptable duplication.",
        2: "Noticeable duplicated logic copied across modules.",
        1: "Substantial duplication; the same logic appears in many places.",
        0: "Duplication is pervasive.",
    },
    "maintainability.error_handling": {
        4: "Errors are handled consistently; failure modes are predictable; silent failures are absent.",
        3: "Consistent handling with minor gaps.",
        2: "Errors are handled unevenly; some failures are swallowed or obscure.",
        1: "Most failure paths are unhandled or misreported.",
        0: "Failure modes are unpredictable or ignored.",
    },
    "maintainability.technical_debt": {
        4: "No accumulating TODO/FIXME/hack markers; debt is tracked and documented if present.",
        3: "Little debt; markers are few and explained.",
        2: "Visible markers or shortcuts scattered through the code.",
        1: "Significant shortcuts with no tracking.",
        0: "Debt is pervasive and unmanaged.",
    },
    "dependencies.dependency_hygiene": {
        4: "Dependency set is minimal and appropriate for the stack; no unused or duplicated dependencies.",
        3: "Mostly clean with a few minor extras.",
        2: "Several unnecessary or duplicated dependencies.",
        1: "Many dependencies that appear unused or overlapping.",
        0: "No dependency discipline.",
    },
    "dependencies.version_management": {
        4: "Versions are pinned or locked; installs are reproducible from committed manifests.",
        3: "Versions specified with minor looseness; installs are practically reproducible.",
        2: "Versions are loosely specified or the manifest is incomplete.",
        1: "Versions are unpinned; installs vary.",
        0: "No version management.",
    },
    "dependencies.dependency_necessity": {
        4: 'Each dependency is justified by actual use; no "just in case" additions.',
        3: "Nearly all dependencies are justified by use.",
        2: "Some dependencies lack evident justification.",
        1: "Many dependencies cannot be tied to actual use.",
        0: "Dependencies are added without justification.",
    },
    "dependencies.vulnerability_risk_awareness": {
        4: "Known vulnerabilities are checked; risks are documented with remediation or a recorded decision.",
        3: "Checks exist with some findings undocumented.",
        2: "Checks exist but findings are not assessed.",
        1: "Risk is never checked.",
        0: "Dependencies are used with no risk information at all.",
    },
    "dependencies.supply_chain_discipline": {
        4: "Sources are trusted and identified; integrity/pinning is in place; no unvetted fetched code.",
        3: "Good discipline with minor gaps.",
        2: "Mixed practices; some untrusted or unvetted sources.",
        1: "Fetched code is largely unvetted.",
        0: "No supply-chain discipline.",
    },
    "documentation.readme": {
        4: "README states the project's purpose, current status, usage, and points to further docs.",
        3: "README is useful with minor omissions.",
        2: "README exists but is thin or partly stale.",
        1: "README exists but is misleading or substantially incomplete.",
        0: "No README.",
    },
    "documentation.installation_and_execution": {
        4: "Setup, install, and run instructions are complete and accurate; defaults match reality.",
        3: "Instructions are correct with minor gaps.",
        2: "Instructions are incomplete or partially outdated.",
        1: "Instructions exist but do not work or are misleading.",
        0: "No installation or execution instructions.",
    },
    "documentation.architecture_documentation": {
        4: "Design, components, decisions (for example decision records), and key flows are documented and current.",
        3: "Architecture documented with minor gaps.",
        2: "Partial documentation; some major components undocumented.",
        1: "Documentation is nominal or far out of date.",
        0: "No architecture documentation.",
    },
    "documentation.api_interface_documentation": {
        4: "Public interfaces/endpoints are documented with contracts and examples.",
        3: "Interfaces documented with minor gaps or missing examples.",
        2: "Some interfaces documented; others undocumented.",
        1: "Only trivial or inconsistent interface documentation.",
        0: "No API or interface documentation.",
    },
    "documentation.developer_documentation": {
        4: "Contribution flow, environment setup, testing, and coding standards are documented.",
        3: "Developer docs exist with minor omissions.",
        2: "Partial developer docs; key processes undocumented.",
        1: "Developer documentation is nominal or stale.",
        0: "No developer documentation.",
    },
}

_OUTPUT_TEMPLATE = """OUTPUT
Respond with ONLY a single JSON object (no prose, no markdown) matching this exact schema:

{
  "schema_version": 1,
  "case_id": "<case id from EVIDENCE>",
  "name": "<repository name from EVIDENCE>",
  "rubric_version": "{__rubric_version__}",
  "evidence_identity": "<evidence identity from EVIDENCE>",
  "criteria": [
    {
      "criterion_id": "architecture.project_organization",
      "dimension": "architecture",
      "status": "FOUND",
      "score": 3,
      "citations": ["architecture.top_level_structure"],
      "rationale": "one or two sentences tying this score to the cited evidence"
    }
  ]
}

Field rules:
- criteria must contain EXACTLY 25 rows, one per criterion id, in any order.
- criterion_id MUST be one of the 25 ids listed in RUBRIC; dimension MUST match its rubric dimension.
- status MUST be one of FOUND, NOT_FOUND, UNCERTAIN, NOT_APPLICABLE.
- score: an integer within the status bound from RUBRIC. Required for FOUND, NOT_FOUND, and UNCERTAIN. Must be null for NOT_APPLICABLE.
- citations: an array of evidence IDs from the EVIDENCE block. Every scored criterion needs at least one citation.
- For NOT_APPLICABLE rows add "justification": "<why the criterion does not apply>" with its evidence citations; omit score/rationale.
- For UNCERTAIN rows add "uncertainty_reason": "<why the evidence is partial or ambiguous>"; never score above 2; if every positive claim is unsupported set "unsupported": true and score 0.
- rationale: optional short justification for the chosen score.
- Do not add fields other than those described."""


def _require_rubric_version() -> None:
    if canonical_rubric.RUBRIC_VERSION != EXPECTED_RUBRIC_VERSION:
        raise BaselineError(
            "rubric mismatch in baseline prompt: scoring engine implements "
            f"rubric {canonical_rubric.RUBRIC_VERSION!r}, prompt renders "
            f"rubric {EXPECTED_RUBRIC_VERSION!r}"
        )


def render_rubric() -> str:
    """Render the canonical rubric block included in every prompt."""
    _require_rubric_version()
    lines: list[str] = [f"RUBRIC (version {EXPECTED_RUBRIC_VERSION})"]
    lines.append("Dimensions: " + ", ".join(canonical_rubric.DIMENSIONS))
    lines.append("Each dimension is 20 points: 5 criteria of 4 points each.")
    lines.append("")
    lines.append("Evidence statuses and allowed scores:")
    for status, meaning in _STATUS_MEANINGS.items():
        lines.append(f"- {status}: {meaning} (allowed score: {_STATUS_BOUNDS_DISPLAY[status]})")
    lines.append("")
    lines.append("General 0-4 anchors:")
    for score, anchor in _GENERAL_ANCHORS:
        lines.append(f"- {score}: {anchor}")
    lines.append("")
    lines.append(f"{len(canonical_rubric.CRITERIA)} criteria (id [dimension] name):")
    for criterion_id in canonical_rubric.CRITERIA:
        spec = canonical_rubric.CRITERIA[criterion_id]
        lines.append("")
        lines.append(f"## {criterion_id} [{spec['dimension']}] {spec['name']}")
        for score in (4, 3, 2, 1, 0):
            lines.append(f"  {score}: {RUBRIC_ANCHORS[criterion_id][score]}")
    return "\n".join(lines)


def _indent(text: str, indent: str = "  ") -> str:
    return "\n".join(indent + line for line in text.splitlines())


def render_evidence(evidence: EvidenceArtifact) -> str:
    """Render the evidence block included in every prompt."""
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
    for item in evidence.items:
        lines.append(f"{item.evidence_id} [{item.category}] {item.status}")
        lines.append(_indent(item.observation))
        if item.source_paths:
            lines.append(_indent("source_paths: " + ", ".join(item.source_paths)))
        if item.notes:
            lines.append(_indent(f"notes: {item.notes}"))
    return "\n".join(lines)


def render_output() -> str:
    _require_rubric_version()
    return _OUTPUT_TEMPLATE.replace("{__rubric_version__}", EXPECTED_RUBRIC_VERSION)


def build_prompt(evidence: EvidenceArtifact) -> tuple[str, str]:
    """Deterministic ``(system, user)`` prompt pair for an evidence artifact."""
    _require_rubric_version()
    user = "\n\n".join((render_rubric(), render_evidence(evidence), render_output()))
    return SYSTEM_PROMPT, user
