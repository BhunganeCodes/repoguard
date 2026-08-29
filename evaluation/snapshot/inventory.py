"""Machine-readable repository inventory generation.

All observations are raw facts about the snapshot tree: counts and
presence flags. Nothing here is a quality judgment or score.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from evaluation.snapshot.models import Inventory, LanguageCount, ManifestCase, Presence

_SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".clj",
    ".cpp",
    ".cs",
    ".cxx",
    ".dart",
    ".ex",
    ".exs",
    ".go",
    ".h",
    ".hpp",
    ".hrl",
    ".hs",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".mjs",
    ".php",
    ".pl",
    ".pm",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}

_DOCUMENTATION_EXTENSIONS = {
    ".adoc",
    ".asciidoc",
    ".markdown",
    ".mdown",
    ".mkd",
    ".md",
    ".rst",
}

_LANGUAGE_BY_EXTENSION = {
    ".c": "C",
    ".cc": "C++",
    ".clj": "Clojure",
    ".cpp": "C++",
    ".cs": "C#",
    ".cxx": "C++",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".go": "Go",
    ".h": "C",
    ".hpp": "C++",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".java": "Java",
    ".js": "JavaScript",
    ".json": "JSON",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".lua": "Lua",
    ".md": "Markdown",
    ".mjs": "JavaScript",
    ".php": "PHP",
    ".pl": "Perl",
    ".pm": "Perl",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".scala": "Scala",
    ".sh": "Shell",
    ".swift": "Swift",
    ".toml": "TOML",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".css": "CSS",
    ".html": "HTML",
}

_MANIFEST_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "cargo.toml",
    "composer.json",
    "gemfile",
    "go.mod",
    "gopkg.toml",
    "mix.exs",
    "package.json",
    "pom.xml",
    "pubspec.yaml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "settings.gradle",
}

_LOCKFILE_NAMES = {
    "cargo.lock",
    "composer.lock",
    "constraints.lock",
    "gemfile.lock",
    "go.sum",
    "gradle.lockfile",
    "mix.lock",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "poetry.lock",
    "pubspec.lock",
    "requirements.lock",
    "yarn.lock",
}

_CI_DIRS = (".buildkite", ".circleci", ".github/actions", ".github/workflows", ".gitlab-ci")
_CI_NAMES = {
    "appveyor.yml",
    "azure-pipelines.yml",
    ".gitlab-ci.yml",
    "jenkinsfile",
    ".travis.yml",
}

_DOCKER_NAMES = {
    ".dockerignore",
    "containerfile",
    "containerfile.*",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "dockerfile",
    "dockerfile.*",
}

_TEST_SEGMENTS = {"__tests__", "spec", "specs", "test", "tests"}


def _presence_from_dict(raw: dict[str, object], key: str) -> Presence:
    entry = raw.get(key)
    if not isinstance(entry, dict):
        return Presence(present=False)
    paths = entry.get("paths")
    return Presence(
        present=bool(entry.get("present")),
        paths=[str(p) for p in paths] if isinstance(paths, list) else [],
    )


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return default


def inventory_from_dict(raw: dict[str, object], *, fallback_ecosystem: str) -> Inventory:
    """Rebuild an Inventory from a previously written inventory.yaml mapping."""
    languages_raw = raw.get("detected_languages")
    languages: list[LanguageCount] = []
    if isinstance(languages_raw, list):
        for entry in languages_raw:
            if isinstance(entry, dict) and isinstance(entry.get("language"), str):
                languages.append(
                    LanguageCount(
                        language=entry["language"],
                        file_count=_as_int(entry.get("file_count"), 0),
                    )
                )
    top_level_raw = raw.get("top_level")
    return Inventory(
        repository_id=str(raw.get("repository_id", "")),
        repository_url=str(raw.get("repository_url", "")),
        requested_commit=str(raw.get("requested_commit", "")),
        verified_commit=str(raw.get("verified_commit", "")),
        content_hash=str(raw.get("content_hash", "")),
        acquired_at=str(raw.get("acquired_at", "")),
        ecosystem=str(raw.get("ecosystem", fallback_ecosystem)),
        detected_languages=languages,
        tracked_file_count=_as_int(raw.get("tracked_file_count"), 0),
        source_file_count=_as_int(raw.get("source_file_count"), 0),
        test_file_count=_as_int(raw.get("test_file_count"), 0),
        documentation_file_count=_as_int(raw.get("documentation_file_count"), 0),
        dependency_manifest=_presence_from_dict(raw, "dependency_manifest"),
        lockfile=_presence_from_dict(raw, "lockfile"),
        ci=_presence_from_dict(raw, "ci"),
        docker=_presence_from_dict(raw, "docker"),
        readme=str(raw["readme"]) if raw.get("readme") else None,
        license_file=str(raw["license_file"]) if raw.get("license_file") else None,
        top_level=[str(i) for i in top_level_raw] if isinstance(top_level_raw, list) else [],
    )


def _is_test_file(relative: PurePosixPath) -> bool:
    parts = [part.lower() for part in relative.parts[:-1]]
    if any(segment in _TEST_SEGMENTS for segment in parts):
        return True
    stem = relative.name.lower().rsplit(".", 1)[0]
    return "test" in stem or "spec" in stem


def _name_matches(relative: PurePosixPath, names: set[str]) -> bool:
    lowered = relative.name.lower()
    if any(lowered == name for name in names if not name.endswith(".*")):
        return True
    return any(lowered.startswith(name[:-2]) for name in names if name.endswith(".*"))


def _first_entry_matches(relative: PurePosixPath, dirs: tuple[str, ...]) -> bool:
    posix = relative.as_posix().lower()
    return any(posix == d or posix.startswith(d + "/") for d in dirs)


def build_inventory(
    case: ManifestCase,
    verified_commit: str,
    content_hash: str,
    acquired_at: str,
    tracked_files: list[str],
    top_level: list[str],
) -> Inventory:
    """Build the inventory from tracked file paths at the pinned commit."""
    manifest_paths: list[str] = []
    lock_paths: list[str] = []
    ci_paths: list[str] = []
    docker_paths: list[str] = []
    readme: str | None = None
    license_file: str | None = None
    source_count = 0
    test_count = 0
    documentation_count = 0
    language_counts: dict[str, int] = {}

    for path in tracked_files:
        relative = PurePosixPath(path)
        lowered_name = relative.name.lower()
        extension = relative.suffix.lower()

        if extension in _SOURCE_EXTENSIONS:
            source_count += 1
        if _is_test_file(relative):
            test_count += 1
        if extension in _DOCUMENTATION_EXTENSIONS:
            documentation_count += 1

        language = _LANGUAGE_BY_EXTENSION.get(extension)
        if language is not None:
            language_counts[language] = language_counts.get(language, 0) + 1

        if lowered_name in _MANIFEST_NAMES or lowered_name.startswith("requirements"):
            manifest_paths.append(path)
        if lowered_name in _LOCKFILE_NAMES:
            lock_paths.append(path)
        if _name_matches(relative, _DOCKER_NAMES) or _first_entry_matches(
            relative, (".devcontainer", ".devcontainers")
        ):
            docker_paths.append(path)
        if _first_entry_matches(relative, _CI_DIRS) or lowered_name in _CI_NAMES:
            ci_paths.append(path)
        if lowered_name.startswith("readme") and readme is None:
            readme = path
        if (
            lowered_name.startswith("license")
            or lowered_name.startswith("copying")
            or lowered_name == "unlicense"
        ) and license_file is None:
            license_file = path

    detected = [
        LanguageCount(language=name, file_count=count)
        for name, count in sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return Inventory(
        repository_id=case.candidate_id,
        repository_url=case.url,
        requested_commit=case.pinned_commit,
        verified_commit=verified_commit,
        content_hash=content_hash,
        acquired_at=acquired_at,
        ecosystem=case.ecosystem,
        detected_languages=detected,
        tracked_file_count=len(tracked_files),
        source_file_count=source_count,
        test_file_count=test_count,
        documentation_file_count=documentation_count,
        dependency_manifest=Presence(present=bool(manifest_paths), paths=manifest_paths),
        lockfile=Presence(present=bool(lock_paths), paths=lock_paths),
        ci=Presence(present=bool(ci_paths), paths=ci_paths),
        docker=Presence(present=bool(docker_paths), paths=docker_paths),
        readme=readme,
        license_file=license_file,
        top_level=top_level,
    )
