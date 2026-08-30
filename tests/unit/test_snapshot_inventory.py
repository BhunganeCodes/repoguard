"""Repository inventory generation tests."""

from __future__ import annotations

from evaluation.snapshot.inventory import build_inventory
from evaluation.snapshot.models import ManifestCase

SHA = "e80360834b59dd4c8bfd45344ad1478ab9f86565"


def _case() -> ManifestCase:
    return ManifestCase(
        candidate_id="C001",
        name="sample",
        url="file:///sample",
        pinned_commit=SHA,
        ecosystem="Go",
        license="MIT",
        dataset_decision="include",
        dataset_status="confirmed",
    )


FILES = [
    "LICENSE",
    "README.md",
    "go.mod",
    "go.sum",
    ".github/workflows/ci.yml",
    ".circleci/config.yml",
    "Dockerfile",
    "compose.yaml",
    "main.go",
    "internal/parser_test.py",
    "docs/guide.md",
    "src/parser.py",
    "src/style.css",
]


def test_inventory_counts_and_presence() -> None:
    inv = build_inventory(
        case=_case(),
        verified_commit=SHA,
        content_hash="abc",
        acquired_at="2026-08-28T00:00:00Z",
        tracked_files=FILES,
        top_level=[
            "LICENSE",
            "README.md",
            "go.mod",
            "Dockerfile",
            "docs",
            "internal",
            "src",
            ".github",
        ],
    )
    assert inv.tracked_file_count == len(FILES)
    # .go, .py are source; .css is not treated as source
    assert inv.source_file_count == 3
    assert inv.test_file_count == 1
    assert inv.documentation_file_count == 2  # README.md + docs/guide.md
    assert inv.dependency_manifest.present and inv.dependency_manifest.paths == ["go.mod"]
    assert inv.lockfile.present and inv.lockfile.paths == ["go.sum"]
    assert inv.ci.present
    assert ".github/workflows/ci.yml" in inv.ci.paths
    assert inv.docker.present and inv.docker.paths == ["Dockerfile", "compose.yaml"]
    assert inv.readme == "README.md"
    assert inv.license_file == "LICENSE"


def test_inventory_languages() -> None:
    inv = build_inventory(
        case=_case(),
        verified_commit=SHA,
        content_hash="abc",
        acquired_at="2026-08-28T00:00:00Z",
        tracked_files=FILES,
        top_level=[],
    )
    by_name = {lang.language: lang.file_count for lang in inv.detected_languages}
    assert by_name["Go"] == 1  # main.go only; go.mod / go.sum are not source-by-extension
    assert by_name["Python"] == 2
    assert by_name["Markdown"] == 2  # README.md + docs/guide.md
    assert by_name["CSS"] == 1


def test_inventory_absence() -> None:
    inv = build_inventory(
        case=_case(),
        verified_commit=SHA,
        content_hash="abc",
        acquired_at="2026-08-28T00:00:00Z",
        tracked_files=["main.go"],
        top_level=["main.go"],
    )
    assert not inv.dependency_manifest.present
    assert not inv.lockfile.present
    assert not inv.ci.present
    assert not inv.docker.present
    assert inv.readme is None
    assert inv.license_file is None


def test_dockerfile_with_suffix_matches() -> None:
    inv = build_inventory(
        case=_case(),
        verified_commit=SHA,
        content_hash="abc",
        acquired_at="2026-08-28T00:00:00Z",
        tracked_files=["Dockerfile.dev"],
        top_level=["Dockerfile.dev"],
    )
    assert inv.docker.present
