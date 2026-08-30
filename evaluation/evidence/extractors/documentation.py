"""Documentation evidence extractor.

Reports presence and location of documentation artifacts: README files,
documentation directories, API documentation generators, contribution
guides, architecture/design docs, changelog/release notes, and
examples/tutorials. Findings are presence facts tied to concrete paths.
"""

from __future__ import annotations

from evaluation.evidence.extractors.base import (
    MAX_SOURCE_PATHS_PER_ITEM,
    ExtractionContext,
    count_label,
    make_item,
    norm,
    ordered,
    read_lines,
)
from evaluation.evidence.models import EvidenceItem

NAME = "documentation"
VERSION = "1"

_README_NAMES = frozenset({"readme.md", "readme.rst", "readme.txt", "readme.adoc", "readme"})
_DOC_DIR_HINTS = {"docs", "doc", "documentation", "wiki"}
_API_DOC_CONFIG_NAMES = frozenset(
    {
        "mkdocs.yml",
        "mkdocs.yaml",
        "sphinx.conf.py",
        "conf.py",
        "docusaurus.config.js",
        "docusaurus.config.ts",
        "vuepress.config.ts",
        "vitepress.config.ts",
        "swagger.json",
        "swagger.yaml",
        "openapi.json",
        "openapi.yaml",
        "openapi.yml",
        "redocly.yaml",
        "api-docs.json",
        "package.json",
    }
)
_CHANGELOG_NAMES = frozenset({"changelog.md", "changes.md", "news.md", "release-notes.md"})
_EXAMPLE_DIR_HINTS = {"examples", "example", "samples", "sample", "tutorials"}


def _basename_lower(path: str) -> str:
    return norm(path).rsplit("/", 1)[-1].lower()


def extract(ctx: ExtractionContext) -> list[EvidenceItem]:
    items = []

    readmes = []
    for f in ctx.tracked_files:
        base = _basename_lower(f)
        if base in _README_NAMES or base.startswith("readme."):
            readmes.append(norm(f))
    readmes = ordered(readmes)
    if readmes:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="readme",
                status="FOUND",
                observation=(
                    f"{count_label(len(readmes), 'README file', 'README files')} observed: "
                    + ", ".join(readmes)
                    + "."
                ),
                source_paths=readmes[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"readme_count": len(readmes)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="readme",
                status="NOT_FOUND",
                observation="No README file observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    doc_dirs = [d for d in ctx.top_level_dirs if d in _DOC_DIR_HINTS]
    nested_doc_dirs = set()
    for d in doc_dirs:
        nested_doc_dirs.add(d)
    if doc_dirs:
        sources = [f for f in ctx.tracked_files if norm(f).split("/", 1)[0] in doc_dirs]
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="documentation_directories",
                status="FOUND",
                observation="Documentation directories observed: " + ", ".join(doc_dirs) + ".",
                source_paths=sources[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"documentation_directories": sorted(nested_doc_dirs)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="documentation_directories",
                status="NOT_FOUND",
                observation="No documentation directories observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    api = _api_docs_config(ctx)
    if api:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="api_docs_config",
                status="FOUND",
                observation=(
                    "API documentation configuration observed in: " + ", ".join(api) + "."
                ),
                source_paths=api,
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="api_docs_config",
                status="NOT_FOUND",
                observation="No API documentation configuration observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    guides = _contribution_guides(ctx)
    if guides:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="contribution_guides",
                status="FOUND",
                observation="Contribution guides observed: " + ", ".join(guides) + ".",
                source_paths=guides[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"contribution_guide_count": len(guides)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="contribution_guides",
                status="NOT_FOUND",
                observation="No contribution guides observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    arch = _architecture_docs(ctx)
    if arch:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="architecture_docs",
                status="FOUND",
                observation="Architecture/design documentation observed: " + ", ".join(arch) + ".",
                source_paths=arch[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"architecture_doc_count": len(arch)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="architecture_docs",
                status="NOT_FOUND",
                observation="No architecture/design documentation observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    changelog = _changelog_paths(ctx)
    if changelog:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="changelog_release_notes",
                status="FOUND",
                observation=(
                    "Changelog/release documentation observed: " + ", ".join(changelog) + "."
                ),
                source_paths=changelog[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"changelog_count": len(changelog)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="changelog_release_notes",
                status="NOT_FOUND",
                observation="No changelog or release notes observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    examples = _example_paths(ctx)
    if examples:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="examples_tutorials",
                status="FOUND",
                observation="Examples/tutorials observed: " + ", ".join(examples) + ".",
                source_paths=examples[:MAX_SOURCE_PATHS_PER_ITEM],
                observed={"example_asset_count": len(examples)},
                extractor=NAME,
                extractor_version=VERSION,
            )
        )
    else:
        items.append(
            make_item(
                ctx,
                category="documentation",
                evidence_type="examples_tutorials",
                status="NOT_FOUND",
                observation="No examples or tutorials observed.",
                extractor=NAME,
                extractor_version=VERSION,
            )
        )

    return items


def _api_docs_config(ctx: ExtractionContext) -> list[str]:
    matches: list[str] = []
    for f in ctx.tracked_files:
        cleaned = norm(f)
        base = _basename_lower(f)
        if base in _API_DOC_CONFIG_NAMES:
            in_doc_dir = "docs/" in cleaned.lower() or "doc/" in cleaned.lower()
            if base == "conf.py" and not in_doc_dir:
                continue
            matches.append(cleaned)
            continue
        lower = cleaned.lower()
        if any(name in lower for name in ("swagger", "openapi")):
            matches.append(cleaned)
    full_text_config_files = (
        f for f in ctx.tracked_files if _basename_lower(f) in {"pyproject.toml", "package.json"}
    )
    sphinx_docs = ("mkdocs", "sphinx", "docusaurus", "typedoc", "pdoc", "swagger", "openapi")
    for f in full_text_config_files:
        cleaned = norm(f)
        text = "\n".join(read_lines(ctx.checkout, cleaned, limit=200)).lower()
        if any(m in text for m in sphinx_docs):
            matches.append(cleaned)
    return ordered(matches)


def _contribution_guides(ctx: ExtractionContext) -> list[str]:
    matches = []
    for f in ctx.tracked_files:
        cleaned = norm(f)
        base = _basename_lower(f)
        lower = cleaned.lower()
        if base.startswith("contributing") or base.startswith("contributor"):
            matches.append(cleaned)
        elif "contribution" in lower and lower.endswith((".md", ".rst", ".txt", ".adoc")):
            matches.append(cleaned)
    return ordered(matches)


def _architecture_docs(ctx: ExtractionContext) -> list[str]:
    matches = []
    suffix = (".md", ".rst", ".txt", ".adoc")
    for f in ctx.tracked_files:
        cleaned = norm(f)
        base = _basename_lower(f)
        if not base.endswith(suffix):
            continue
        lower = "/" + cleaned.lower()
        if (
            "architecture" in lower
            or "/adr/" in lower
            or base.startswith("adr")
            or "/design" in lower
        ):
            matches.append(cleaned)
    return ordered(matches)


def _changelog_paths(ctx: ExtractionContext) -> list[str]:
    matches = []
    suffix = (".md", ".rst", ".txt", ".adoc")
    for f in ctx.tracked_files:
        cleaned = norm(f)
        base = _basename_lower(f)
        lower = cleaned.lower()
        if base in _CHANGELOG_NAMES:
            matches.append(cleaned)
        elif (
            base.startswith("changelog")
            or base.startswith("release-notes")
            or base.startswith("news")
        ):
            if base.endswith(suffix) or base in {"news", "changes"}:
                matches.append(cleaned)
        elif "/changes/" in lower or "/release-notes/" in lower:
            matches.append(cleaned)
        elif base == ".changeset":
            matches.append(cleaned)
    return ordered(matches)


def _example_paths(ctx: ExtractionContext) -> list[str]:
    matches = []
    for f in ctx.tracked_files:
        parts = [p.lower() for p in norm(f).split("/")]
        if parts and parts[0] in _EXAMPLE_DIR_HINTS:
            matches.append(norm(f))
    return ordered(matches)
