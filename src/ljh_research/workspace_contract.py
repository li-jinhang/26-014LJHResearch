"""Read-only workspace contract used by daily research, without importing setup."""
from pathlib import Path
from .knowledge.layout import research_root, require_workspace_marker, RESEARCH_DIR, LEGACY_RESEARCH_DIRS, legacy_roots
from .knowledge.template_loader import render_template


def resolve_project_root(project_root=None):
    return Path(project_root).expanduser().resolve() if project_root else Path.cwd().resolve()


def parse_frontmatter(text):
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {}
    end = text.find("\n---\n", 4)
    return {key.strip(): value.strip() for line in text[4:end].splitlines()
            if ":" in line for key, value in [line.split(":", 1)]}


def require_owned_workspace(project_root):
    root = resolve_project_root(project_root)
    if root.name in (RESEARCH_DIR, *LEGACY_RESEARCH_DIRS):
        raise ValueError(f"--project-root must be the project root, not {RESEARCH_DIR}")
    if research_root(root).exists() and legacy_roots(root):
        raise ValueError("conflicting research document trees; use ljh-research-setup to inspect before continuing")
    if not research_root(root).exists():
        if legacy_roots(root):
            raise ValueError("workspace migration required; use ljh-research-setup migrate to ljh research docs")
        raise ValueError("workspace is missing; use ljh-research-setup")
    if not research_root(root).resolve().is_relative_to(root):
        raise ValueError("workspace path escapes project root")
    require_workspace_marker(root)
    if not (research_root(root) / "01约束文件.md").is_file():
        raise ValueError("needs_configuration: use ljh-research-setup to repair constraints")
    return research_root(root)


def build_experiment_index():
    return render_template("indexes/3实验-README.md")


def build_research_point_index():
    return render_template("indexes/2研究点-README.md")


def build_reproduction_index():
    return render_template("indexes/4复现-README.md")
