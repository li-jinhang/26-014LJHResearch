"""Foam workspace resources for ljh research structured memory."""

from __future__ import annotations

from pathlib import Path

from ljh_research.knowledge.template_loader import load_template

FOAM_DIR = ".foam"

TEMPLATES: tuple[str, ...] = (
    "foam/templates/research-point.md",
    "foam/templates/experiment.md",
    "foam/templates/reproduction.md",
    "foam/queries/active-research-points.yaml",
    "foam/queries/pending-experiments.yaml",
    "foam/queries/active-reproductions.yaml",
    "foam/queries/paper-notes.yaml",
    "foam/queries/framework-adoption-pending.yaml",
)

# Kept as a compatibility alias for callers that used the old embedded mapping.
FILES: dict[str, str] = {relative.removeprefix("foam/"): load_template(relative) for relative in TEMPLATES}


def expected_files() -> dict[str, str]:
    """Return the complete Foam manifest without writing a project file."""

    return dict(FILES)


def ensure_foam_workspace(research_dir: Path, force: bool = False) -> dict[str, str]:
    """Create missing Foam templates and saved queries without touching cards."""
    statuses: dict[str, str] = {}
    foam_dir = research_dir / FOAM_DIR
    for relative in TEMPLATES:
        destination = relative.removeprefix("foam/")
        content = load_template(relative)
        path = foam_dir / destination
        if path.exists() and not force:
            statuses[f"{FOAM_DIR}/{destination}"] = "kept"
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        statuses[f"{FOAM_DIR}/{destination}"] = "written" if force else "created"
    return statuses


def validate_foam_workspace(research_dir: Path) -> list[str]:
    errors: list[str] = []
    foam_dir = research_dir / FOAM_DIR
    for relative in TEMPLATES:
        destination = relative.removeprefix("foam/")
        path = foam_dir / destination
        if not path.is_file():
            errors.append(f"{FOAM_DIR}/{destination}: missing")
            continue
        if not path.read_text(encoding="utf-8").strip():
            errors.append(f"{FOAM_DIR}/{destination}: empty")
    return errors
