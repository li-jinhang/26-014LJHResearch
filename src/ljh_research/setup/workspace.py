#!/usr/bin/env python3
"""Plan, create, validate, or repair one ``ljh research docs`` workspace safely."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.foam_workspace import expected_files as expected_foam_files
from ljh_research.knowledge.foam_workspace import validate_foam_workspace
from ljh_research.knowledge.layout import (
    BASIC_INFO_FILE,
    CONSTRAINTS_FILE,
    EXPERIENCE_FILE,
    EXPERIMENTS_DIR,
    FRAMEWORK_FILE,
    KNOWLEDGE_DIR,
    PAPERS_DIR,
    REPRODUCTIONS_DIR,
    RESEARCH_DIR,
    RESEARCH_POINTS_DIR,
    SCHEDULER_FILE,
    WORKSPACE_LOGS_DIR,
    WORKSPACE_MARKER_FILE,
    WORKSPACE_SCHEMA_VERSION,
    research_root,
    workspace_marker_is_valid,
    legacy_roots,
    LEGACY_RESEARCH_DIRS,
)
from ljh_research.knowledge.project_conventions import declared_path_states, load as load_conventions, split_frontmatter
from ljh_research.knowledge.template_loader import render_template
from ljh_research.knowledge.workflow_log import close as close_log
from ljh_research.knowledge.workflow_log import create as create_log
from ljh_research.knowledge.workflow_log import record as record_log
from ljh_research.memory.layout import MEMORY_DIRECTORIES, expected_files as memory_files


EXPECTED_TITLES = {
    SCHEDULER_FILE: ("# 调度",),
    BASIC_INFO_FILE: ("# 基本信息",),
    CONSTRAINTS_FILE: ("# 项目约束",),
    FRAMEWORK_FILE: ("# 研究项目总体思路与框架概要", "# 研究项目大体思路与框架概要"),
    EXPERIENCE_FILE: ("# 项目研发重要经验",),
}
SUSPICIOUS_MOJIBAKE_FRAGMENTS = ("锟", "鈥", "婧愭", "鎻愬", "鐭ヨ", "姒傚")
TOPIC_LAYERS = ("源文件库", "提取内容", "知识库", "概念库")


def resolve_project_root(project_root: str | None) -> Path:
    return Path(project_root).expanduser().resolve() if project_root else Path.cwd().resolve()


def build_templates(today: str) -> dict[str, str]:
    template_map = {
        SCHEDULER_FILE: "root/调度.md",
        BASIC_INFO_FILE: "root/00基本信息.md",
        CONSTRAINTS_FILE: "root/01约束文件.md",
        FRAMEWORK_FILE: "root/02框架信息.md",
        EXPERIENCE_FILE: "root/03研发经验.md",
    }
    return {filename: render_template(template, DATE=today) for filename, template in template_map.items()}


def build_experiment_index() -> str:
    return render_template("indexes/3实验-README.md")


def build_research_point_index() -> str:
    return render_template("indexes/2研究点-README.md")


def build_reproduction_index() -> str:
    return render_template("indexes/4复现-README.md")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Compatibility parser for card metadata; conventions use project_conventions."""

    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def _body_without_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    try:
        _, body = split_frontmatter(text)
        return body
    except ValueError:
        return text


def validate_reproduction_cards(reproduction_dir: Path) -> list[str]:
    errors: list[str] = []
    if not reproduction_dir.is_dir():
        return errors
    for path in sorted(reproduction_dir.glob("REPRO-*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{REPRODUCTIONS_DIR}/{path.name}: not valid UTF-8 ({exc})")
            continue
        metadata = parse_frontmatter(text)
        required = ("id", "title", "status", "paper_id", "repo_url", "paper_metrics", "tolerance")
        missing = [key for key in required if key not in metadata]
        if missing:
            errors.append(f"{REPRODUCTIONS_DIR}/{path.name}: missing frontmatter keys: {', '.join(missing)}")
    return errors


def validate_markdown_file(path: Path, expected_titles: tuple[str, ...]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"{path.name}: not valid UTF-8 ({exc})"]
    first_nonblank = next((line.strip() for line in _body_without_frontmatter(text).splitlines() if line.strip()), "")
    errors: list[str] = []
    if first_nonblank not in expected_titles:
        errors.append(f"{path.name}: expected one of {expected_titles!r}, got {first_nonblank!r}")
    suspicious = [fragment for fragment in SUSPICIOUS_MOJIBAKE_FRAGMENTS if fragment in text]
    if suspicious:
        errors.append(f"{path.name}: suspicious mojibake fragments: {', '.join(suspicious)}")
    return errors


def validate_topic_structure(knowledge_base_dir: Path) -> list[str]:
    errors: list[str] = []
    if not knowledge_base_dir.is_dir():
        return errors
    for domain in knowledge_base_dir.iterdir():
        if not domain.is_dir():
            continue
        for topic in domain.iterdir():
            if not topic.is_dir():
                continue
            for child in topic.iterdir():
                if not child.is_dir() or child.name in TOPIC_LAYERS:
                    continue
                if any((child / layer).is_dir() for layer in TOPIC_LAYERS):
                    errors.append(f"nested topic detected: {topic.relative_to(knowledge_base_dir)}/{child.name}")
    return errors


def required_directories() -> tuple[str, ...]:
    return tuple(dict.fromkeys((KNOWLEDGE_DIR, PAPERS_DIR, RESEARCH_POINTS_DIR, EXPERIMENTS_DIR, REPRODUCTIONS_DIR, WORKSPACE_LOGS_DIR, *MEMORY_DIRECTORIES)))


def expected_workspace_files(today: str) -> dict[str, str]:
    files = build_templates(today)
    files.update(memory_files())
    files[f"{RESEARCH_POINTS_DIR}/README.md"] = build_research_point_index()
    files[f"{EXPERIMENTS_DIR}/README.md"] = build_experiment_index()
    files[f"{REPRODUCTIONS_DIR}/README.md"] = build_reproduction_index()
    for relative, content in expected_foam_files().items():
        files[f".foam/{relative}"] = content
    return files


def marker_payload() -> dict[str, object]:
    return {"kind": "ljh-research-workspace", "schema_version": WORKSPACE_SCHEMA_VERSION}


def marker_path(project_root: Path) -> Path:
    return research_root(project_root) / WORKSPACE_MARKER_FILE


def marker_is_valid(project_root: Path) -> bool:
    return workspace_marker_is_valid(project_root)


@dataclass(frozen=True)
class ValidationReport:
    status: str
    errors: tuple[str, ...]
    needs_configuration: tuple[str, ...]
    missing_paths: tuple[str, ...]


def validate_workspace(project_root: Path) -> ValidationReport:
    workspace = research_root(project_root)
    if workspace.exists() and legacy_roots(project_root):
        return ValidationReport("conflict", ("Canonical and legacy research document trees both exist; inspect before continuing",), (), ())
    if not workspace.exists():
        if legacy_roots(project_root):
            return ValidationReport("migration_required", tuple(f"legacy workspace: {p.name}; use setup migrate" for p in legacy_roots(project_root)), (), ())
        return ValidationReport("missing", (), (), ())
    if not workspace.is_dir() or not marker_is_valid(project_root):
        return ValidationReport("unowned", ("workspace marker missing or invalid",), (), ())

    errors: list[str] = []
    for directory in required_directories():
        if not (workspace / directory).is_dir():
            errors.append(f"{directory}: missing directory")
    for filename, titles in EXPECTED_TITLES.items():
        path = workspace / filename
        if not path.exists():
            errors.append(f"{filename}: missing")
        else:
            errors.extend(validate_markdown_file(path, titles))
    for directory in (RESEARCH_POINTS_DIR, EXPERIMENTS_DIR, REPRODUCTIONS_DIR):
        if not (workspace / directory / "README.md").is_file():
            errors.append(f"{directory}/README.md: missing")
    errors.extend(validate_reproduction_cards(workspace / REPRODUCTIONS_DIR))
    errors.extend(validate_foam_workspace(workspace))
    for relative in memory_files():
        if not (workspace / relative).is_file():
            errors.append(f"{relative}: missing")
    errors.extend(validate_topic_structure(workspace / KNOWLEDGE_DIR))

    needs_configuration: list[str] = []
    missing_paths: list[str] = []
    try:
        conventions = load_conventions(project_root)
        for field, state in declared_path_states(project_root, conventions).items():
            if state == "needs_configuration":
                needs_configuration.append(field)
            elif state == "missing":
                missing_paths.append(field)
    except ValueError as exc:
        needs_configuration.append(str(exc))
    return ValidationReport("valid" if not errors else "incomplete", tuple(errors), tuple(needs_configuration), tuple(missing_paths))


def print_report(report: ValidationReport) -> None:
    print(f"workspace_status={report.status}")
    for error in report.errors:
        print(f"error={error}")
    for field in report.needs_configuration:
        print(f"needs_configuration={field}")
    for field in report.missing_paths:
        print(f"missing_path={field}")


def require_owned_workspace(project_root: Path) -> Path:
    """Refuse feature writes outside a validated workspace lifecycle."""

    assert_project_root_is_not_workspace(project_root)
    report = validate_workspace(project_root)
    if report.status == "missing":
        raise SystemExit("workspace is missing; ask the user to initialize ljh research docs first")
    if report.status == "unowned":
        raise SystemExit("workspace is not owned by ljh-research; refusing to write")
    if report.status != "valid":
        raise SystemExit("workspace is incomplete; ask the user to run repair first")
    return research_root(project_root)


def assert_project_root_is_not_workspace(project_root: Path) -> None:
    if project_root.name in (RESEARCH_DIR, *LEGACY_RESEARCH_DIRS):
        raise SystemExit(f"--project-root must be the project root, not {RESEARCH_DIR}")


def plan(project_root: Path) -> list[str]:
    assert_project_root_is_not_workspace(project_root)
    workspace = research_root(project_root)
    if not workspace.exists():
        if legacy_roots(project_root):
            return [f"STOP legacy workspace {p.name}/ exists; use explicit setup migrate to {RESEARCH_DIR}/" for p in legacy_roots(project_root)]
        return [
            f"CREATE {RESEARCH_DIR}/",
            *(f"CREATE {RESEARCH_DIR}/{directory}/" for directory in required_directories()),
            *(f"CREATE {RESEARCH_DIR}/{relative}" for relative in expected_workspace_files(date.today().isoformat())),
            f"CREATE {RESEARCH_DIR}/{WORKSPACE_MARKER_FILE}",
        ]
    report = validate_workspace(project_root)
    if report.status == "unowned":
        return [f"STOP {RESEARCH_DIR}/ is not a recognized ljh-research workspace"]
    planned = [f"VALIDATE {RESEARCH_DIR}/"]
    for error in report.errors:
        if error.endswith(": missing") or error.endswith(": missing directory"):
            planned.append(f"REPAIR {error.split(':', 1)[0]}")
    return planned


def _write_workspace(destination: Path, today: str) -> list[str]:
    created: list[str] = []
    for directory in required_directories():
        (destination / directory).mkdir(parents=True, exist_ok=False)
        created.append(f"{directory}/")
    (destination / WORKSPACE_MARKER_FILE).write_text(
        json.dumps(marker_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    created.append(WORKSPACE_MARKER_FILE)
    for relative, content in expected_workspace_files(today).items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(relative)
    return created


def command_create(project_root: Path, automatic_task: str | None = None) -> int:
    assert_project_root_is_not_workspace(project_root)
    workspace = research_root(project_root)
    if workspace.exists():
        raise SystemExit(f"workspace already exists: {workspace}; run validate or repair instead")
    if legacy_roots(project_root):
        raise SystemExit("legacy research workspace exists; use explicit setup migrate instead of creating a second document tree")
    project_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f"{RESEARCH_DIR}-stage-", dir=project_root))
    try:
        created = _write_workspace(stage, date.today().isoformat())
        stage.replace(workspace)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    report = validate_workspace(project_root)
    if report.status != "valid":
        raise SystemExit("created workspace did not validate: " + "; ".join(report.errors))
    log_path = None
    if automatic_task:
        log_path = create_log(project_root, automatic_task)
        for relative in created:
            record_log(log_path, "CREATE", f"{RESEARCH_DIR}/{relative}", "workspace initialization")
        close_log(log_path)
    print(f"workspace={workspace}")
    print("created=true")
    for relative in created:
        print(f"created={relative}")
    if log_path:
        print(f"log={log_path}")
    return 0


def command_repair(project_root: Path, automatic_task: str | None = None) -> int:
    assert_project_root_is_not_workspace(project_root)
    workspace = research_root(project_root)
    if not workspace.exists():
        raise SystemExit("workspace is missing; run create after explicit user approval")
    if not marker_is_valid(project_root):
        raise SystemExit("workspace is not owned by ljh-research; refusing to write")
    report = validate_workspace(project_root)
    non_repairable = [error for error in report.errors if not error.endswith(": missing") and not error.endswith(": missing directory")]
    if non_repairable:
        raise SystemExit("workspace has non-repairable validation errors: " + "; ".join(non_repairable))
    created: list[str] = []
    for directory in required_directories():
        path = workspace / directory
        if not path.exists():
            path.mkdir(parents=True)
            created.append(f"{directory}/")
    for relative, content in expected_workspace_files(date.today().isoformat()).items():
        path = workspace / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(relative)
    report = validate_workspace(project_root)
    if report.status != "valid":
        raise SystemExit("repair did not validate: " + "; ".join(report.errors))
    log_path = None
    if automatic_task and created:
        log_path = create_log(project_root, automatic_task)
        for relative in created:
            record_log(log_path, "CREATE", f"{RESEARCH_DIR}/{relative}", "workspace repair")
        close_log(log_path)
    print(f"workspace={workspace}")
    print(f"repaired={str(bool(created)).lower()}")
    for relative in created:
        print(f"created={relative}")
    if log_path:
        print(f"log={log_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "create", "validate", "repair"), nargs="?", default="validate")
    parser.add_argument("--project-root", help="Project root path. Defaults to the current directory.")
    parser.add_argument("--automatic-task", help="Record this explicit automatic task in one timestamped log.")
    return parser


def main() -> int:
    configure_utf8()
    args = build_parser().parse_args()
    project_root = resolve_project_root(args.project_root)
    if args.operation == "plan":
        for action in plan(project_root):
            print(action)
        return 0
    if args.operation == "create":
        return command_create(project_root, args.automatic_task)
    if args.operation == "repair":
        return command_repair(project_root, args.automatic_task)
    assert_project_root_is_not_workspace(project_root)
    report = validate_workspace(project_root)
    print_report(report)
    return 0 if report.status == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
