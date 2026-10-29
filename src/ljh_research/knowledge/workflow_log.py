"""Append compact, per-task automatic-workflow traces without copying user content."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ljh_research.knowledge.layout import WORKSPACE_LOGS_DIR, research_root


def create(project_root: Path, task: str) -> Path:
    logs_dir = research_root(project_root) / WORKSPACE_LOGS_DIR
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = logs_dir / f"{stamp}.log"
    suffix = 1
    while path.exists():
        path = logs_dir / f"{stamp}-{suffix}.log"
        suffix += 1
    path.write_text(f"START task={task}\n", encoding="utf-8")
    return path


def record(log_path: Path, operation: str, relative_path: str, summary: str, source: str = "") -> None:
    if operation not in {"CREATE", "UPDATE", "DELETE"}:
        raise ValueError(f"unsupported log operation: {operation}")
    line = f"{operation} path={relative_path} summary={summary}"
    if source:
        line += f" source={source}"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def close(log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("END\n")
