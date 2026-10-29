"""Load and render reusable ljh-research templates."""

from __future__ import annotations

import re
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "resources" / "templates"
TOKEN_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def template_path(relative: str) -> Path:
    """Return a bundled template path and reject path traversal."""
    path = (TEMPLATE_DIR / relative).resolve()
    if TEMPLATE_DIR.resolve() not in path.parents:
        raise ValueError(f"template path escapes template directory: {relative}")
    return path


def load_template(relative: str) -> str:
    path = template_path(relative)
    if not path.is_file():
        raise FileNotFoundError(f"bundled template not found: {relative}")
    return path.read_text(encoding="utf-8")


def render_template(relative: str, **values: object) -> str:
    """Render ``{{UPPER_CASE_TOKEN}}`` placeholders in a bundled template."""
    text = load_template(relative)
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.add(key)
            return match.group(0)
        return str(values[key])

    rendered = TOKEN_PATTERN.sub(replace, text)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"missing template values for {relative}: {names}")
    return rendered


def render_template_if_exists(relative: str, **values: object) -> str:
    """Render a template when present; useful for optional project defaults."""
    if not template_path(relative).is_file():
        return ""
    return render_template(relative, **values)
