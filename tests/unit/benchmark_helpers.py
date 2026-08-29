"""Synthetic fixtures for the benchmark runner tests.

These helpers build a frozen dataset manifest file, an immutable snapshot
(checkout + ``snapshot.yaml``), and a bound evidence artifact for synthetic
cases. They are fixtures only: never real repositories, never ground truth,
and never evaluation results. All runs use mock providers (network-free); no
test in this module touches the network or the official dataset.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml
from baseline_helpers import mock_valid
from repoguard_helpers import staged_response
from scoring_helpers import make_evidence

from evaluation.baseline.pipeline import EvaluatorConfig
from evaluation.baseline.provider import LLMProvider, LLMRequest, LLMResponse, MockProvider
from evaluation.evidence.models import EvidenceArtifact
from evaluation.evidence.serialize import content_identity
from evaluation.snapshot.commits import SNAPSHOT_HASH_SCHEME
from evaluation.snapshot.hashing import hash_snapshot_tree
from evaluation.snapshot.models import ManifestCase
from evaluation.snapshot.paths import snapshot_dir

COMMIT = "a" * 40
REPO_URL = "https://example.com/x.git"
DATASET_NAME = "repoguard-evaluation-dataset"
DATASET_VERSION = "1.0.0"

_DEFAULT_FILES = {
    "README.md": "# synthetic\n",
    "src/app.py": "def main():\n    return 0\n",
}


def case_dict(
    candidate_id: str = "C001",
    *,
    status: str = "confirmed",
    decision: str = "include",
    name: str = "synthetic",
    url: str = REPO_URL,
    commit: str = COMMIT,
    ecosystem: str = "python",
    license: str = "MIT",
) -> dict[str, str]:
    return {
        "candidate_id": candidate_id,
        "name": name,
        "url": url,
        "pinned_commit": commit,
        "ecosystem": ecosystem,
        "license": license,
        "dataset_decision": decision,
        "dataset_status": status,
    }


def write_dataset(path: Path, cases: list[dict[str, str]]) -> Path:
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset": {
            "name": DATASET_NAME,
            "version": DATASET_VERSION,
            "creation_date": "2026-08-28",
            "status": "frozen",
        },
        "source_registry": "synthetic",
        "protocol": "docs/evaluation.md",
        "freeze_decision": "synthetic fixture",
        "counts": {"included": len(cases), "confirmed": len(cases)},
        "candidates": cases,
    }
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return path


def make_case(candidate_id: str = "C001", status: str = "confirmed") -> ManifestCase:
    data = case_dict(candidate_id, status=status)
    return ManifestCase(
        candidate_id=data["candidate_id"],
        name=data["name"],
        url=data["url"],
        pinned_commit=data["pinned_commit"],
        ecosystem=data["ecosystem"],
        license=data["license"],
        dataset_decision=data["dataset_decision"],
        dataset_status=data["dataset_status"],
    )


def write_snapshot_store(
    store: Path, case: ManifestCase, files: dict[str, str] | None = None
) -> Path:
    """Write a realistic immutable snapshot (checkout + record) for a case."""
    target = snapshot_dir(store, case)
    checkout = target / "checkout"
    for relative, content in (files or _DEFAULT_FILES).items():
        path = checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    content_hash = hash_snapshot_tree(checkout)
    record: dict[str, Any] = {
        "schema_version": 1,
        "identity": f"{SNAPSHOT_HASH_SCHEME}:{content_hash}",
        "candidate_id": case.candidate_id,
        "name": case.name,
        "repository_url": case.url,
        "requested_commit": case.pinned_commit,
        "verified_commit": case.pinned_commit,
        "content_hash": content_hash,
        "acquired_at": "2026-08-28T00:00:00Z",
        "git_version": "synthetic",
        "dataset": {"name": DATASET_NAME, "version": DATASET_VERSION},
        "acquisition": {"remote_scheme": "http", "blob_filter": True, "depth": 1},
    }
    (target / "snapshot.yaml").write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    return target


def read_snapshot_content_hash(snapshot_root: Path) -> str:
    raw = yaml.safe_load((snapshot_root / "snapshot.yaml").read_text(encoding="utf-8"))
    return str(raw["content_hash"])


def write_evidence(snapshot_root: Path, case: ManifestCase) -> EvidenceArtifact:
    """Write a bound, valid evidence artifact for a snapshot; returns it."""
    evidence = make_evidence(case.candidate_id)
    evidence = replace(
        evidence,
        name=case.name,
        repository_url=case.url,
        requested_commit=case.pinned_commit,
        verified_commit=case.pinned_commit,
        snapshot_content_hash=read_snapshot_content_hash(snapshot_root),
    )
    evidence.evidence_identity = content_identity(evidence)
    (snapshot_root / "evidence.yaml").write_text(
        yaml.safe_dump(evidence.to_dict(), sort_keys=False), encoding="utf-8"
    )
    return evidence


class SequencedProvider:
    """Deterministic provider that serves one canned response per call.

    The benchmark run sends exactly one request per system; a run pairing
    the baseline and RepoGuard therefore consumes two responses. Tests use
    this to hand each system its own valid mock response.
    """

    name = "mock"

    def __init__(self, responses: list[LLMProvider]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        inner = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        self.calls += 1
        return inner.generate(request)

    def public_config(self) -> dict[str, Any]:
        return {"mode": self.name}


def paired_providers(evidence: EvidenceArtifact) -> SequencedProvider:
    """Baseline + RepoGuard mock providers that both succeed for ``evidence``."""
    return SequencedProvider([mock_valid(evidence), MockProvider(staged_response(evidence))])


def failing_provider_for(evidence: EvidenceArtifact, system: str) -> SequencedProvider:
    """A provider pair that fails the named system with a provider error."""
    valid = mock_valid(evidence)
    failing = MockProvider(exc=RuntimeError("boom"))
    if system == "baseline":
        return SequencedProvider([failing, MockProvider(staged_response(evidence))])
    return SequencedProvider([valid, failing])


def mock_config() -> EvaluatorConfig:
    return EvaluatorConfig(provider_name="mock", model="mock")
