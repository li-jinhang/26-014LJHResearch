#!/usr/bin/env python3
"""Protect existing non-research project files during autonomous research work.

The guard snapshots every regular file below a project root except ``ljh research docs``.
It intentionally never restores files: a failed verification is evidence that the
caller must stop, not permission to overwrite a user's work during rollback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from ljh_research.workspace_contract import resolve_project_root
from ljh_research.knowledge.layout import RESEARCH_DIR


RESEARCH_DIR_NAME = RESEARCH_DIR
IGNORED_DIR_NAMES = {".git", "__pycache__"}


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_protected_files(root: Path):
    research_root = root / RESEARCH_DIR_NAME
    for current, directories, filenames in os.walk(root):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if name not in IGNORED_DIR_NAMES and current_path / name != research_root
        ]
        for filename in filenames:
            path = current_path / filename
            if path.is_file() and not path.is_symlink():
                yield path


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    return {_relative(path, root): _digest(path) for path in sorted(_iter_protected_files(root))}


def _load_state(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
        raise SystemExit(f"Invalid guard state: {path}")
    return payload


def _safe_relative(value: str, root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SystemExit(f"Path must be project-root-relative: {value}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"Path escapes project root: {value}") from exc
    if resolved == (root / RESEARCH_DIR_NAME).resolve() or (root / RESEARCH_DIR_NAME).resolve() in resolved.parents:
        raise SystemExit(f"Path belongs to {RESEARCH_DIR_NAME}; guard only protects non-research paths: {value}")
    return candidate


def _allowed(path: str, roots: list[Path]) -> bool:
    candidate = Path(path)
    return any(candidate == root or root in candidate.parents for root in roots)


def command_snapshot(args: argparse.Namespace, root: Path) -> int:
    state_path = Path(args.state).resolve()
    if state_path.is_relative_to(root.resolve()):
        raise SystemExit("Guard state must be outside the project root.")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(snapshot(root), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"state={state_path}")
    print(f"protected_files={len(_load_state(state_path))}")
    return 0


def command_check_new_target(args: argparse.Namespace, root: Path) -> int:
    target = _safe_relative(args.target, root)
    allowed_parent = _safe_relative(args.under, root)
    if target == allowed_parent or allowed_parent not in target.parents:
        raise SystemExit(f"Target must be inside the allowed new root: {allowed_parent.as_posix()}")
    if (root / target).exists():
        raise SystemExit(f"Target already exists: {target.as_posix()}")
    print(f"target={target.as_posix()}")
    print("available=true")
    return 0


def command_verify(args: argparse.Namespace, root: Path) -> int:
    before = _load_state(Path(args.state).resolve())
    after = snapshot(root)
    allowed_parent = _safe_relative(args.under, root)
    allowed_roots = [_safe_relative(value, root) for value in args.allow_new_root]
    for allowed_root in allowed_roots:
        if allowed_root == allowed_parent or allowed_parent not in allowed_root.parents:
            raise SystemExit(f"Allowed new root must be inside: {allowed_parent.as_posix()}")

    missing = sorted(path for path in before if path not in after)
    changed = sorted(path for path, digest in before.items() if after.get(path) not in {None, digest})
    added = sorted(path for path in after if path not in before and not _allowed(path, allowed_roots))

    for path in missing:
        print(f"missing={path}")
    for path in changed:
        print(f"changed={path}")
    for path in added:
        print(f"unexpected_added={path}")
    if missing or changed or added:
        print("protected=false")
        return 1
    print("protected=true")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot and verify existing non-research project files.")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    commands = parser.add_subparsers(dest="command", required=True)

    snapshot_cmd = commands.add_parser("snapshot", help="Write a baseline outside the project root.")
    snapshot_cmd.add_argument("--state", required=True, help="External JSON state path.")

    target_cmd = commands.add_parser("check-new-target", help="Require a new, non-research project-relative target.")
    target_cmd.add_argument("--target", required=True)
    target_cmd.add_argument("--under", required=True, help="Existing experiments root containing the new target.")

    verify_cmd = commands.add_parser("verify", help="Verify the baseline and permitted newly-created roots.")
    verify_cmd.add_argument("--state", required=True, help="External JSON state path.")
    verify_cmd.add_argument("--under", required=True, help="Existing experiments root containing every allowed new root.")
    verify_cmd.add_argument("--allow-new-root", action="append", default=[], help="Allowed new project-relative root; repeat as needed.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = resolve_project_root(args.project_root)
    if args.command == "snapshot":
        return command_snapshot(args, root)
    if args.command == "check-new-target":
        return command_check_new_target(args, root)
    return command_verify(args, root)


if __name__ == "__main__":
    raise SystemExit(main())
