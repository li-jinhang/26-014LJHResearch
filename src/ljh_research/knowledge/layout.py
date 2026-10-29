"""Canonical on-disk layout for an ljh research project."""

from __future__ import annotations

import json
from pathlib import Path


# Scientific documents are separate from the project-local skill installation.
RESEARCH_DIR = "ljh research docs"
LEGACY_RESEARCH_DIRS = (".ljh-research", "ljh research")
WORKSPACE_MARKER_FILE = ".workspace.json"
WORKSPACE_LOGS_DIR = "logs"
WORKSPACE_SCHEMA_VERSION = 1
KNOWLEDGE_DIR = "0知识库"
PAPERS_DIR = "1论文"
RESEARCH_POINTS_DIR = "2研究点"
EXPERIMENTS_DIR = "3实验"
REPRODUCTIONS_DIR = "4复现"

SCHEDULER_FILE = "调度.md"
BASIC_INFO_FILE = "00基本信息.md"
CONSTRAINTS_FILE = "01约束文件.md"
FRAMEWORK_FILE = "02框架信息.md"
EXPERIENCE_FILE = "03研发经验.md"


def research_root(project_root: Path) -> Path:
    return project_root / RESEARCH_DIR


def legacy_roots(project_root: Path) -> list[Path]:
    return [project_root / name for name in LEGACY_RESEARCH_DIRS if (project_root / name).exists()]


def workspace_marker_path(project_root: Path) -> Path:
    return research_root(project_root) / WORKSPACE_MARKER_FILE



def workspace_marker_is_valid(project_root: Path) -> bool:
    """Recognize ownership without creating or changing any workspace file."""

    try:
        path = workspace_marker_path(project_root)
        if not path.is_file():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        return (
            isinstance(payload, dict)
            and payload == {"kind": "ljh-research-workspace", "schema_version": WORKSPACE_SCHEMA_VERSION}
            and type(payload.get("schema_version")) is int
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False


def require_workspace_marker(project_root: Path) -> None:
    """Refuse mutation of missing, unmarked, or corrupt workspaces."""

    if not workspace_marker_is_valid(project_root):
        raise ValueError("workspace is not owned by ljh-research; refusing to write (marker missing or invalid)")
