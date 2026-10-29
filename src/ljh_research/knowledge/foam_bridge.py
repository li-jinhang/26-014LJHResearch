#!/usr/bin/env python3
"""Read-only Foam CLI bridge for ljh research structured memory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.foam_workspace import ensure_foam_workspace, validate_foam_workspace
from ljh_research.workspace_contract import require_owned_workspace, resolve_project_root
from ljh_research.knowledge.layout import research_root


def resolve_foam_bin(value: str | None) -> str | None:
    candidate = value or os.environ.get("FOAM_BIN") or "foam"
    path = Path(candidate)
    if path.is_file():
        return str(path)
    return shutil.which(candidate)


def run_foam(foam_bin: str | None, workspace: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    if foam_bin is None:
        raise SystemExit("Foam CLI not found. Install foam-cli or pass --foam-bin /path/to/foam.")
    return subprocess.run(
        [foam_bin, *arguments, "--workspace", str(workspace), "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def emit_result(result: subprocess.CompletedProcess[str]) -> int:
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.returncode


def command_status(workspace: Path, foam_bin: str | None) -> int:
    errors = validate_foam_workspace(workspace)
    payload = {
        "workspace": str(workspace),
        "foam_cli": foam_bin,
        "foam_cli_available": foam_bin is not None,
        "configured": not errors,
        "configuration_errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_health(workspace: Path, foam_bin: str | None) -> int:
    checks = {
        "lint": ["lint"],
        "placeholders": ["list", "placeholders"],
        "orphans": ["list", "orphans"],
    }
    payload: dict[str, object] = {"workspace": str(workspace), "checks": {}}
    exit_code = 0
    for name, command in checks.items():
        try:
            result = run_foam(foam_bin, workspace, command)
        except SystemExit as exc:
            payload["error"] = str(exc)
            exit_code = 1
            break
        payload["checks"][name] = {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
        exit_code = max(exit_code, result.returncode)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    parser.add_argument("--foam-bin", help="Foam executable. Defaults to FOAM_BIN or foam on PATH.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap", help="Create missing .foam templates and queries.")
    bootstrap.add_argument("--force", action="store_true", help="Overwrite Foam templates and queries.")
    subparsers.add_parser("status", help="Report Foam configuration and CLI availability.")
    subparsers.add_parser("lint", help="Run read-only foam lint with JSON output.")
    search = subparsers.add_parser("search", help="Search Foam notes by title, tag, or frontmatter.")
    search.add_argument("--query", default="", help="Title or alias substring.")
    search.add_argument("--tag", action="append", default=[], help="Repeat for AND tag filters.")
    search.add_argument("--property", action="append", default=[], help="Repeat key=value filters.")
    search.add_argument("--limit", type=int, default=20)
    links = subparsers.add_parser("links", help="Read outgoing links and backlinks for one note.")
    links.add_argument("--path", required=True, help="Workspace-relative Markdown path.")
    links.add_argument("--direction", choices=("both", "incoming", "outgoing"), default="both")
    subparsers.add_parser("health", help="Run lint, placeholder, and orphan checks as JSON.")
    return parser


def main() -> int:
    configure_utf8()
    args = build_parser().parse_args()
    project_root = resolve_project_root(args.project_root)
    workspace = require_owned_workspace(project_root)
    if args.command == "bootstrap":
        statuses = ensure_foam_workspace(workspace, force=args.force)
        for path, status in statuses.items():
            print(f"{status}: {path}")
        return 0

    foam_bin = resolve_foam_bin(args.foam_bin)
    if args.command == "status":
        return command_status(workspace, foam_bin)
    if args.command == "health":
        return command_health(workspace, foam_bin)
    if args.command == "lint":
        return emit_result(run_foam(foam_bin, workspace, ["lint"]))
    if args.command == "search":
        command = ["search"]
        if args.query:
            command.append(args.query)
        for tag in args.tag:
            command.extend(["--tag", tag])
        for property_filter in args.property:
            command.extend(["--property", property_filter])
        command.extend(["--limit", str(args.limit)])
        return emit_result(run_foam(foam_bin, workspace, command))
    command = ["links", "--path", args.path]
    if args.direction != "both":
        command.append(f"--{args.direction}")
    return emit_result(run_foam(foam_bin, workspace, command))


if __name__ == "__main__":
    raise SystemExit(main())
