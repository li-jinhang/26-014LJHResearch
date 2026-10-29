#!/usr/bin/env python3
"""Shared helpers for searching topic-level source-file indexes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


SOURCE_LIBRARY_NAMES = {"源文件库", "source-files"}


@dataclass(frozen=True)
class SourceMatch:
    readme: Path
    entry: str
    score: int
    match_type: str = "candidate"  # "exact" | "candidate"


def iter_source_readmes(knowledge_base_dir: Path):
    if not knowledge_base_dir.exists():
        return
    for readme in knowledge_base_dir.rglob("README.md"):
        if readme.parent.name in SOURCE_LIBRARY_NAMES:
            yield readme


def iter_source_entries(text: str):
    for paragraph in re.split(r"\n\s*\n", text):
        entry = paragraph.strip()
        if entry.startswith("- `"):
            yield entry


def normalized_text(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())


def normalize_query_terms(queries: list[str | None]) -> list[str]:
    terms: list[str] = []
    for query in queries:
        if not query:
            continue
        normalized = query.strip().lower()
        if not normalized:
            continue
        terms.append(normalized)
        terms.extend(token for token in re.split(r"\s+", normalized) if len(token) >= 3)
    return list(dict.fromkeys(terms))


def parse_entry(entry: str) -> tuple[str | None, str | None]:
    """Return (filename, title) parsed from a source-index entry."""
    filename: str | None = None
    title: str | None = None
    for line in entry.splitlines():
        line = line.strip()
        match = re.match(r"^-\s*`([^`]+)`", line)
        if match and filename is None:
            filename = match.group(1).strip()
        match = re.match(r"^-\s*题名[：:]\s*(.+)$", line)
        if match and title is None:
            title = match.group(1).strip()
    return filename, title


def is_exact_match(query: str, filename: str | None, title: str | None) -> bool:
    """Exact duplicate only when the normalized query equals or contains the
    normalized filename/title (or vice versa) at a meaningful length."""
    query_norm = normalized_text(query)
    if not query_norm:
        return False
    for candidate in (filename, title):
        if not candidate:
            continue
        candidate_norm = normalized_text(candidate)
        if not candidate_norm:
            continue
        if query_norm == candidate_norm:
            return True
        if len(query_norm) >= 15 and query_norm in candidate_norm:
            return True
        if len(candidate_norm) >= 15 and candidate_norm in query_norm:
            return True
    return False


def search_source_library(knowledge_base_dir: Path, queries: list[str | None]) -> list[SourceMatch]:
    all_terms = normalize_query_terms(queries)
    if not all_terms:
        return []
    matches: list[SourceMatch] = []
    for readme in iter_source_readmes(knowledge_base_dir):
        try:
            text = readme.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for entry in iter_source_entries(text):
            haystack = entry.lower()
            filename, title = parse_entry(entry)
            exact = any(is_exact_match(query, filename, title) for query in queries if query)
            score = sum(1 for term in all_terms if term in haystack)
            if exact or score:
                matches.append(
                    SourceMatch(
                        readme=readme,
                        entry=entry,
                        score=score,
                        match_type="exact" if exact else "candidate",
                    )
                )
    return sorted(
        matches,
        key=lambda match: (match.match_type != "exact", -match.score, str(match.readme), match.entry),
    )


def exact_matches(matches: list[SourceMatch]) -> list[SourceMatch]:
    return [match for match in matches if match.match_type == "exact"]
