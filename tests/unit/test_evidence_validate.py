"""Evidence artifact validation rules."""

from __future__ import annotations

from evaluation.evidence.models import EvidenceArtifact, EvidenceItem
from evaluation.evidence.validate import validate_artifact, validate_item


def _item(
    *,
    evidence_id: str = "testing.test_files",
    category: str = "testing",
    status: str = "FOUND",
    source_paths: list[str] | None = None,
    observation: str = "N test files observed.",
    notes: str | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        case_id="C001",
        category=category,
        evidence_type=evidence_id.split(".", 1)[1],
        status=status,
        observation=observation,
        source_paths=source_paths if source_paths is not None else ["tests/a_test.go"],
        extractor="testing",
        extractor_version="1",
        notes=notes,
    )


def _artifact(items: list[EvidenceItem]) -> EvidenceArtifact:
    return EvidenceArtifact(
        schema_version=1,
        case_id="C001",
        name="lib",
        repository_url="https://example.com/x.git",
        requested_commit="a",
        verified_commit="b",
        snapshot_content_hash="c",
        extraction_version="v1",
        evidence_identity="repoguard-evidence-v1:deadbeef",
        generated_at="2026-08-28T00:00:00Z",
        items=items,
    )


def _all_five_categories() -> list[EvidenceItem]:
    items = []
    for category in ("architecture", "testing", "maintainability", "dependencies", "documentation"):
        for _i in range(1):
            items.append(
                _item(
                    evidence_id=f"{category}.sample",
                    category=category,
                    observation=f"{category} observation.",
                )
            )
    return items


def test_valid_artifact_has_no_problems() -> None:
    assert validate_artifact(_artifact(_all_five_categories())) == []


def test_found_requires_source_path() -> None:
    item = _item(source_paths=[])
    problems = validate_item(item)
    assert any("FOUND without any source path" in p for p in problems)


def test_absolute_windows_path_rejected() -> None:
    item = _item(source_paths=["C:\\Users\\x\\main.go"])
    assert any("not a repository-relative" in p for p in validate_item(item))


def test_absolute_unix_path_rejected() -> None:
    item = _item(source_paths=["/home/user/main.go"])
    assert any("not a repository-relative" in p for p in validate_item(item))


def test_traversal_path_rejected() -> None:
    item = _item(source_paths=["src/../main.go"])
    assert any("not a repository-relative" in p for p in validate_item(item))


def test_backslash_path_rejected() -> None:
    item = _item(source_paths=["src\\main.go"])
    assert any("not a repository-relative" in p for p in validate_item(item))


def test_invalid_status_rejected() -> None:
    item = _item(status="MISSING")
    problems = validate_item(item)
    assert any("invalid evidence status" in p for p in problems)


def test_invalid_category_rejected() -> None:
    item = _item(category="quality")
    problems = validate_item(item)
    assert any("invalid evidence category" in p for p in problems)


def test_duplicate_evidence_id_rejected() -> None:
    artifact = _artifact(_all_five_categories())
    duplicate = _all_five_categories()
    artifact.items = _all_five_categories() + duplicate
    problems = validate_artifact(artifact)
    assert any("duplicate evidence_id" in p for p in problems)


def test_missing_category_rejected() -> None:
    artifact = _artifact(_all_five_categories()[:-1])
    problems = validate_artifact(artifact)
    assert any("no evidence items produced for category: documentation" in p for p in problems)


def test_identity_scheme_required() -> None:
    artifact = _artifact(_all_five_categories())
    artifact.evidence_identity = "sha256:abc"
    problems = validate_artifact(artifact)
    assert any("does not use the extraction scheme" in p for p in problems)


def test_unsupported_schema_version_rejected() -> None:
    artifact = _artifact(_all_five_categories())
    artifact.schema_version = 2
    problems = validate_artifact(artifact)
    assert any("unsupported schema_version" in p for p in problems)


def test_forbidden_quality_word_rejected() -> None:
    item = _item(observation="The architecture is weak and unmaintainable.")
    problems = validate_item(item)
    assert any("forbidden quality/scoring word" in p for p in problems)


def test_quality_word_in_notes_rejected() -> None:
    item = _item(notes="notably strong overall")
    problems = validate_item(item)
    assert any("forbidden quality/scoring word" in p for p in problems)


def test_score_word_rejected() -> None:
    item = _item(observation="Assigning a maintainability score here.")
    problems = validate_item(item)
    assert any("forbidden quality/scoring word" in p for p in problems)


def test_not_found_without_paths_is_valid_for_non_found() -> None:
    item = _item(status="NOT_FOUND", source_paths=[])
    assert validate_item(item) == []
