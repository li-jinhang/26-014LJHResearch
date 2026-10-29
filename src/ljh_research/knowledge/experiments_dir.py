#!/usr/bin/env python3
"""Resolve or explicitly set the declared experiment directory."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.profile_config import resolve_project_relative
from ljh_research.knowledge.project_conventions import constraints_path, load, update


def resolve_project_root(project_root: Optional[str]) -> Path:
    return Path(project_root).expanduser().resolve() if project_root else Path.cwd().resolve()


def resolve(project_root: Path) -> Path:
    try:
        value = load(project_root)["experiments_dir"]
        if value is None:
            raise ValueError("needs_configuration: experiments_dir")
        return resolve_project_relative(project_root, value, key="experiments_dir")
    except ValueError as exc:
        raise SystemExit(f"invalid project conventions: {exc}") from exc


def set_dir(project_root: Path, relative: str) -> Path:
    try:
        values = update(project_root, "experiments_dir", relative)
        resolved = resolve_project_relative(project_root, values["experiments_dir"], key="experiments_dir")
    except ValueError as exc:
        raise SystemExit(f"invalid experiments dir: {exc}") from exc
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    parser.add_argument("--set", metavar="RELATIVE_PATH", help="Persist one project-root-relative experiment directory.")
    args = parser.parse_args()
    project_root = resolve_project_root(args.project_root)
    resolved = set_dir(project_root, args.set) if args.set else resolve(project_root)
    print(f"experiments_dir={resolved}")
    print(f"config={constraints_path(project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
