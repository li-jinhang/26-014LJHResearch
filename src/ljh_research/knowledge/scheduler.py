#!/usr/bin/env python3
"""Route research-point outcomes without duplicating their source-of-truth state."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.experiment_point import experiments_dir, find_card as find_experiment_card, parse_frontmatter as parse_experiment_frontmatter
from ljh_research.workspace_contract import resolve_project_root
from ljh_research.knowledge.layout import SCHEDULER_FILE, research_root
from ljh_research.knowledge.research_point import find_card as find_research_point_card, iter_cards, parse_frontmatter
from ljh_research.knowledge.template_loader import load_template


ROUTING_START = "<!-- LJH-SCHEDULER-ROUTING-START -->"
ROUTING_END = "<!-- LJH-SCHEDULER-ROUTING-END -->"


def scheduler_path(project_root: Path) -> Path:
    return research_root(project_root) / SCHEDULER_FILE


def routing_block() -> str:
    template = load_template("root/调度.md")
    start = template.index(ROUTING_START)
    end = template.index(ROUTING_END, start) + len(ROUTING_END)
    return template[start:end]


def require_scheduler(project_root: Path) -> Path:
    path = scheduler_path(project_root)
    if not path.is_file():
        raise SystemExit(f"Scheduler is missing: {path}; run init_ljh_research.py first")
    text = path.read_text(encoding="utf-8")
    if ROUTING_START not in text or ROUTING_END not in text:
        raise SystemExit("Scheduler lacks state routing; run scheduler.py bootstrap to add the non-destructive routing block")
    return path


def parse_related_points(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = re.findall(r"RP-\d{4,}", value.upper())
    if not isinstance(parsed, list):
        return []
    result: list[str] = []
    for item in parsed:
        point_id = str(item).strip().upper()
        if re.fullmatch(r"RP-\d{4,}", point_id) and point_id not in result:
            result.append(point_id)
    return result


def workflow_for(metadata: dict[str, str]) -> tuple[str, str]:
    status = metadata.get("status", "draft")
    adoption = metadata.get("framework_adoption", "not_assessed")
    if status == "draft":
        return "candidate-preparation", "补全假设、最小实现边界和验证协议；由用户决定是否激活。"
    if status == "active":
        return "active-evidence", "补齐论文、代码、EXP/REP 证据；维持单变量与可复现控制。"
    if status == "validated":
        if adoption in {"not_assessed", "pending_decision"}:
            return "validated-framework-adoption", "询问用户是否更新基础框架；先规划文档修改，再取得对修改计划的同意。"
        if adoption == "adopted":
            return "adopted-align", "核查 02框架信息、调度、代码和索引一致性，并保留版本与来源证据。"
        if adoption == "deferred":
            return "validated-deferred", "保留已验证证据；等待用户重新开启框架采纳决策。"
        return "validated-superseded", "保留科学验证记录，沿链接检查替代研究点或框架版本。"
    if status == "paused":
        return "paused", "保留暂停理由；只有新的明确证据才重新进入评估。"
    if status == "rejected":
        return "rejected", "保留证伪证据与失败归因；不自动删除或重开。"
    return "unknown", f"未知研究状态：{status}"


def print_route(point_id: str, metadata: dict[str, str]) -> None:
    workflow, action = workflow_for(metadata)
    print(f"research_point={point_id}")
    print(f"research_status={metadata.get('status', 'draft')}")
    print(f"framework_adoption={metadata.get('framework_adoption', 'not_assessed')}")
    print(f"workflow={workflow}")
    print(f"next_action={action}")


def command_bootstrap(project_root: Path) -> int:
    path = scheduler_path(project_root)
    if not path.is_file():
        raise SystemExit(f"Scheduler is missing: {path}; run init_ljh_research.py first")
    text = path.read_text(encoding="utf-8")
    if ROUTING_START in text and ROUTING_END in text:
        print(f"kept={path}")
        return 0
    separator = "" if text.endswith("\n") else "\n"
    path.write_text(text.rstrip() + separator + "\n" + routing_block() + "\n", encoding="utf-8")
    print(f"updated={path}")
    return 0


def command_next(args: argparse.Namespace, project_root: Path) -> int:
    require_scheduler(project_root)
    points_directory = research_root(project_root) / "2研究点"
    if args.id:
        _, text = find_research_point_card(points_directory, args.id)
        print_route(args.id.upper(), parse_frontmatter(text))
        return 0

    path, text = find_experiment_card(experiments_dir(project_root), args.experiment)
    metadata = parse_experiment_frontmatter(text)
    print(f"experiment={metadata.get('id', path.stem)}")
    print(f"experiment_status={metadata.get('status', '')}")
    if metadata.get("status") != "completed":
        print("event=experiment-not-completed")
        print("next_action=先记录当前判断并经用户确认置为 completed，再进入关联研究点的调度。")
        return 0
    print("event=experiment-completed")
    related = parse_related_points(metadata.get("research_points", "[]"))
    if not related:
        print("next_action=该实验尚未结构化关联研究点；先补充 RP-NNN 关系，不自动推断。")
        return 0
    for point_id in related:
        _, point_text = find_research_point_card(points_directory, point_id)
        print_route(point_id, parse_frontmatter(point_text))
    return 0


def command_queue(project_root: Path) -> int:
    require_scheduler(project_root)
    directory = research_root(project_root) / "2研究点"
    pending: list[tuple[str, dict[str, str]]] = []
    for path, text in iter_cards(directory):
        metadata = parse_frontmatter(text)
        if metadata.get("status") == "validated" and metadata.get("framework_adoption", "not_assessed") in {"not_assessed", "pending_decision"}:
            pending.append((metadata.get("id", path.stem), metadata))
    for point_id, metadata in pending:
        print(f"{point_id}\t{metadata.get('title', '')}\t{metadata.get('framework_adoption', 'not_assessed')}")
    print(f"count={len(pending)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route ljh-research states to their next governed workflow.")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap", help="Add the routing block to a legacy scheduler without overwriting it.")
    next_command = commands.add_parser("next", help="Read one RP or completed EXP and report its next workflow.")
    target = next_command.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", help="Research point ID, for example RP-001.")
    target.add_argument("--experiment", help="Completed experiment ID, for example EXP-001.")
    commands.add_parser("queue", help="List validated research points awaiting a framework-adoption decision.")
    return parser


def main() -> int:
    configure_utf8()
    args = build_parser().parse_args()
    project_root = resolve_project_root(args.project_root)
    if args.command == "bootstrap":
        return command_bootstrap(project_root)
    if args.command == "next":
        return command_next(args, project_root)
    return command_queue(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
