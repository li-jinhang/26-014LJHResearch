#!/usr/bin/env python3
"""Topic-level structure helpers for paired ljh research knowledge and paper roots."""

from __future__ import annotations

from pathlib import Path
import re

from ljh_research.knowledge.layout import KNOWLEDGE_DIR, PAPERS_DIR, research_root


RESERVED_TOPIC_NAMES = {"源文件库", "提取内容", "知识库", "概念库", "source-files", "README.md"}
KNOWLEDGE_LAYERS = ("知识库", "概念库")
PAPER_LAYERS = ("源文件库", "提取内容")
TOPIC_LAYERS = KNOWLEDGE_LAYERS + PAPER_LAYERS


def validate_topic_relative(topic_root_relative: str) -> Path:
    """Require 0知识库/<domain>/<topic>; reject reserved names and nesting."""
    path = Path(topic_root_relative)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit("--topic-root-relative must be a safe path under ljh research")
    if len(path.parts) != 3 or path.parts[0] != KNOWLEDGE_DIR:
        raise SystemExit(
            f"--topic-root-relative must be exactly {KNOWLEDGE_DIR}/<domain>/<topic>; "
            "do not nest a new topic under an existing topic"
        )
    domain, topic = path.parts[1], path.parts[2]
    if not domain or not topic:
        raise SystemExit("--topic-root-relative: domain and topic must not be empty")
    if topic in RESERVED_TOPIC_NAMES or domain in RESERVED_TOPIC_NAMES:
        raise SystemExit(f"--topic-root-relative: reserved layer name used: {topic}")
    return path


def topic_dir(project_root: Path, topic_relative: Path) -> Path:
    return research_root(project_root) / topic_relative


def paper_topic_relative(topic_relative: Path) -> Path:
    """Map 0知识库/<domain>/<topic> to its 1论文 peer."""
    return Path(PAPERS_DIR, *topic_relative.parts[1:])


def paper_topic_dir(project_root: Path, topic_relative: Path) -> Path:
    return research_root(project_root) / paper_topic_relative(topic_relative)


def detect_nested_topic(topic_path: Path) -> list[Path]:
    """Return child dirs under an existing topic that look like nested topics."""
    nested: list[Path] = []
    if not topic_path.is_dir():
        return nested
    for child in topic_path.iterdir():
        if not child.is_dir() or child.name in TOPIC_LAYERS:
            continue
        if any((child / layer).is_dir() for layer in TOPIC_LAYERS):
            nested.append(child)
    return nested


def ensure_topic_layers(project_root: Path, topic_relative: Path) -> Path:
    """Create paired 0知识库 and 1论文 topic layers; return the knowledge topic."""
    topic = topic_dir(project_root, topic_relative)
    topic.mkdir(parents=True, exist_ok=True)
    for layer in KNOWLEDGE_LAYERS:
        (topic / layer).mkdir(parents=True, exist_ok=True)
    paper_topic = paper_topic_dir(project_root, topic_relative)
    paper_topic.mkdir(parents=True, exist_ok=True)
    for layer in PAPER_LAYERS:
        (paper_topic / layer).mkdir(parents=True, exist_ok=True)
    return topic


def ensure_readme(path: Path, title: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")


def append_index_line(readme_path: Path, line: str) -> bool:
    """Append a wiki-index line idempotently; returns True when appended."""
    if not readme_path.exists():
        readme_path.parent.mkdir(parents=True, exist_ok=True)
        readme_path.write_text("", encoding="utf-8")
    text = readme_path.read_text(encoding="utf-8")
    if line.strip() in text:
        return False
    readme_path.write_text(text.rstrip() + "\n" + line.strip() + "\n", encoding="utf-8")
    return True


def default_paper_id(topic: Path, method: str) -> str:
    """Allocate the next stable paper ID; names and titles remain editable metadata."""

    knowledge_dir = topic / "知识库"
    max_num = 0
    if knowledge_dir.is_dir():
        for child in sorted(knowledge_dir.iterdir()):
            match = re.match(r"^PAPER-(\d{4,})(?:-|$)", child.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
    return f"PAPER-{max_num + 1:04d}"
