"""Shared validation for project-relative paths stored in the skill profile."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


PROFILE_PATH_KEYS = ("experiments_dir", "models_dir", "configs_dir")


def normalize_relative_path(value: Any, *, key: str) -> str:
    """Validate and normalize one project-relative path."""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a non-empty relative path string")
    raw = value.strip().replace("\\", "/")
    if not raw:
        raise ValueError(f"{key} must be a non-empty relative path string")
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"{key} must stay relative to the project root: {value!r}")
    if ".." in posix.parts or ".." in windows.parts:
        raise ValueError(f"{key} must not contain '..': {value!r}")
    parts = [part for part in posix.parts if part not in ("", ".")]
    if not parts:
        raise ValueError(f"{key} must be a non-empty relative path string")
    return "/".join(parts)


def resolve_project_relative(project_root: Path, value: Any, *, key: str) -> Path:
    """Resolve a profile path and enforce the project boundary."""
    normalized = normalize_relative_path(value, key=key)
    root = project_root.expanduser().resolve()
    candidate = (root / Path(*PurePosixPath(normalized).parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        # This also catches a symlink inside the project that points outside it.
        raise ValueError(f"{key} resolves outside the project root: {value!r}") from exc
    return candidate


def validate_profile_paths(
    data: dict[str, Any], *, project_root: Path | None = None
) -> dict[str, Any]:
    """Return a copy of profile data after validating path-bearing fields."""
    if not isinstance(data, dict):
        raise ValueError("project profile must be a JSON object")
    validated = dict(data)
    for key in PROFILE_PATH_KEYS:
        if key in validated and validated[key] is not None:
            normalized = normalize_relative_path(validated[key], key=key)
            if project_root is not None:
                resolve_project_relative(project_root, normalized, key=key)
            validated[key] = normalized
    if "code_roots" in validated and validated["code_roots"] is not None:
        roots = validated["code_roots"]
        if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
            raise ValueError("code_roots must be a list of relative path strings")
        normalized_roots = []
        for index, root in enumerate(roots):
            key = f"code_roots[{index}]"
            normalized = normalize_relative_path(root, key=key)
            if project_root is not None:
                resolve_project_relative(project_root, normalized, key=key)
            normalized_roots.append(normalized)
        validated["code_roots"] = normalized_roots
    return validated
