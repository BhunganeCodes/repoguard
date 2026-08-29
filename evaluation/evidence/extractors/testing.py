"""Testing evidence extractor.

Reports mechanically observable facts about tests: presence and location of
test files, naming conventions, test configuration, declared test commands,
coverage configuration, integration/E2E markers, and fixture/mock assets.
"""

from __future__ import annotations

import re

from evaluation.evidence.extractors.base import (
    MAX_SOURCE_PATHS_PER_ITEM,
    ExtractionContext,
    dirname,
    make_item,
    norm,
    ordered,
    read_lines,
)
from evaluation.evidence.models import EvidenceItem

NAME = "testing"
VERSION = "1"

_TEST_DIR_NAMES = frozenset({"test", "tests", "spec", "__tests__", "e2e"})

# Basename test-marker patterns, applied case-insensitively to the file name.
_TEST_NAME_PATTERNS = (
    re.compile(r"^test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r"^test_.*\.(go|rs|jl)$"),
    re.compile(r".*_test\.(go|rs|jl)$"),
    re.compile(r".*\.test\.(js|jsx|ts|tsx|mjs|cts)$"),
    re.compile(r".*\.spec\.(js|jsx|ts|tsx|rb|go|rs)$"),
    re.compile(r".*_spec\.rb$"),
    re.compile(r"^spec_.*\.rb$"),
    re.compile(r"^.*\.(test|spec)\.(py|go|rs)$"),
)

_TEST_CONFIG_FILENAMES = frozenset(
    {
        "pytest.ini",
        "vitest.config.ts",
        "vitest.config.js",
        "jest.config.ts",
        "jest.config.js",
        ".mocharc.json",
        ".mocharc.js",
        ".mocharc.yml",
        "karma.conf.js",
        "jasmine.json",
        "phpunit.xml",
        "phpunit.xml.dist",
        "cypress.config.ts",
        "cypress.config.js",
        "playwright.config.ts",
        "playwright.config.js",
        ".rspec",
        "Rakefile",
    }
)

# Config files that may carry test configuration in a non-obvious section.
_SECTION_CONFIG_FILENAMES = frozenset({"pyproject.toml", "tox.ini", "setup.cfg", "pytest.ini"})
_COVERAGE_CONFIG_NAMES = frozenset(
    {".coveragerc", ".codecov.yml", "codecov.yml", "codecov.yaml", "coverage.xml"}
)

_TEST_COMMAND_TOKENS = (
    "go test",
    "pytest",
    "npm test",
    "npm run test",
    "yarn test",
    "pnpm test",
    "cargo test",
    "mvn test",
    "gradle test",
    "npx jest",
    "bazel test",
    "deno test",
    "rails test",
    "rspec",
    "phpunit",
    "mix test",
    "dotnet test",
    "pants test",
)

_TEST_GENERIC_FILE_PATTERNS = re.compile(r"(^|[/_.-])test$|(^|[/_.-])tests$", re.IGNORECASE)


def is_test_file(path: str) -> bool:
    cleaned = norm(path)
    name = cleaned.rsplit("/", 1)[-1]
    lower = cleaned.lower()
    if _TEST_GENERIC_FILE_PATTERNS.search(lower):
        return True
    for pattern in _TEST_NAME_PATTERNS:
        if pattern.match(name):
            return True
    return False


def _test_dirs_of(test_files: list[str]) -> list[str]:
    return sorted({dirname(f) or "." for f in test_files})


def _naming_conventions(test_files: list[str]) -> list[str]:
    conventions: set[str] = set()
    for path in test_files:
        name = norm(path).rsplit("/", 1)[-1].lower()
        if name.startswith("test_"):
            conventions.add("test_ prefix")
        if (
            name.endswith("_test.py")
            or name.endswith("_test.go")
            or name.endswith("_test.rs")
            or name.endswith("_test.jl")
        ):
            conventions.add("_test suffix")
        if ".test." in name:
            conventions.add(".test. infix")
        if ".spec." in name:
            conventions.add(".spec. infix")
        if name.endswith("_spec.rb") or name.startswith("spec_"):
            conventions.add("spec suffix/prefix")
    return sorted(conventions)


def _has_section(lines: list[str], section_marker: str) -> bool:
    return any(section_marker in line for line in lines)


def extract(ctx: ExtractionContext) -> list[EvidenceItem]:
    items = []
    test_files = [f for f in ctx.tracked_files if is_test_file(f)]

    if test_files:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_files",
                status="FOUND",
                observation=(
                    f"{len(test_files)} test files observed "
                    f"(tracked files: {len(ctx.tracked_files)})."
                ),
                source_paths=test_files[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"test_file_count": len(test_files)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_files",
                status="NOT_FOUND",
                observation="No test files observed by name or location.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    test_dirs = _test_dirs_of(test_files)
    if test_dirs:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_directories",
                status="FOUND",
                observation="Test files reside in directories: " + ", ".join(test_dirs) + ".",
                source_paths=test_files[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"test_directories": test_dirs},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_directories",
                status="NOT_FOUND",
                observation="No dedicated test directories observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    conventions = _naming_conventions(test_files)
    if conventions:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_naming_conventions",
                status="FOUND",
                observation="Naming conventions observed: " + ", ".join(conventions) + ".",
                source_paths=test_files[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"naming_conventions": conventions},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_naming_conventions",
                status="NOT_FOUND",
                observation="No test naming conventions observed (no test files).",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    config_paths: list[str] = []
    for f in ctx.tracked_files:
        base = norm(f).rsplit("/", 1)[-1]
        if base in _TEST_CONFIG_FILENAMES:
            config_paths.append(norm(f))
        elif base in _SECTION_CONFIG_FILENAMES:
            lines = read_lines(ctx.checkout, norm(f), limit=80)
            text = "\n".join(lines).lower()
            if any(m in text for m in ("[tool.pytest", "[pytest", "pytest.ini_options")):
                config_paths.append(norm(f))
            elif "tool.vitest" in text or "vitest" in text:
                pass
    if test_files and config_paths:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_configuration",
                status="FOUND",
                observation=("Test configuration files observed: " + ", ".join(config_paths) + "."),
                source_paths=config_paths,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    elif test_files:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_configuration",
                status="NOT_FOUND",
                observation="Test files exist but no dedicated test configuration files observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_configuration",
                status="NOT_FOUND",
                observation="No test configuration observed (no test files).",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    commands = _declared_test_commands(ctx)
    if commands:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_commands",
                status="FOUND",
                observation=(
                    "Declared test invocation commands observed: " + "; ".join(commands) + "."
                ),
                source_paths=_commands_paths(ctx),
                observed={"test_commands": commands},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="test_commands",
                status="NOT_FOUND",
                observation="No declared test invocation commands observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    coverage_paths = _coverage_config(ctx, test_files)
    if coverage_paths:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="coverage_configuration",
                status="FOUND",
                observation=(
                    "Coverage configuration observed in: " + ", ".join(coverage_paths) + "."
                ),
                source_paths=coverage_paths,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="coverage_configuration",
                status="NOT_FOUND",
                observation="No coverage configuration observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    e2e = _integration_e2e_paths(ctx)
    if e2e:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="integration_e2e_indicators",
                status="FOUND",
                observation=(
                    "Integration/E2E markers observed: "
                    + ", ".join(e2e[:MAX_SOURCE_PATHS_PER_ITEM])
                    + ("" if len(e2e) <= MAX_SOURCE_PATHS_PER_ITEM else " ...")
                    + "."
                ),
                source_paths=e2e[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"marker_count": len(e2e)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="integration_e2e_indicators",
                status="NOT_FOUND",
                observation="No integration or E2E markers observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    fixtures = _fixture_mock_paths(ctx)
    if fixtures:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="fixtures_mocks",
                status="FOUND",
                observation=(
                    "Fixture/mock directories or files observed: "
                    + ", ".join(fixtures[:MAX_SOURCE_PATHS_PER_ITEM])
                    + ("" if len(fixtures) <= MAX_SOURCE_PATHS_PER_ITEM else " ...")
                    + "."
                ),
                source_paths=fixtures[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"fixture_asset_count": len(fixtures)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="testing",
                evidence_type="fixtures_mocks",
                status="NOT_FOUND",
                observation="No fixture or mock directories/files observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    return items


def _commands_paths(ctx: ExtractionContext) -> list[str]:
    paths: list[str] = []
    for f in ctx.tracked_files:
        base = norm(f).rsplit("/", 1)[-1].lower()
        if base in {"package.json", "makefile", "cargo.toml"}:
            paths.append(norm(f))
    cidirs = [d for d in (".github", "workflows") if d in ctx.top_level_dirs]
    for d in cidirs:
        paths += [f for f in ctx.tracked_files if f.startswith(d + "/")]
    return ordered(paths)


def _declared_test_commands(ctx: ExtractionContext) -> list[str]:
    commands: set[str] = set()
    for f in ctx.tracked_files:
        base = norm(f).rsplit("/", 1)[-1].lower()
        if base == "package.json":
            lines = read_lines(ctx.checkout, norm(f), limit=400)
            text = "\n".join(lines)
            for token in _TEST_COMMAND_TOKENS:
                if token in text:
                    commands.add(token)
        elif base in {"makefile", "gnumakefile", "makefile.am"}:
            lines = read_lines(ctx.checkout, norm(f), limit=400)
            for line in lines:
                if re.match(r"^\s*test\s*:", line) or "test:" in line:
                    for token in _TEST_COMMAND_TOKENS:
                        if token in line:
                            commands.add(token)
    ci_files = [
        f
        for f in ctx.tracked_files
        if "/.github/workflows/" in f
        or f.endswith("Jenkinsfile")
        or f == ".gitlab-ci.yml"
        or f == ".circleci/config.yml"
        or f.startswith(".github/workflows/")
    ]
    for f in ci_files:
        lines = read_lines(ctx.checkout, norm(f), limit=200)
        for line in lines:
            for token in _TEST_COMMAND_TOKENS:
                if token in line:
                    commands.add(token)
    return sorted(commands)


def _coverage_config(ctx: ExtractionContext, test_files: list[str]) -> list[str]:
    paths: list[str] = []
    for f in ctx.tracked_files:
        base = norm(f).rsplit("/", 1)[-1]
        if base in _COVERAGE_CONFIG_NAMES:
            paths.append(norm(f))
    for f in ctx.tracked_files:
        base = norm(f).rsplit("/", 1)[-1]
        if base == "pyproject.toml":
            text = "\n".join(read_lines(ctx.checkout, norm(f), limit=200))
            if "coverage" in text.lower() or "--cov" in text:
                paths.append(norm(f))
        elif base == "package.json":
            text = "\n".join(read_lines(ctx.checkout, norm(f), limit=200))
            if "coverage" in text.lower():
                paths.append(norm(f))
    return ordered(paths)


def _integration_e2e_paths(ctx: ExtractionContext) -> list[str]:
    matches: list[str] = []
    for f in ctx.tracked_files:
        lower = norm(f).lower()
        parts = lower.split("/")
        if any(p in _TEST_DIR_NAMES for p in parts) and any(
            p in {"integration", "e2e", "acceptance"} for p in parts
        ):
            matches.append(norm(f))
        elif "/e2e/" in lower or "/integration/" in lower or "e2e" == parts[-1]:
            matches.append(norm(f))
    e2e_config = [f for f in ctx.tracked_files if "cypress.config" in f or "playwright.config" in f]
    return ordered(matches + e2e_config)


def _fixture_mock_paths(ctx: ExtractionContext) -> list[str]:
    matches: list[str] = []
    fixture_dirs = {"fixtures", "mocks", "testdata", "__mocks__", "stubs"}
    for f in ctx.tracked_files:
        parts = norm(f).split("/")
        if any(p in fixture_dirs for p in parts):
            matches.append(norm(f))
            continue
        base = norm(f).rsplit("/", 1)[-1].lower()
        if ".mock." in base or ".fixture." in base or base.endswith("_fixtures.go"):
            matches.append(norm(f))
    return ordered(matches)
