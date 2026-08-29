"""Shared helpers for evidence extractors.

Helpers here are strictly mechanical: pattern matching, bounded file reads,
and stable ordering. They never judge, score, or classify quality.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evaluation.evidence.models import EvidenceItem

# Bounded, deterministic sampling limits. Inputs are sorted before sampling so
# the same checkout always yields the same sample.
MAX_SOURCE_PATHS_PER_ITEM = 25
MAX_SAMPLE_FILES = 300
MAX_LINES_PER_FILE = 2000
MAX_HEADER_LINES = 24

# Fallback character produced by the decoder; a high ratio marks binary files.
_REPLACEMENT_CHAR = "\ufffd"

# File extensions assumed to hold readable text (documentation, configs,
# manifests, and representative source files).
_TEXT_EXTENSIONS = frozenset(
    {
        ".md",
        ".rst",
        ".txt",
        ".adoc",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".ini",
        ".cfg",
        ".conf",
        ".py",
        ".go",
        ".rs",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".java",
        ".kt",
        ".kts",
        ".rb",
        ".php",
        ".sh",
        ".bat",
        ".ps1",
        ".sql",
        ".scss",
        ".css",
        ".html",
        ".xml",
        ".proto",
        ".gradle",
        ".tf",
        ".lua",
        ".swift",
        ".fs",
        ".ex",
        ".exs",
        ".clj",
        ".scala",
        ".cs",
        ".vue",
        ".svelte",
        ".dart",
        ".zig",
        ".prisma",
        ".http",
    }
)

# Basenames that are unambiguous text regardless of extension.
_TEXT_BASENAMES = frozenset(
    {
        "Makefile",
        "GNUmakefile",
        "Dockerfile",
        "Jenkinsfile",
        "LICENSE",
        "LICENCE",
        "NOTICE",
        "CHANGELOG",
        "README",
        "CONTRIBUTING",
    }
)


def norm(path: str) -> str:
    """Normalize a repository-relative path to POSIX form (never absolute)."""
    cleaned = path.replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def is_text_file(name: str) -> bool:
    lowered = name.lower()
    if Path(lowered).suffix in _TEXT_EXTENSIONS:
        return True
    return Path(name).name in _TEXT_BASENAMES or name.endswith(("Makefile", "Dockerfile"))


def ordered(paths: Iterable[str]) -> list[str]:
    return sorted({norm(p) for p in paths})


def count_label(count: int, singular: str, plural: str) -> str:
    """Render ``N <singular|plural>`` with basic plural agreement."""
    return f"{count} {singular if count == 1 else plural}"


def dirname(path: str) -> str:
    parts = norm(path).split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else ""


def is_top_level(path: str) -> bool:
    return dirname(path) == ""


def read_lines(checkout: Path, rel: str, *, limit: int = MAX_LINES_PER_FILE) -> list[str]:
    """Read up to ``limit`` decoded lines of a tracked text file.

    Missing or binary-looking content returns an empty list. Decoding is
    deterministic (UTF-8, replacement on bad bytes).
    """
    target = checkout / rel
    try:
        raw = target.read_bytes()
    except OSError:
        return []
    if len(raw) == 0:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if text.count(_REPLACEMENT_CHAR) / max(len(text), 1) > 0.02:
        return []
    return text.splitlines()[:limit]


def first_lines(checkout: Path, rel: str, *, limit: int = MAX_HEADER_LINES) -> list[str]:
    return read_lines(checkout, rel, limit=limit)


def count_matches(lines: Iterable[str], pattern: str) -> int:
    return sum(1 for line in lines if re.search(pattern, line))


@dataclass(slots=True)
class ExtractionContext:
    """Inputs shared by every extractor."""

    checkout: Path
    tracked_files: list[str]
    case_id: str
    name: str
    repository_url: str
    requested_commit: str
    verified_commit: str
    snapshot_content_hash: str
    top_level_dirs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tracked_files = ordered(self.tracked_files)
        dirs: set[str] = set()
        for rel in self.tracked_files:
            cleaned = norm(rel)
            if "/" in cleaned:
                dirs.add(cleaned.split("/", 1)[0])
        self.top_level_dirs = sorted(dirs)


def text_files_of_interest(files: Sequence[str], *, limit: int = MAX_SAMPLE_FILES) -> list[str]:
    """Bounded, deterministic sample of readable tracked files."""
    candidates = ordered(f for f in files if is_text_file(f))
    return candidates[:limit]


def make_item(
    ctx: ExtractionContext,
    *,
    category: str,
    evidence_type: str,
    status: str,
    observation: str,
    source_paths: Sequence[str] | None = None,
    notes: str | None = None,
    observed: dict[str, Any] | None = None,
    extractor: str,
    extractor_version: str,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"{category}.{evidence_type}",
        case_id=ctx.case_id,
        category=category,
        evidence_type=evidence_type,
        status=status,
        observation=observation,
        source_paths=list(ordered(source_paths)) if source_paths else [],
        extractor=extractor,
        extractor_version=extractor_version,
        notes=notes,
        observed=dict(observed) if observed else None,
    )
