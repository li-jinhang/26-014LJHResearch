#!/usr/bin/env python3
"""Create, refine, index, and search ljh research research-point cards."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import build_research_point_index, require_owned_workspace, resolve_project_root
from ljh_research.knowledge.card_schema import STATUSES, card_filename, next_identifier
from ljh_research.knowledge.template_loader import render_template
from ljh_research.knowledge.layout import RESEARCH_POINTS_DIR, research_root


VALID_STATUSES = STATUSES["research_point"]
INITIAL_STATUSES = ("draft", "active")
VALID_TRANSITIONS = {
    "draft": ("active", "paused"),
    "active": ("draft", "validated", "rejected", "paused"),
    "validated": ("paused",),
    "paused": ("draft", "active", "rejected"),
    "rejected": (),
}
FRAMEWORK_ADOPTIONS = ("not_assessed", "pending_decision", "adopted", "deferred", "superseded")
FRAMEWORK_TRANSITIONS = {
    "not_assessed": ("pending_decision",),
    "pending_decision": ("adopted", "deferred"),
    "adopted": ("superseded",),
    "deferred": ("pending_decision", "superseded"),
    "superseded": (),
}
VALID_PRIORITIES = ("高", "中", "低")
SECTION_MAP = {
    "gap": "研究问题与当前代码缺口",
    "hypothesis": "核心假设",
    "innovation": "创新点及与已有文献的差异",
    "impact": "预期影响的指标与作用机制",
    "implementation": "具体实现边界",
    "validation": "基线、消融和验证协议",
    "risks": "风险、反例和停止条件",
    "evidence": "证据",
}


def points_dir(project_root: Path) -> Path:
    return research_root(project_root) / RESEARCH_POINTS_DIR


def implemented_dir(directory: Path) -> Path:
    return directory / "已实现"


def normalize_title(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value, flags=re.UNICODE).lower()


def parse_frontmatter(text: str) -> dict[str, str]:
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


def replace_metadata(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}:\s*.*$")
    if pattern.search(text):
        return pattern.sub(f"{key}: {value}", text, count=1)
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SystemExit("Research point card has invalid frontmatter")
    return text[:end] + f"\n{key}: {value}" + text[end:]


def iter_cards(directory: Path):
    if not directory.exists():
        return
    for path in sorted(directory.rglob("RP-*.md")):
        yield path, path.read_text(encoding="utf-8")


def next_id(directory: Path) -> str:
    return next_identifier(directory, "RP")


def find_card(directory: Path, point_id: str) -> tuple[Path, str]:
    normalized_id = point_id.upper()
    matches = list(directory.rglob(f"{normalized_id}-*.md"))
    if len(matches) != 1:
        raise SystemExit(f"Expected one card for {normalized_id}, found {len(matches)}")
    return matches[0], matches[0].read_text(encoding="utf-8")


def append_to_section(text: str, heading: str, content: str) -> str:
    marker = f"## {heading}"
    addition = content.strip()
    if marker not in text:
        history_marker = "## 迭代历史"
        block = f"{marker}\n\n{addition}\n\n"
        if history_marker in text:
            return text.replace(history_marker, block + history_marker, 1)
        return text.rstrip() + "\n\n" + block
    start = text.index(marker) + len(marker)
    next_heading = text.find("\n## ", start)
    insert_at = next_heading if next_heading != -1 else len(text)
    current = text[start:insert_at].rstrip()
    updated = current + "\n\n" + addition + "\n"
    return text[:start] + updated + text[insert_at:]


def append_history(text: str, message: str, today: str) -> str:
    return append_to_section(text, "迭代历史", f"- {today}：{message}")


def render_index(directory: Path) -> str:
    rows = []
    for path, text in iter_cards(directory):
        metadata = parse_frontmatter(text)
        title = metadata.get("title", path.stem)
        rows.append(
            "| {id} | [{title}]({file}) | {status} | {adoption} | {priority} | {updated} | {tags} |".format(
                id=metadata.get("id", path.stem.split("-", 2)[:2]),
                title=title.replace("|", "\\|"),
                file=path.relative_to(directory).as_posix(),
                status=metadata.get("status", "draft"),
                adoption=metadata.get("framework_adoption", "not_assessed"),
                priority=metadata.get("priority", "中"),
                updated=metadata.get("updated", ""),
                tags=metadata.get("tags", ""),
            )
        )
    base = build_research_point_index().rstrip()
    return base + ("\n" + "\n".join(rows) if rows else "") + "\n"


def rebuild_index(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / "README.md"
    index.write_text(render_index(directory), encoding="utf-8")
    return index


def card_body(args: argparse.Namespace, point_id: str, today: str) -> str:
    tags = ", ".join(dict.fromkeys(tag.strip() for tag in args.tags.split(",") if tag.strip()))
    evidence = "\n".join(f"- {item}" for item in args.evidence) or "- 待补充可核查的代码、文献或实验记录。"
    return render_template(
        "cards/research-point.md",
        ID=point_id,
        TITLE=args.title.strip(),
        STATUS=args.status,
        PRIORITY=args.priority,
        CREATED=today,
        UPDATED=today,
        TAGS=tags,
        GAP=args.gap or "待补充。",
        HYPOTHESIS=args.hypothesis or "待补充。",
        INNOVATION=args.innovation or "待补充。",
        IMPACT=args.impact or "待补充。不得把预测写成已经实现的指标提升。",
        IMPLEMENTATION=args.implementation or "待补充。",
        VALIDATION=args.validation or "待补充。",
        RISKS=args.risks or "待补充。",
        EVIDENCE=evidence,
    )


def command_add(args: argparse.Namespace, directory: Path) -> int:
    normalized = normalize_title(args.title)
    for path, text in iter_cards(directory):
        if normalize_title(parse_frontmatter(text).get("title", path.stem)) == normalized:
            print("exists=true")
            print(f"card={path}")
            return 0
    point_id = next_id(directory)
    today = date.today().isoformat()
    path = directory / card_filename(point_id, args.slug or args.title, fallback="research-point")
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(card_body(args, point_id, today), encoding="utf-8")
    index = rebuild_index(directory)
    print("created=true")
    print(f"id={point_id}")
    print(f"card={path}")
    print(f"index={index}")
    return 0


def command_refine(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    entry = f"- {today}：{args.text.strip()}"
    text = append_to_section(text, SECTION_MAP[args.section], entry)
    text = replace_metadata(text, "updated", today)
    text = append_history(text, args.note or f"补充“{SECTION_MAP[args.section]}”证据。", today)
    path.write_text(text, encoding="utf-8")
    rebuild_index(directory)
    print(f"updated={path}")
    return 0


def command_status(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    old_status = parse_frontmatter(text).get("status", "draft")
    if old_status == args.status:
        print(f"unchanged={path}")
        print(f"status={args.status}")
        return 0
    allowed = VALID_TRANSITIONS.get(old_status)
    if allowed is None:
        raise SystemExit(f"Research point {args.id.upper()} has unsupported status: {old_status}")
    if args.status not in allowed:
        raise SystemExit(f"Invalid research-status transition: {old_status} -> {args.status}")
    text = replace_metadata(text, "status", args.status)
    if args.status == "validated" and parse_frontmatter(text).get("framework_adoption", "not_assessed") == "not_assessed":
        text = replace_metadata(text, "framework_adoption", "pending_decision")
        text = append_to_section(
            text,
            "框架采纳",
            f"- {today}：研究状态 `validated`，进入 `pending_decision`；请通过 `scheduler.py next --id {args.id.upper()}` 发起用户的框架采纳决策。",
        )
    text = replace_metadata(text, "updated", today)
    text = append_history(text, args.note or f"状态由“{old_status}”变更为“{args.status}”。", today)
    path.write_text(text, encoding="utf-8")
    rebuild_index(directory)
    print(f"updated={path}")
    print(f"status={args.status}")
    return 0


def command_framework(args: argparse.Namespace, directory: Path) -> int:
    """Record a user-approved framework-adoption decision for one validated RP."""
    path, text = find_card(directory, args.id)
    metadata = parse_frontmatter(text)
    if metadata.get("status") != "validated":
        raise SystemExit("Framework adoption can be decided only for a validated research point")
    old = metadata.get("framework_adoption", "not_assessed")
    if args.decision not in FRAMEWORK_TRANSITIONS.get(old, ()):
        raise SystemExit(f"Invalid framework-adoption transition: {old} -> {args.decision}")
    if args.decision == "adopted" and (not args.framework_version or not args.framework_link):
        raise SystemExit("Adoption requires --framework-version and --framework-link after approved document updates")
    if args.decision == "superseded" and not args.successor:
        raise SystemExit("Superseding an adopted/deferred framework requires --successor")

    today = date.today().isoformat()
    text = replace_metadata(text, "framework_adoption", args.decision)
    if args.framework_version:
        text = replace_metadata(text, "framework_version", args.framework_version.strip())
    if args.framework_link:
        text = replace_metadata(text, "framework_link", args.framework_link.strip())
    text = replace_metadata(text, "updated", today)
    details = [f"- {today}：框架采纳状态由 `{old}` 变更为 `{args.decision}`。"]
    if args.framework_version:
        details.append(f"- 框架版本：`{args.framework_version.strip()}`。")
    if args.framework_link:
        details.append(f"- 主框架链接：{args.framework_link.strip()}。")
    if args.successor:
        details.append(f"- 替代项：{args.successor.strip()}。")
    if args.note:
        details.append(f"- 说明：{args.note.strip()}")
    text = append_to_section(text, "框架采纳", "\n".join(details))
    text = append_history(text, args.note or f"框架采纳状态更新为 `{args.decision}`。", today)
    path.write_text(text, encoding="utf-8")
    rebuild_index(directory)
    print(f"updated={path}")
    print(f"framework_adoption={args.decision}")
    return 0


def command_implement(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    destination_dir = implemented_dir(directory)
    if path.parent == destination_dir:
        raise SystemExit(f"Research point {args.id.upper()} is already in 已实现")

    today = date.today().isoformat()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / path.name
    if destination.exists():
        raise SystemExit(f"Destination already exists: {destination}")

    text = replace_metadata(text, "implementation_status", "implemented")
    text = replace_metadata(text, "implemented", today)
    text = replace_metadata(text, "updated", today)
    text = append_to_section(text, SECTION_MAP["evidence"], f"- {today}：实现证据：{args.evidence.strip()}")
    text = append_history(
        text,
        args.note or "创新点实现完成；卡片转移至“已实现”目录。",
        today,
    )
    path.write_text(text, encoding="utf-8")
    path.replace(destination)
    index = rebuild_index(directory)
    print(f"implemented={destination}")
    print(f"index={index}")
    return 0


def command_list(args: argparse.Namespace, directory: Path) -> int:
    count = 0
    for path, text in iter_cards(directory):
        metadata = parse_frontmatter(text)
        if args.status and metadata.get("status") != args.status:
            continue
        count += 1
        print(f"{metadata.get('id', path.stem)}\t{metadata.get('status', '')}\t{metadata.get('priority', '')}\t{metadata.get('title', path.stem)}")
    print(f"count={count}")
    return 0


def command_search(args: argparse.Namespace, directory: Path) -> int:
    query = args.query.lower()
    matches = []
    for path, text in iter_cards(directory):
        if query in text.lower():
            metadata = parse_frontmatter(text)
            matches.append((path, metadata))
    for path, metadata in matches:
        print(f"{metadata.get('id', path.stem)}\t{metadata.get('status', '')}\t{metadata.get('title', path.stem)}\t{path}")
    print(f"count={len(matches)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage ljh research research points.")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Create a confirmed research-point card.")
    add.add_argument("--title", required=True)
    add.add_argument("--status", choices=INITIAL_STATUSES, default="draft")
    add.add_argument("--slug", help="Optional ASCII file-name short name; the stable ID remains canonical.")
    add.add_argument("--priority", choices=VALID_PRIORITIES, default="中")
    add.add_argument("--tags", default="")
    add.add_argument("--gap")
    add.add_argument("--hypothesis")
    add.add_argument("--innovation")
    add.add_argument("--impact")
    add.add_argument("--implementation")
    add.add_argument("--validation")
    add.add_argument("--risks")
    add.add_argument("--evidence", action="append", default=[])

    refine = subparsers.add_parser("refine", help="Append evidence to one card section.")
    refine.add_argument("--id", required=True)
    refine.add_argument("--section", choices=tuple(SECTION_MAP), required=True)
    refine.add_argument("--text", required=True)
    refine.add_argument("--note")

    status = subparsers.add_parser("status", help="Change a card status and log the transition.")
    status.add_argument("--id", required=True)
    status.add_argument("--status", choices=VALID_STATUSES, required=True)
    status.add_argument("--note")

    framework = subparsers.add_parser(
        "framework", help="Record a framework-adoption decision after user-approved documentation changes."
    )
    framework.add_argument("--id", required=True)
    framework.add_argument("--decision", choices=("pending_decision", "adopted", "deferred", "superseded"), required=True)
    framework.add_argument("--framework-version")
    framework.add_argument("--framework-link")
    framework.add_argument("--successor")
    framework.add_argument("--note")

    implement = subparsers.add_parser(
        "implement",
        help="Record implementation evidence and move a card to 已实现.",
    )
    implement.add_argument("--id", required=True)
    implement.add_argument("--evidence", required=True)
    implement.add_argument("--note")

    listing = subparsers.add_parser("list", help="List research points.")
    listing.add_argument("--status", choices=VALID_STATUSES)

    search = subparsers.add_parser("search", help="Search all card content.")
    search.add_argument("--query", required=True)

    subparsers.add_parser("reindex", help="Rebuild README.md from card metadata.")
    return parser


def main() -> int:
    configure_utf8()
    args = build_parser().parse_args()
    project_root = resolve_project_root(args.project_root)
    require_owned_workspace(project_root)
    directory = points_dir(project_root)
    if args.command == "add":
        return command_add(args, directory)
    if args.command == "refine":
        return command_refine(args, directory)
    if args.command == "status":
        return command_status(args, directory)
    if args.command == "implement":
        return command_implement(args, directory)
    if args.command == "framework":
        return command_framework(args, directory)
    if args.command == "list":
        return command_list(args, directory)
    if args.command == "search":
        return command_search(args, directory)
    index = rebuild_index(directory)
    print(f"updated={index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
