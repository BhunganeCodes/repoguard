"""Architecture evidence extractor.

Reports mechanically observable structure: top-level layout, module
boundaries, source/test separation, configuration boundaries, architecture
documentation, and explicit visibility-boundary markers. It never labels the
architecture (no "clean", "layered", "spaghetti"), only the facts.
"""

from __future__ import annotations

from evaluation.evidence.extractors.base import (
    MAX_SOURCE_PATHS_PER_ITEM,
    ExtractionContext,
    count_label,
    dirname,
    is_top_level,
    make_item,
    norm,
    ordered,
)
from evaluation.evidence.models import EvidenceItem

NAME = "architecture"
VERSION = "1"

_CONFIG_DIR_NAMES = frozenset({".config", ".github", ".circleci", ".gitlab", "config"})
_TEST_DIR_HINTS = frozenset({"test", "tests", "spec", "__tests__", "e2e"})
_BOUNDARY_DIR_HINTS = frozenset({"cmd", "pkg", "internal", "src", "lib", "app"})
_VISIBILITY_BOUNDARY_DIRS = frozenset({"internal", "pkg"})


def _top_level_entries(ctx: ExtractionContext) -> tuple[dict[str, list[str]], list[str]]:
    """Return (dir -> representative files, top-level files).

    Representative file selection is deterministic: the first
    ``MAX_SOURCE_PATHS_PER_ITEM`` tracked files under each directory.
    """
    top_level_files: list[str] = []
    files_by_first_dir: dict[str, list[str]] = {}
    for rel in ctx.tracked_files:
        cleaned = norm(rel)
        if is_top_level(cleaned):
            top_level_files.append(cleaned)
        else:
            first = cleaned.split("/", 1)[0]
            files_by_first_dir.setdefault(first, []).append(cleaned)
    ordered_dirs: dict[str, list[str]] = {}
    for name in sorted(files_by_first_dir):
        ordered_dirs[name] = files_by_first_dir[name][:MAX_SOURCE_PATHS_PER_ITEM]
    return ordered_dirs, sorted(top_level_files)


def _test_files(ctx: ExtractionContext) -> list[str]:
    from evaluation.evidence.extractors.testing import is_test_file

    return ordered(f for f in ctx.tracked_files if is_test_file(f))


def extract(ctx: ExtractionContext) -> list[EvidenceItem]:
    items = []
    dirs, top_files = _top_level_entries(ctx)

    if ctx.tracked_files:
        sources = []
        for name in sorted(dirs):
            sources.extend(dirs[name][:1])
        sources.extend(top_files[:MAX_SOURCE_PATHS_PER_ITEM])
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="top_level_structure",
                status="FOUND",
                observation=(
                    f"Top-level structure: {len(dirs)} directories "
                    f"({', '.join(sorted(dirs)) or 'none'}) and "
                    f"{len(top_files)} files ({', '.join(top_files) or 'none'})."
                ),
                source_paths=sources,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="top_level_structure",
                status="NOT_FOUND",
                observation="No tracked files found in the snapshot checkout.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    boundary = [d for d in sorted(dirs) if d in _BOUNDARY_DIR_HINTS]
    if boundary:
        sources = [f for d in boundary for f in dirs[d][:1]]
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="module_boundaries",
                status="FOUND",
                observation=("Top-level module directories: " + ", ".join(boundary) + "."),
                source_paths=sources,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="module_boundaries",
                status="NOT_FOUND",
                observation=(
                    "No top-level module-named directories "
                    "(cmd, pkg, src, lib, app, internal) observed."
                ),
                source_paths=ordered(sorted(dirs))[:MAX_SOURCE_PATHS_PER_ITEM],
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    test_files = _test_files(ctx)
    if test_files:
        test_dirs = sorted({dirname(f) or "." for f in test_files})
        source_paths = test_files[:MAX_SOURCE_PATHS_PER_ITEM]
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="source_test_separation",
                status="FOUND",
                observation=(
                    f"{len(test_files)} test files observed in directories: "
                    + ", ".join(test_dirs)
                    + "."
                ),
                source_paths=source_paths,
                observed={"test_file_count": len(test_files)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="source_test_separation",
                status="NOT_FOUND",
                observation="No test files observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    config_dirs = [d for d in sorted(dirs) if d in _CONFIG_DIR_NAMES]
    config_files = [f for f in top_files if f.lower().startswith(".") and not f.endswith("/")]
    if config_dirs or config_files:
        sources = [f for d in config_dirs for f in dirs[d][:1]]
        sources += config_files[:MAX_SOURCE_PATHS_PER_ITEM]
        observed: dict[str, object] = {}
        if config_dirs:
            observed["config_directories"] = config_dirs
        if config_files:
            observed["config_files"] = len(config_files)
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="config_boundaries",
                status="FOUND",
                observation=(
                    "Configuration boundary observed: directories "
                    f"{', '.join(config_dirs) or 'none'} and "
                    f"{len(config_files)} top-level dot-files."
                ),
                source_paths=sources,
                observed=observed,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="config_boundaries",
                status="NOT_FOUND",
                observation="No dedicated configuration directory or top-level dotfiles observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    docs_suffix = (".md", ".rst", ".txt", ".adoc")
    arch_docs = []
    for f in ctx.tracked_files:
        lower = "/" + norm(f).lower()
        base = norm(f).rsplit("/", 1)[-1].lower()
        if not base.endswith(docs_suffix):
            continue
        if (
            "architecture" in lower
            or "/arch/" in lower
            or "/adr/" in lower
            or "/design" in lower
            or base.startswith(("arch", "adr", "design"))
        ):
            arch_docs.append(norm(f))
    if arch_docs:
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="architecture_docs",
                status="FOUND",
                observation=(
                    "Architecture-related documentation present "
                    f"({count_label(len(arch_docs), 'file', 'files')})."
                ),
                source_paths=arch_docs[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"architecture_doc_count": len(arch_docs)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="architecture_docs",
                status="NOT_FOUND",
                observation="No architecture or ADR documentation observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    vis = sorted(set(dirs) & _VISIBILITY_BOUNDARY_DIRS)
    if vis:
        sources = [f for d in vis for f in dirs[d][:1]]
        detail = []
        for d in vis:
            count = sum(1 for f in ctx.tracked_files if norm(f).split("/", 1)[0] == d)
            detail.append(f"{d} contains {count} tracked files")
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="dependency_direction_markers",
                status="FOUND",
                observation=(
                    "Explicit visibility-boundary directories observed: " + ", ".join(vis) + "."
                ),
                source_paths=sources,
                notes="; ".join(detail),
                observed={"visibility_directories": vis},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="architecture",
                evidence_type="dependency_direction_markers",
                status="NOT_FOUND",
                observation=(
                    "No explicit visibility-boundary directories (internal/, pkg/) observed."
                ),
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    return items
