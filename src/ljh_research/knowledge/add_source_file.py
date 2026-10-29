#!/usr/bin/env python3
"""Copy a first-hand source into a topic-level source library and index it."""

from __future__ import annotations

import argparse
import shutil
from datetime import date
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import require_owned_workspace, resolve_project_root
from ljh_research.knowledge.layout import PAPERS_DIR, research_root
from ljh_research.knowledge.source_index import search_source_library, exact_matches
from ljh_research.knowledge.template_loader import load_template


def normalize_relative(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit("--library-relative must be a safe path under ljh research")
    if path.name not in {"源文件库", "source-files"}:
        raise SystemExit("--library-relative must point to a topic-level 源文件库")
    if path.parts[0] != PAPERS_DIR or len(path.parts) not in {2, 4}:
        raise SystemExit(f"--library-relative must be {PAPERS_DIR}/源文件库 (or an explicit legacy topic library)")
    return path


def ensure_readme(path: Path) -> None:
    if path.exists():
        return
    path.write_text(load_template("sources/source-library.md"), encoding="utf-8")


def append_index_entry(
    readme_path: Path,
    copied_name: str,
    title: str | None,
    original: str,
    note: str | None,
    original_url: str | None,
    entry_date: str,
) -> None:
    text = readme_path.read_text(encoding="utf-8")
    if copied_name in text:
        return
    lines = [
        f"- `{copied_name}`",
        f"  - 入库日期：{entry_date}",
        f"  - 题名：{title or '待补充'}",
        f"  - 原始外部路径/URL：`{original}`",
    ]
    if original_url:
        lines.append(f"  - 官方来源 URL：`{original_url}`")
    if note:
        lines.append(f"  - 关联笔记：{note}")
    readme_path.write_text(text.rstrip() + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description="Add a source file to a topic-level 源文件库.")
    parser.add_argument("--project-root", help="Project root path. Defaults to the current directory.")
    parser.add_argument("--source", required=True, help="Source file path, typically a paper PDF.")
    parser.add_argument("--title", help="Paper/source title for README provenance.")
    parser.add_argument("--name", help="Destination filename. Defaults to the source filename.")
    parser.add_argument("--library-relative", required=True, help="Domain/topic source library under ljh research.")
    parser.add_argument("--note", help="Optional related note link.")
    parser.add_argument("--original-url", help="Original official URL of the source for provenance.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Import date, YYYY-MM-DD.")
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    require_owned_workspace(project_root)
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Source file does not exist: {source}")
    library_relative = normalize_relative(args.library_relative)
    library_dir = research_root(project_root) / library_relative
    library_dir.mkdir(parents=True, exist_ok=True)
    dest_name = args.name or source.name
    if Path(dest_name).name != dest_name:
        raise SystemExit("--name must be a filename, not a path")

    papers_dir = research_root(project_root) / PAPERS_DIR
    matches = search_source_library(
        papers_dir, [args.title, source.name, str(source), dest_name]
    )
    exact = exact_matches(matches)
    if exact:
        print("exists=true")
        print("copied=false")
        for match in exact[:5]:
            print(f"match_readme={match.readme}")
            print(match.entry)
            print("---")
        return 0

    destination = library_dir / dest_name
    if destination.exists():
        raise SystemExit(f"Destination already exists but is not indexed: {destination}")
    shutil.copy2(source, destination)
    readme = library_dir / "README.md"
    ensure_readme(readme)
    append_index_entry(
        readme, destination.name, args.title, str(source), args.note, args.original_url, args.date
    )
    print(f"copied={destination}")
    print(f"source={source}")
    print(f"index={readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
