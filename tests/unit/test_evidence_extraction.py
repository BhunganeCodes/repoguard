"""End-to-end evidence extraction tests (local fixture trees, no git needed).

Extractors are exercised directly over a constructed ``ExtractionContext``
with a temporary checkout directory. The full snapshot pipeline (git
checkout + record) is covered in ``test_evidence_pipeline.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

from evaluation.evidence._version import EXTRACTION_SCHEME
from evaluation.evidence.extractors import registry
from evaluation.evidence.extractors.base import ExtractionContext
from evaluation.evidence.models import EvidenceItem
from evaluation.evidence.serialize import canonical_dump
from evaluation.evidence.validate import FORBIDDEN_QUALITY_WORDS, validate_artifact, validate_item


def build_context(
    tmp_path: Path,
    files: dict[str, str],
    *,
    case_id: str = "T001",
) -> tuple[ExtractionContext, Path]:
    checkout = tmp_path / "checkout"
    checkout.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        target = checkout / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    context = ExtractionContext(
        checkout=checkout,
        tracked_files=sorted(files),
        case_id=case_id,
        name="fixture",
        repository_url="https://example.com/fixture.git",
        requested_commit="a" * 40,
        verified_commit="a" * 40,
        snapshot_content_hash="hash",
    )
    return context, checkout


def extract_all(context: ExtractionContext) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for _category, _name, _version, extract_fn in registry():
        items.extend(extract_fn(context))
    return items


def item_map(items: list[EvidenceItem]) -> dict[str, EvidenceItem]:
    return {item.evidence_id: item for item in items}


def test_architecture_extractor_finds_structure(tmp_path: Path) -> None:
    files = {
        "main.go": "package main\n",
        "cmd/app/main.go": "package main\n",
        "pkg/util/util.go": "package util\n",
        "internal/core/core.go": "package core\n",
        "tests/main_test.go": "package main\nfunc TestMain(t *testing.T) {}\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))

    assert items["architecture.top_level_structure"].status == "FOUND"
    assert items["architecture.module_boundaries"].status == "FOUND"
    assert "cmd" in items["architecture.module_boundaries"].observation
    assert items["architecture.source_test_separation"].status == "FOUND"
    assert items["architecture.dependency_direction_markers"].status == "FOUND"
    assert "internal" in items["architecture.dependency_direction_markers"].observation
    assert items["architecture.config_boundaries"].status == "NOT_FOUND"
    assert items["architecture.architecture_docs"].status == "NOT_FOUND"


def test_architecture_config_boundaries_found(tmp_path: Path) -> None:
    files = {
        ".github/workflows/ci.yml": "on: push\n",
        "config/app.yaml": "a: 1\n",
        "main.go": "package main\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))
    assert items["architecture.config_boundaries"].status == "FOUND"


def test_testing_extractor(tmp_path: Path) -> None:
    files = {
        "tests/main_test.go": "package main\nfunc TestMain(t *testing.T) {}\n",
        "pytest.ini": "[pytest]\n",
        ".github/workflows/test.yml": ("jobs:\n  test:\n    steps:\n      - run: go test ./...\n"),
        "testdata/sample.txt": "fixture\n",
        "internal/core/core.go": "package core\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))

    assert items["testing.test_files"].status == "FOUND"
    assert items["testing.test_directories"].status == "FOUND"
    assert items["testing.test_naming_conventions"].status == "FOUND"
    assert items["testing.test_configuration"].status == "FOUND"
    assert "pytest.ini" in items["testing.test_configuration"].observation
    assert items["testing.test_commands"].status == "FOUND"
    assert "go test" in items["testing.test_commands"].observation
    assert items["testing.coverage_configuration"].status == "NOT_FOUND"
    assert items["testing.integration_e2e_indicators"].status == "NOT_FOUND"
    assert items["testing.fixtures_mocks"].status == "FOUND"
    assert "testdata" in items["testing.fixtures_mocks"].observation


def test_testing_integration_markers(tmp_path: Path) -> None:
    files = {
        "e2e/scenario.py": "def test_scenario():\n    pass\n",
        "playwright.config.ts": "export default {}\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))
    assert items["testing.integration_e2e_indicators"].status == "FOUND"


def test_no_tests_produces_not_found(tmp_path: Path) -> None:
    files = {"main.go": "package main\n", "internal/core/core.go": "package core\n"}
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))
    assert items["testing.test_files"].status == "NOT_FOUND"
    assert items["testing.test_configuration"].status == "NOT_FOUND"
    assert items["testing.test_naming_conventions"].status == "NOT_FOUND"


def test_empty_repo_all_not_found_valid(tmp_path: Path) -> None:
    context, _checkout = build_context(tmp_path, {})
    items = extract_all(context)
    assert items
    for item in items:
        assert item.status in {"FOUND", "NOT_FOUND", "UNCERTAIN", "NOT_APPLICABLE"}
        problems = validate_item(item)
        assert problems == [], problems


def test_dependencies_go_module(tmp_path: Path) -> None:
    go_mod = (
        "module example.com/x\n\ngo 1.22\n\nrequire (\n"
        "\tgithub.com/a/b v1.0.0\n\tgithub.com/c/d v0.5.0 // indirect\n)\n"
    )
    files = {
        "go.mod": go_mod,
        "go.sum": "github.com/a/b v1.0.0 h1:hash\n",
        "main.go": "package main\n",
        "internal/core/core.go": "package core\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))

    assert items["dependencies.dependency_manifests"].status == "FOUND"
    assert "go.mod" in items["dependencies.dependency_manifests"].observation
    assert items["dependencies.lockfiles"].status == "FOUND"
    assert items["dependencies.dependency_declarations"].status == "FOUND"
    assert items["dependencies.dependency_declarations"].observed["direct_dependency_count"] == 2
    assert items["dependencies.version_pinning"].status == "FOUND"
    assert items["dependencies.dev_test_dependencies"].status == "NOT_FOUND"
    assert items["dependencies.workspace_monorepo"].status == "NOT_FOUND"
    assert items["dependencies.vendored_dependencies"].status == "NOT_FOUND"


def test_dependencies_pyproject(tmp_path: Path) -> None:
    pyproject = (
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        'dependencies = ["requests>=2.31", "click==8.1.7"]\n'
        '[project.optional-dependencies]\ndev = ["pytest>=8"]\n'
    )
    files = {"pyproject.toml": pyproject, "demo/__init__.py": ""}
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))

    assert items["dependencies.dependency_manifests"].status == "FOUND"
    assert items["dependencies.dependency_declarations"].status == "FOUND"
    assert items["dependencies.dependency_declarations"].observed["direct_dependency_count"] == 2
    pinning = items["dependencies.version_pinning"]
    assert pinning.observed == {"exact": 1, "range": 1, "unversioned": 0}
    assert items["dependencies.dev_test_dependencies"].status == "FOUND"


def test_dependencies_malformed_manifest_is_uncertain(tmp_path: Path) -> None:
    files = {"package.json": "{not valid json", "main.js": "console.log(1)\n"}
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))
    assert items["dependencies.dependency_manifests"].status == "FOUND"
    assert items["dependencies.dependency_declarations"].status == "UNCERTAIN"


def test_dependencies_vendored_and_workspace(tmp_path: Path) -> None:
    files = {
        "go.work": "go 1.22\n",
        "vendor/modules.txt": "# example.com/x v0.0.0\n",
        "vendor/example.com/x/a.go": "package x\n",
        "main.go": "package main\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))
    assert items["dependencies.workspace_monorepo"].status == "FOUND"
    assert items["dependencies.vendored_dependencies"].status == "FOUND"


def test_documentation_extractor(tmp_path: Path) -> None:
    files = {
        "README.md": "# Demo\n",
        "docs/guide.md": "## Guide\n",
        "docs/architecture.md": "## Design\n",
        "CHANGELOG.md": "# Changelog\n",
        "CONTRIBUTING.md": "## Contributing\n",
        "mkdocs.yml": "site_name: Demo\n",
        "examples/demo.go": "package main\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))

    assert items["documentation.readme"].status == "FOUND"
    assert items["documentation.documentation_directories"].status == "FOUND"
    assert items["documentation.api_docs_config"].status == "FOUND"
    assert items["documentation.contribution_guides"].status == "FOUND"
    assert items["documentation.architecture_docs"].status == "FOUND"
    assert items["documentation.changelog_release_notes"].status == "FOUND"
    assert items["documentation.examples_tutorials"].status == "FOUND"


def test_no_documentation(tmp_path: Path) -> None:
    files = {"main.go": "package main\n"}
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))
    assert items["documentation.readme"].status == "NOT_FOUND"
    assert items["documentation.documentation_directories"].status == "NOT_FOUND"


def test_maintainability_extractor(tmp_path: Path) -> None:
    files = {
        ".ruff.toml": "line-length = 100\n",
        ".editorconfig": "root = true\n",
        "mypy.ini": "[mypy]\n",
        ".github/workflows/ci.yml": "on: push\n",
        "CONTRIBUTING.md": "## Contributing\n",
        "src/a.py": "# TODO: fix this\nvalue = 1\n",
        "src/b.py": "# Code generated by gen. DO NOT EDIT.\nvalue = 2\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = item_map(extract_all(context))

    assert items["maintainability.formatting_config"].status == "FOUND"
    assert items["maintainability.lint_config"].status == "FOUND"
    assert items["maintainability.static_analysis_config"].status == "FOUND"
    assert items["maintainability.ci_workflows"].status == "FOUND"
    assert items["maintainability.contribution_docs"].status == "FOUND"
    assert items["maintainability.code_organization"].status == "FOUND"
    assert items["maintainability.generated_code_markers"].status == "FOUND"
    assert items["maintainability.todo_fixme_counts"].status == "FOUND"
    counts = items["maintainability.todo_fixme_counts"].observed or {}
    assert counts["TODO"] == 1


def test_deterministic_repeated_extraction(tmp_path: Path) -> None:
    files = {
        "README.md": "# Demo\n",
        "go.mod": "module example.com/x\n\ngo 1.22\n\nrequire github.com/a/b v1.0.0\n",
        "main.go": "package main\n",
        "tests/main_test.go": "package main\nfunc TestMain(t *testing.T) {}\n",
        "internal/core/core.go": "package core\n",
        ".github/workflows/ci.yml": "on: push\n",
        "docs/guide.md": "## Guide\n",
    }
    context, checkout = build_context(tmp_path, files)
    first = extract_all(context)
    second = extract_all(context)
    assert canonical_dump([item.to_dict() for item in first]) == canonical_dump(
        [item.to_dict() for item in second]
    )


def test_artifact_equivalent_across_identical_tree(tmp_path: Path) -> None:
    specs = {
        "README.md": "# Demo\n",
        "go.mod": "module example.com/x\n\ngo 1.22\n\nrequire github.com/a/b v1.0.0\n",
        "main.go": "package main\n",
        "tests/main_test.go": "package main\n",
    }
    context_one, _ = build_context(tmp_path / "one", specs)
    context_two, _ = build_context(tmp_path / "two", specs)
    first = extract_all(context_one)
    second = extract_all(context_two)
    assert canonical_dump([item.to_dict() for item in first]) == canonical_dump(
        [item.to_dict() for item in second]
    )


def test_no_absolute_paths_in_output(tmp_path: Path) -> None:
    files = {
        "README.md": "# Demo\n",
        "go.mod": "module example.com/x\n\ngo 1.22\n",
        "main.go": "package main\n",
        "tests/main_test.go": "package main\n",
        "internal/core/core.go": "package core\n",
        "docs/guide.md": "## Guide\n",
    }
    context, checkout = build_context(tmp_path, files)
    items = extract_all(context)
    rendered = canonical_dump([item.to_dict() for item in items])
    assert str(checkout) not in rendered
    assert str(tmp_path) not in rendered
    for item in items:
        for path in item.source_paths:
            assert not path.startswith("/")
            assert not re.match(r"^[A-Za-z]:[\\/]", path)
            assert ".." not in path.split("/")
            assert "\\" not in path


def test_no_forbidden_quality_words_in_observations(tmp_path: Path) -> None:
    files = {
        "README.md": "# Demo\n",
        "go.mod": "module example.com/x\n\ngo 1.22\n\nrequire github.com/a/b v1.0.0\n",
        "main.go": "package main\n",
        "tests/main_test.go": "package main\n",
        "internal/core/core.go": "package core\n",
        ".github/workflows/ci.yml": "on: push\n",
        "docs/architecture.md": "## Design\n",
        "src/a.py": "# TODO: fixme\n",
        "e2e/scenario.py": "def test_scenario():\n    pass\n",
        "playwright.config.ts": "export default {}\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = extract_all(context)
    for item in items:
        text = f"{item.observation} {item.notes or ''}".lower()
        for word in FORBIDDEN_QUALITY_WORDS:
            assert f" {word} " not in f" {text} ", (item.evidence_id, word)


def test_full_artifact_passes_validation(tmp_path: Path) -> None:
    files = {
        "README.md": "# Demo\n",
        "go.mod": "module example.com/x\n\ngo 1.22\n\nrequire github.com/a/b v1.0.0\n",
        "main.go": "package main\n",
        "tests/main_test.go": "package main\n",
        "internal/core/core.go": "package core\n",
        ".ruff.toml": "line-length = 100\n",
        "docs/guide.md": "## Guide\n",
        "mkdocs.yml": "site_name: Demo\n",
    }
    context, _checkout = build_context(tmp_path, files)
    items = extract_all(context)

    from evaluation.evidence.models import EvidenceArtifact

    artifact = EvidenceArtifact(
        schema_version=1,
        case_id="T001",
        name="fixture",
        repository_url="https://example.com/fixture.git",
        requested_commit="a" * 40,
        verified_commit="a" * 40,
        snapshot_content_hash="hash",
        extraction_version="v1",
        evidence_identity="",
        generated_at="2026-08-28T00:00:00Z",
        items=items,
    )
    from evaluation.evidence.serialize import content_identity

    artifact.evidence_identity = content_identity(artifact)
    assert artifact.evidence_identity.startswith(EXTRACTION_SCHEME + ":")
    assert validate_artifact(artifact) == []
