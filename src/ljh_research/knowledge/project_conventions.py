"""Read and write the single machine-readable project convention source.

The public interface deliberately stays small: callers load the conventions,
ask whether a declared path exists, or explicitly update a known field.  Parsing,
validation, front-matter rendering, and path safety remain local to this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ljh_research.knowledge.layout import CONSTRAINTS_FILE, require_workspace_marker, research_root
from ljh_research.knowledge.profile_config import normalize_relative_path, resolve_project_relative


SCHEMA_VERSION = 1
PATH_FIELDS = ("models_dir", "configs_dir", "experiments_dir", "main_entry", "training_entry")
LIST_PATH_FIELDS = ("code_roots",)
LIST_FIELDS = ("code_roots", "default_metrics", "fixed_controls")
UPDATE_MODES = ("manual", "automatic")

DEFAULTS: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "domain": None,
    "framework": None,
    "uses_git": None,
    "code_roots": [],
    "models_dir": None,
    "configs_dir": None,
    "experiments_dir": None,
    "main_entry": None,
    "training_entry": None,
    "default_metrics": [],
    "fixed_seed": None,
    "seed_selection": "forbidden",
    "fixed_controls": ["data_split", "seed", "training_budget", "validation_selection"],
    "extra_seed_policy": "robustness_only",
    "update_mode": "manual",
}


def constraints_path(project_root: Path) -> Path:
    return research_root(project_root) / CONSTRAINTS_FILE


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse deliberately flat front matter and return its untouched Markdown body."""

    if not text.startswith("---\n"):
        raise ValueError("01约束文件.md is missing machine-readable front matter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("01约束文件.md front matter is not terminated")
    values: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid convention line: {line!r}")
        key, raw = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError("convention key must not be empty")
        values[key] = parse_value(raw.strip())
    return values, text[end + len("\n---\n") :]


def parse_value(raw: str) -> Any:
    if raw == "null":
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def format_value(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def render_frontmatter(values: dict[str, Any]) -> str:
    return "---\n" + "\n".join(f"{key}: {format_value(values[key])}" for key in DEFAULTS) + "\n---\n"


def validate(values: dict[str, Any], *, project_root: Path | None = None) -> dict[str, Any]:
    unknown = sorted(set(values) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"unknown convention fields: {', '.join(unknown)}")
    merged = {key: values.get(key, default) for key, default in DEFAULTS.items()}
    if merged["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {merged['schema_version']!r}")
    if merged["uses_git"] not in (None, True, False):
        raise ValueError("uses_git must be true, false, or null")
    if merged["fixed_seed"] is not None and (not isinstance(merged["fixed_seed"], int) or isinstance(merged["fixed_seed"], bool)):
        raise ValueError("fixed_seed must be an integer or null")
    if merged["update_mode"] not in UPDATE_MODES:
        raise ValueError(f"update_mode must be one of: {', '.join(UPDATE_MODES)}")
    for field in PATH_FIELDS:
        value = merged[field]
        if value is None:
            continue
        normalized = normalize_relative_path(value, key=field)
        if project_root is not None:
            resolve_project_relative(project_root, normalized, key=field)
        merged[field] = normalized
    for field in LIST_FIELDS:
        value = merged[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{field} must be a list of strings")
        if field in LIST_PATH_FIELDS:
            normalized_items = []
            for index, item in enumerate(value):
                key = f"{field}[{index}]"
                normalized = normalize_relative_path(item, key=key)
                if project_root is not None:
                    resolve_project_relative(project_root, normalized, key=key)
                normalized_items.append(normalized)
            merged[field] = normalized_items
    for field in ("domain", "framework", "seed_selection", "extra_seed_policy"):
        if merged[field] is not None and not isinstance(merged[field], str):
            raise ValueError(f"{field} must be a string or null")
    return merged


def load(project_root: Path) -> dict[str, Any]:
    path = constraints_path(project_root)
    if not path.is_file():
        raise ValueError(f"needs_configuration: missing {path.name}")
    try:
        raw, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read conventions: {exc}") from exc
    return validate(raw, project_root=project_root)


def write(project_root: Path, values: dict[str, Any]) -> Path:
    require_workspace_marker(project_root)
    path = constraints_path(project_root)
    if not path.is_file():
        raise ValueError(f"needs_configuration: missing {path.name}")
    raw = path.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw)
    validated = validate(values, project_root=project_root)
    path.write_text(render_frontmatter(validated) + body, encoding="utf-8")
    return path


def update(project_root: Path, key: str, value: Any) -> dict[str, Any]:
    require_workspace_marker(project_root)
    if key not in DEFAULTS:
        raise ValueError(f"unknown convention field: {key}")
    values = load(project_root)
    values[key] = value
    write(project_root, values)
    return values


def declared_path_states(project_root: Path, values: dict[str, Any]) -> dict[str, str]:
    """Return explicit states without ever inferring an undeclared project path."""

    states: dict[str, str] = {}
    for field in PATH_FIELDS:
        value = values[field]
        if value is None:
            states[field] = "needs_configuration"
        elif resolve_project_relative(project_root, value, key=field).exists():
            states[field] = "configured"
        else:
            states[field] = "missing"
    for field in LIST_PATH_FIELDS:
        values_for_field = values[field]
        if not values_for_field:
            states[field] = "needs_configuration"
        else:
            missing = any(not resolve_project_relative(project_root, value, key=field).exists() for value in values_for_field)
            states[field] = "missing" if missing else "configured"
    return states
