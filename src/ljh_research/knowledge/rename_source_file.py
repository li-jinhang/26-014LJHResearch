#!/usr/bin/env python3
"""Rename a topic-level imported source and update local markdown references."""

from __future__ import annotations

import argparse
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.add_source_file import normalize_relative
from ljh_research.workspace_contract import require_owned_workspace, resolve_project_root
from ljh_research.knowledge.layout import research_root


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description="Rename an imported source file safely.")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    parser.add_argument("--library-relative", required=True, help="Topic source library under ljh research.")
    parser.add_argument("--current-name", required=True, help="Current imported filename.")
    parser.add_argument("--new-name", required=True, help="New filename, including extension.")
    args = parser.parse_args()

    if Path(args.current_name).name != args.current_name or Path(args.new_name).name != args.new_name:
        raise SystemExit("--current-name and --new-name must be filenames")
    project_root = resolve_project_root(args.project_root)
    require_owned_workspace(project_root)
    library = research_root(project_root) / normalize_relative(args.library_relative)
    current = library / args.current_name
    new = library / args.new_name
    if not current.is_file():
        raise SystemExit(f"Imported source does not exist: {current}")
    if new.exists():
        raise SystemExit(f"Destination already exists: {new}")
    current.rename(new)
    replacements = 0
    for note in research_root(project_root).rglob("*.md"):
        text = note.read_text(encoding="utf-8")
        if args.current_name in text:
            note.write_text(text.replace(args.current_name, args.new_name), encoding="utf-8")
            replacements += 1
    print(f"renamed={new}")
    print(f"references_updated={replacements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
