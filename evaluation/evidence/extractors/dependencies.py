"""Dependencies evidence extractor.

Reports mechanically observable dependency facts: declared dependency
manifests, lockfiles, parsed direct dependency declarations (with bounding),
dev/test dependency groups, version-specifier shapes, workspace/monorepo
markers, and vendored dependency directories. Parsing is defensive: an
unparseable manifest yields UNCERTAIN, never a fabricated declaration list.
"""

from __future__ import annotations

import json
import re
import tomllib

from evaluation.evidence.extractors.base import (
    MAX_SOURCE_PATHS_PER_ITEM,
    ExtractionContext,
    count_label,
    make_item,
    norm,
    ordered,
)
from evaluation.evidence.models import EvidenceItem

NAME = "dependencies"
VERSION = "1"

_MANIFEST_BASENAMES = frozenset(
    {
        "go.mod",
        "go.work",
        "Cargo.toml",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "composer.json",
        "Gemfile",
        "gems.rb",
        "mix.exs",
        "pubspec.yaml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    }
)

_LOCKFILE_BASENAMES = frozenset(
    {
        "go.sum",
        "Cargo.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lock",
        "bun.lockb",
        "poetry.lock",
        "uv.lock",
        "Pipfile.lock",
        "composer.lock",
        "Gemfile.lock",
        "gems.locked",
        "mix.lock",
        "pubspec.lock",
        "gradle.lockfile",
    }
)

_MANIFEST_PRIORITY = (
    "go.mod",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "requirements.txt",
    "composer.json",
    "Gemfile",
    "gems.rb",
    "mix.exs",
    "pubspec.yaml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
)

_WORKSPACE_FILENAMES = frozenset(
    {"go.work", "pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", "uv.lock"}
)

_VENDOR_DIR_NAMES = frozenset(
    {"vendor", "third_party", "3rdparty", "node_modules", "vendor_modules"}
)

# Mapping of exact manifest basename to recognized dependency manager names.
_MANAGER_BY_BASENAME = {
    "go.mod": "Go Modules",
    "go.work": "Go workspace",
    "Cargo.toml": "Cargo",
    "package.json": "npm",
    "pyproject.toml": "PEP 621",
    "requirements.txt": "pip",
    "composer.json": "Composer",
    "Gemfile": "Bundler",
    "gems.rb": "Bundler",
    "mix.exs": "Mix",
    "pubspec.yaml": "Pub",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
}


def _read_text(ctx: ExtractionContext, rel: str, *, max_bytes: int = 65536) -> str | None:
    target = ctx.checkout / rel
    try:
        raw = target.read_bytes()[:max_bytes]
    except OSError:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _find_manifests(ctx: ExtractionContext) -> list[str]:
    matches: list[str] = []
    for f in ctx.tracked_files:
        cleaned = norm(f)
        base = cleaned.rsplit("/", 1)[-1]
        if base in _MANIFEST_BASENAMES:
            matches.append(cleaned)
    return ordered(matches)


def _primary_manifest(manifests: list[str]) -> str | None:
    for template in _MANIFEST_PRIORITY:
        for candidate in manifests:
            if candidate.rsplit("/", 1)[-1] == template:
                return candidate
    return None


def _manager_of(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    return _MANAGER_BY_BASENAME.get(base, "unknown")


def _parse_go_mod(text: str) -> tuple[list[tuple[str, str]], str | None]:
    deps: list[tuple[str, str]] = []
    error: str | None = None
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("//"):
            continue
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block:
            if line.startswith(")"):
                in_block = False
                continue
            parts = line.split()
            if len(parts) >= 3 and parts[0] != "module":
                deps.append((parts[0].split("//")[0].strip(), parts[1].split("//")[0].strip()))
            elif len(parts) >= 2:
                deps.append((parts[0].split("//")[0].strip(), parts[1].split("//")[0].strip()))
            continue
        if line.startswith("require ") and not line.startswith("require ("):
            parts = line.split()
            if len(parts) >= 3:
                deps.append((parts[1].split("//")[0].strip(), parts[2].split("//")[0].strip()))
    return deps, error


def _parse_json_deps(text: str) -> tuple[list[tuple[str, str]], dict[str, object], str | None]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return [], {}, "JSON parse failed"
    if not isinstance(data, dict):
        return [], {}, "manifest root is not an object"
    deps_text = data.get("dependencies")
    dev_deps = data.get("devDependencies")
    workspaces: object = data.get("workspaces")
    deps: list[tuple[str, str]] = []
    if isinstance(deps_text, dict):
        for name, ver in deps_text.items():
            deps.append((str(name), "" if ver is None else str(ver)))
    extra: dict[str, object] = {}
    if isinstance(dev_deps, dict):
        extra["dev_dependency_count"] = len(dev_deps)
    if workspaces is not None:
        extra["has_workspaces"] = True
    return deps, extra, None


def _parse_toml_deps(
    text: str, *, is_pyproject: bool
) -> tuple[list[tuple[str, str]], dict[str, object], str | None]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], {}, f"TOML parse failed: {exc}"
    deps: list[tuple[str, str]] = []
    extra: dict[str, object] = {}
    if is_pyproject:
        project = data.get("project")
        if isinstance(project, dict):
            raw = project.get("dependencies")
            if isinstance(raw, list):
                for entry in raw:
                    if isinstance(entry, str):
                        name, ver = _split_pep508(entry)
                        deps.append((name, ver))
            optional = project.get("optional-dependencies") or {}
            if isinstance(optional, dict):
                extra["optional_group_count"] = len(optional)
                extra["dev_dependency_count"] = sum(
                    len(v) for v in optional.values() if isinstance(v, list)
                )
        poetry = data.get("tool", {}).get("poetry", {}).get("dependencies")
        if isinstance(poetry, dict):
            for name, spec in poetry.items():
                if isinstance(spec, dict):
                    deps.append((str(name), str(spec.get("version", ""))))
                elif isinstance(spec, str):
                    deps.append((str(name), spec))
    else:
        raw = data.get("dependencies")
        if isinstance(raw, dict):
            for name, spec in raw.items():
                if isinstance(spec, dict):
                    deps.append((str(name), str(spec.get("version", ""))))
                elif isinstance(spec, (str, int, float, bool)):
                    deps.append((str(name), "" if spec is True else str(spec)))
        dev_raw = data.get("dev-dependencies")
        if isinstance(dev_raw, dict):
            extra["dev_dependency_count"] = len(dev_raw)
    return deps, extra, None


def _split_pep508(entry: str) -> tuple[str, str]:
    entry = entry.strip()
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", entry)
    if not match:
        return (entry, "")
    return (match.group(1), match.group(2).strip())


def _parse_requirements(text: str) -> tuple[list[tuple[str, str]], str | None]:
    deps: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", "--")):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*(==|>=|<=|~=|!=|=|<|>)?\s*(.*)$", line)
        if match:
            deps.append((match.group(1), (match.group(2) or "") + (match.group(3) or "")))
    return deps, None


def _parse_primary(
    manifest: str, ctx: ExtractionContext
) -> tuple[list[tuple[str, str]] | None, dict[str, object], str | None]:
    base = manifest.rsplit("/", 1)[-1]
    text = _read_text(ctx, manifest)
    if text is None:
        return None, {}, "manifest unreadable"
    if base == "go.mod":
        deps, error = _parse_go_mod(text)
        return deps or None, {}, error
    if base == "package.json":
        deps, extra, error = _parse_json_deps(text)
        return deps or None, extra, error
    if base == "pyproject.toml":
        deps, extra, error = _parse_toml_deps(text, is_pyproject=True)
        return deps or None, extra, error
    if base == "Cargo.toml":
        deps, extra, error = _parse_toml_deps(text, is_pyproject=False)
        return deps or None, extra, error
    if base == "requirements.txt":
        deps, error = _parse_requirements(text)
        return deps or None, {}, error
    if base in ("pom.xml", "build.gradle", "build.gradle.kts"):
        return None, {}, "declaration parsing not implemented for this manifest type"
    return None, {}, "declaration parsing not implemented for this manifest type"


def _pin_kind(version: str) -> str:
    version = version.strip()
    if not version or version in {"*", "latest", "workspace", "workspace:"}:
        return "unversioned"
    if version.startswith(("==", "=")):
        return "exact"
    if version.startswith((">=", "<=", "~=", "!=", "<", ">", "~", "^", "!=")):
        return "range"
    return "exact"


def _pin_counts(deps: list[tuple[str, str]]) -> dict[str, int]:
    counts = {"exact": 0, "range": 0, "unversioned": 0}
    for _name, version in deps:
        counts[_pin_kind(version)] += 1
    return counts


def extract(ctx: ExtractionContext) -> list[EvidenceItem]:
    items = []
    manifests = _find_manifests(ctx)

    if manifests:
        with_manager = [f"{m} ({_manager_of(m)})" for m in manifests[:MAX_SOURCE_PATHS_PER_ITEM]]
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="dependency_manifests",
                status="FOUND",
                observation=(
                    f"{count_label(len(manifests), 'dependency manifest', 'dependency manifests')} "
                    f"observed: " + ", ".join(with_manager) + "."
                ),
                source_paths=manifests[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"manifest_count": len(manifests)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="dependency_manifests",
                status="NOT_FOUND",
                observation="No dependency manifest observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    lockfiles = [
        f
        for f in ctx.tracked_files
        if f.rsplit("/", 1)[-1] in _LOCKFILE_BASENAMES
        or f.rsplit("/", 1)[-1].startswith("requirements")
        and f.rsplit("/", 1)[-1].endswith(".lock")
    ]
    if lockfiles:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="lockfiles",
                status="FOUND",
                observation=(
                    f"{count_label(len(lockfiles), 'lockfile', 'lockfiles')} observed: "
                    + ", ".join(lockfiles)
                    + "."
                ),
                source_paths=lockfiles[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"lockfile_count": len(lockfiles)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="lockfiles",
                status="NOT_FOUND",
                observation="No lockfiles observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    primary = _primary_manifest(manifests)
    if primary is None:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="dependency_declarations",
                status="NOT_FOUND",
                observation="No parseable primary dependency manifest observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        deps, extra, error = _parse_primary(primary, ctx)
        if error is not None:
            items.append(
                make_item(
                    ctx,
                    category="dependencies",
                    evidence_type="dependency_declarations",
                    status="UNCERTAIN",
                    observation=(
                        f"Primary manifest {primary} present but could not be parsed "
                        f"({error}); declaration list not produced."
                    ),
                    source_paths=[primary],
                    extractor=NAME,
                    extractor_version=VERSION,
                )
            )
        elif deps is None:
            items.append(
                make_item(
                    ctx,
                    category="dependencies",
                    evidence_type="dependency_declarations",
                    status="UNCERTAIN",
                    observation=(
                        f"Primary manifest {primary} present but declaration parsing "
                        f"is not supported for this manifest type."
                    ),
                    source_paths=[primary],
                    extractor=NAME,
                    extractor_version=VERSION,
                )
            )
        else:
            sample = ", ".join(name for name, _ in deps[:20])
            items.append(
                make_item(
                    ctx,
                    category="dependencies",
                    evidence_type="dependency_declarations",
                    status="FOUND",
                    observation=(
                        f"{count_label(len(deps), 'direct dependency', 'direct dependencies')} "
                        f"declared in {primary}: "
                        f"{sample}" + (" ..." if len(deps) > 20 else "") + "."
                    ),
                    source_paths=[primary],
                    observed={"direct_dependency_count": len(deps), **extra},
                    extractor=NAME,
                    extractor_version=VERSION,
                )
            )

    dev_deps = _dev_dependency_paths(ctx, manifests)
    if dev_deps:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="dev_test_dependencies",
                status="FOUND",
                observation=(
                    "Dev/test dependency declarations observed in: " + ", ".join(dev_deps) + "."
                ),
                source_paths=dev_deps,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="dev_test_dependencies",
                status="NOT_FOUND",
                observation="No dev/test dependency declarations observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    if primary is not None and deps is not None and error is None:
        counts = _pin_counts(deps)
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="version_pinning",
                status="FOUND",
                observation=(
                    f"Of {len(deps)} direct dependencies in {primary}: "
                    f"{counts['exact']} exact, {counts['range']} range, "
                    f"{counts['unversioned']} unversioned."
                ),
                source_paths=[primary],
                observed=counts,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="version_pinning",
                status="NOT_FOUND",
                observation=(
                    "No version pinning analysis possible (no parseable primary manifest)."
                ),
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    workspace = _workspace_markers(ctx)
    if workspace:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="workspace_monorepo",
                status="FOUND",
                observation="Workspace/monorepo markers observed: " + ", ".join(workspace) + ".",
                source_paths=workspace[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"workspace_marker_count": len(workspace)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="workspace_monorepo",
                status="NOT_FOUND",
                observation="No workspace/monorepo markers observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    vendored = _vendored_paths(ctx)
    if vendored:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="vendored_dependencies",
                status="FOUND",
                observation=(
                    "Vendored dependency content observed under: "
                    + ", ".join(sorted(set(vendored)))
                    + "."
                ),
                source_paths=vendored[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"vendored_file_count": len(vendored)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="dependencies",
                evidence_type="vendored_dependencies",
                status="NOT_FOUND",
                observation="No vendored dependency directories observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    return items


def _dev_dependency_paths(ctx: ExtractionContext, manifests: list[str]) -> list[str]:
    known = {
        "requirements-dev.txt",
        "requirements_dev.txt",
        "dev-requirements.txt",
        "dev_requirements.txt",
    }
    matches = [m for m in manifests if m.rsplit("/", 1)[-1] in known]
    for m in manifests:
        base = m.rsplit("/", 1)[-1]
        text = _read_text(ctx, m)
        if text is None:
            continue
        if base == "package.json":
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(data, dict) and isinstance(data.get("devDependencies"), dict):
                matches.append(m)
        elif base == "Cargo.toml":
            try:
                data = tomllib.loads(text)
            except (tomllib.TOMLDecodeError, ValueError):
                continue
            if isinstance(data.get("dev-dependencies"), dict):
                matches.append(m)
        elif base == "pyproject.toml":
            lower = text.lower()
            if (
                "[tool.poetry.dev-dependencies]" in lower
                or "[tool.poetry.group.dev" in lower
                or "[project.optional-dependencies]" in lower
                or "[dependency-groups]" in lower
            ):
                matches.append(m)
    return ordered(matches)


def _workspace_markers(ctx: ExtractionContext) -> list[str]:
    matches = []
    for f in ctx.tracked_files:
        base = norm(f).rsplit("/", 1)[-1]
        if base in _WORKSPACE_FILENAMES:
            matches.append(norm(f))
        if base == "go.work":
            matches.append(norm(f))
        if base == "package.json":
            text = _read_text(ctx, norm(f))
            if text and '"workspaces"' in text:
                matches.append(norm(f))
    for d in ctx.top_level_dirs:
        if d == "packages":
            matches.append(d)
    return ordered(matches)


def _vendored_paths(ctx: ExtractionContext) -> list[str]:
    matches = []
    for f in ctx.tracked_files:
        parts = norm(f).split("/")
        if parts and parts[0] in _VENDOR_DIR_NAMES:
            matches.append(norm(f))
        if len(parts) > 1 and parts[0] == "vendor" and parts[1] == "modules.txt":
            matches.append(norm(f))
    return ordered(matches)


__all__ = ["NAME", "VERSION", "extract"]
