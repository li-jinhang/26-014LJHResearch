#!/usr/bin/env python3
"""Read or explicitly update project conventions in ``01约束文件.md``.

The command name remains for discoverability, but it no longer owns a second
JSON profile.  The constraints file is the only configuration source.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.project_conventions import DEFAULTS, constraints_path, load, parse_value, update


def resolve_project_root(project_root: Optional[str]) -> Path:
    return Path(project_root).expanduser().resolve() if project_root else Path.cwd().resolve()


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    parser.add_argument("--get", metavar="KEY", help="Read one convention field.")
    parser.add_argument("--set", metavar="KEY=VALUE", help="Explicitly update one convention field; values accept JSON.")
    parser.add_argument("--init", action="store_true", help="Validate the conventions created by workspace initialization.")
    args = parser.parse_args()
    project_root = resolve_project_root(args.project_root)

    if args.set:
        if "=" not in args.set:
            raise SystemExit("--set expects KEY=VALUE")
        key, _, raw = args.set.partition("=")
        key = key.strip()
        try:
            values = update(project_root, key, parse_value(raw.strip()))
        except ValueError as exc:
            raise SystemExit(f"invalid project conventions: {exc}") from exc
        print(f"set {key}={json.dumps(values[key], ensure_ascii=False)}")

    try:
        conventions = load(project_root)
    except ValueError as exc:
        raise SystemExit(f"invalid project conventions: {exc}") from exc
    if args.init:
        print(f"validated={constraints_path(project_root)}")
    if args.get:
        if args.get not in DEFAULTS:
            raise SystemExit(f"unknown convention key: {args.get}")
        print(f"{args.get}={json.dumps(conventions[args.get], ensure_ascii=False)}")
        return 0
    print(f"config={constraints_path(project_root)}")
    for key in DEFAULTS:
        print(f"{key}={json.dumps(conventions[key], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
