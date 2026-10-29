"""Shared stable card identities, file names, and controlled status vocabularies."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


STATUSES = {
    "research_point": ("draft", "active", "validated", "rejected", "paused"),
    "experiment": ("planned", "running", "completed", "failed", "invalid"),
    "reproduction": ("planned", "setup", "running", "reproduced", "partial", "failed", "blocked"),
}


def ascii_slug(value: str, *, fallback: str) -> str:
    """Return a compact cross-platform slug; IDs remain the canonical reference."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return (slug or fallback).strip("-")[:60]


def next_identifier(directory: Path, prefix: str) -> str:
    numbers: list[int] = []
    if directory.is_dir():
        for path in directory.rglob(f"{prefix}-*.md"):
            match = re.match(rf"{re.escape(prefix)}-(\d+)(?:-|$)", path.name)
            if match:
                numbers.append(int(match.group(1)))
    return f"{prefix}-{max(numbers, default=0) + 1:04d}"


def card_filename(identifier: str, title_or_slug: str, *, fallback: str) -> str:
    return f"{identifier}-{ascii_slug(title_or_slug, fallback=fallback)}.md"
