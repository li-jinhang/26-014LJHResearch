#!/usr/bin/env python3
"""Create, refine, index, and search ljh research experiment cards (3实验)."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import build_experiment_index, require_owned_workspace, resolve_project_root
from ljh_research.knowledge.card_schema import STATUSES, card_filename, next_identifier
from ljh_research.knowledge.template_loader import render_template
from ljh_research.knowledge.layout import EXPERIMENTS_DIR, research_root


VALID_STATUSES = STATUSES["experiment"]
VALID_PRIORITIES = ("高", "中", "低")
SECTION_MAP = {
    "objective": "实验目的与研究问题",
    "hypothesis": "核心假设",
    "subjects": "三类比对对象",
    "protocol": "数据与评估协议",
    "metrics": "指标定义",
    "visuals": "可视化方案",
    "implementation": "实现边界与产物",
    "expected": "预期结果与合理性基线",
    "conclusion": "实验结论",
    "risks": "风险、反例与停止条件",
    "evidence": "证据",
}
CARD_KINDS = {
    "experiment": {
        "id_prefix": "EXP",
        "template": "cards/experiment.md",
        "type": "experiment",
        "label": "正式实验",
    },
    "micro": {
        "id_prefix": "MEXP",
        "template": "cards/micro-experiment.md",
        "type": "micro_experiment",
        "label": "微实验",
    },
}


def experiments_dir(project_root: Path) -> Path:
    return research_root(project_root) / EXPERIMENTS_DIR


def normalize_title(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value, flags=re.UNICODE).lower()


def normalize_research_points(values: list[str]) -> list[str]:
    """Return unique, stable RP IDs for machine-readable EXP -> RP routing."""
    normalized: list[str] = []
    for value in values:
        point_id = value.strip().upper()
        if not re.fullmatch(r"RP-\d{4,}", point_id):
            raise SystemExit(f"Invalid research point id: {value}")
        if point_id not in normalized:
            normalized.append(point_id)
    return normalized


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
        raise SystemExit("Experiment card has invalid frontmatter")
    return text[:end] + f"\n{key}: {value}" + text[end:]


CARD_PATTERNS = ("EXP-*.md", "PRE-*.md", "MEXP-*.md")


def iter_cards(directory: Path):
    if not directory.exists():
        return
    for pattern in CARD_PATTERNS:
        for path in sorted(directory.rglob(pattern)):
            yield path, path.read_text(encoding="utf-8")


def next_id(directory: Path, kind: str) -> str:
    prefix = CARD_KINDS[kind]["id_prefix"]
    return next_identifier(directory, prefix)


def find_card(directory: Path, card_id: str) -> tuple[Path, str]:
    normalized_id = card_id.upper()
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
                "| {id} | {category} | [{title}]({file}) | {status} | {priority} | {updated} | {tags} |".format(
                id=metadata.get("id", path.stem.split("-", 2)[:2]),
                category="微实验" if metadata.get("type") == "micro_experiment" else "正式实验",
                title=title.replace("|", "\\|"),
                file=path.relative_to(directory).as_posix(),
                status=metadata.get("status", "planned"),
                priority=metadata.get("priority", "中"),
                updated=metadata.get("updated", ""),
                tags=metadata.get("tags", ""),
            )
        )
    base = build_experiment_index().rstrip()
    return base + ("\n" + "\n".join(rows) if rows else "") + "\n"


def rebuild_index(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / "README.md"
    index.write_text(render_index(directory), encoding="utf-8")
    return index


def card_body(args: argparse.Namespace, card_id: str, today: str) -> str:
    kind = getattr(args, "kind", "experiment")
    card = CARD_KINDS[kind]
    tags = ", ".join(dict.fromkeys(tag.strip() for tag in args.tags.split(",") if tag.strip()))
    if kind == "micro" and "micro" not in {tag.strip() for tag in tags.split(",")}:
        tags = f"micro, {tags}" if tags else "micro"
    evidence = "\n".join(f"- {item}" for item in args.evidence) or "- 待补充可核查的代码、数据或日志证据。"
    research_points = normalize_research_points(args.research_point)
    if kind == "micro":
        relations = "\n".join(f"- 线索关联研究点：`{point_id}`（不作为验证证据）" for point_id in research_points) or "- 暂不关联研究点。"
    else:
        relations = "\n".join(f"- 验证研究点：`{point_id}`" for point_id in research_points) or "- 待关联研究点。"
    common = dict(
        ID=card_id,
        TITLE=args.title.strip(),
        STATUS=args.status,
        PRIORITY=args.priority,
        CREATED=today,
        UPDATED=today,
        TAGS=tags,
        RESEARCH_POINTS=json.dumps(research_points, ensure_ascii=False),
        RESEARCH_POINT_RELATIONS=relations,
        EVIDENCE=evidence,
    )
    if kind == "micro":
        return render_template(
            card["template"],
            **common,
            OBJECTIVE=args.objective or "待补充。",
            HYPOTHESIS=args.hypothesis or "待补充。",
            METHOD=args.protocol or args.implementation or "待补充。",
            RESULT=args.expected or "待补充。",
            CONCLUSION="待实验执行后补充。",
            RISKS=args.risks or "待补充。",
        )
    return render_template(
        card["template"],
        **common,
        OBJECTIVE=args.objective or "待补充。",
        HYPOTHESIS=args.hypothesis or "待补充。",
        SUBJECTS=args.subjects or "待补充。",
        PROTOCOL=args.protocol or "待补充。",
        METRICS=args.metrics or "待补充。",
        VISUALS=args.visuals or "待补充。",
        IMPLEMENTATION=args.implementation or "待补充。",
        EXPECTED=args.expected or "待补充。不得把预测数值写成已经实现的结果。",
        RISKS=args.risks or "待补充。",
    )


def preview_lines(args: argparse.Namespace, directory: Path) -> list[str]:
    card_id = next_id(directory, getattr(args, "kind", "experiment"))
    today = date.today().isoformat()
    kind = CARD_KINDS[getattr(args, "kind", "experiment")]
    card_path = directory / card_filename(card_id, getattr(args, "slug", None) or args.title, fallback="experiment")
    research_points = normalize_research_points(args.research_point)
    fields = {
        "kind": kind["label"],
        "id": card_id,
        "title": args.title,
        "type": kind["type"],
        "status": args.status,
        "priority": args.priority,
        "tags": ", ".join(dict.fromkeys(tag.strip() for tag in args.tags.split(",") if tag.strip())),
        "card": card_path,
        "research_points": ", ".join(research_points) or "无",
    }
    lines = [f"{key}={value}" for key, value in fields.items()]
    sections = {
        "objective": args.objective or "待补充。",
        "hypothesis": args.hypothesis or "待补充。",
        "subjects": getattr(args, "subjects", None) or "待补充。",
        "protocol": args.protocol or "待补充。",
        "metrics": getattr(args, "metrics", None) or "待补充。",
        "visuals": getattr(args, "visuals", None) or "待补充。",
        "implementation": getattr(args, "implementation", None) or "待补充。",
        "expected": args.expected or "待补充。",
        "risks": args.risks or "待补充。",
        "evidence": ", ".join(args.evidence) or "待补充。",
    }
    lines.extend(f"section.{key}={value}" for key, value in sections.items())
    lines.append("action=写入前必须获得用户明确同意")
    return lines


def command_add(args: argparse.Namespace, directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    normalized = normalize_title(args.title)
    for path, text in iter_cards(directory):
        metadata = parse_frontmatter(text)
        if metadata.get("title", "").strip().lower() == args.title.strip().lower() or (
            path.stem and normalize_title(metadata.get("title", path.stem)) == normalized
        ):
            print(f"id={metadata.get('id', path.stem)} exists=true")
            return 0

    card_id = next_id(directory, args.kind)
    today = date.today().isoformat()
    card_path = directory / card_filename(card_id, args.slug or args.title, fallback="experiment")
    card_path.write_text(card_body(args, card_id, today), encoding="utf-8")
    index = rebuild_index(directory)
    print(f"id={card_id}")
    print(f"card={card_path}")
    print(f"index={index}")
    return 0


def command_refine(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    heading = SECTION_MAP[args.section]
    text = append_to_section(text, heading, args.text)
    text = replace_metadata(text, "updated", today)
    if args.note:
        text = append_history(text, args.note, today)
    path.write_text(text, encoding="utf-8")
    index = rebuild_index(directory)
    print(f"refined={path}")
    print(f"section={heading}")
    print(f"index={index}")
    return 0


def command_status(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    text = replace_metadata(text, "status", args.status)
    text = replace_metadata(text, "updated", today)
    text = append_history(text, args.note or f"状态更新为“{args.status}”。", today)
    path.write_text(text, encoding="utf-8")
    index = rebuild_index(directory)
    print(f"status={args.status}")
    print(f"card={path}")
    print(f"index={index}")
    return 0


def command_conclude(args: argparse.Namespace, directory: Path) -> int:
    # 默认只记录实验结论，不改变卡片状态；仅当用户明确同意（--mark-complete）
    # 时才把状态置为 ``completed``。
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    text = append_to_section(text, SECTION_MAP["conclusion"], f"- {today}：{args.conclusion.strip()}")
    mark_complete = bool(getattr(args, "mark_complete", False))
    if mark_complete:
        text = replace_metadata(text, "status", "completed")
        history = args.note or "实验结论已记录，经用户确认状态置为 completed。"
    else:
        history = args.note or "实验结论已记录，状态保持原状（未自动置为 completed）。"
    text = replace_metadata(text, "updated", today)
    text = append_history(text, history, today)
    path.write_text(text, encoding="utf-8")
    index = rebuild_index(directory)
    print(f"concluded={path}")
    print(f"status={'completed' if mark_complete else 'unchanged'}")
    print(f"index={index}")
    return 0


def command_list(args: argparse.Namespace, directory: Path) -> int:
    count = 0
    for path, text in iter_cards(directory):
        metadata = parse_frontmatter(text)
        if args.kind == "micro" and metadata.get("type") != "micro_experiment":
            continue
        if args.kind == "experiment" and metadata.get("type") == "micro_experiment":
            continue
        if args.status and metadata.get("status") != args.status:
            continue
        count += 1
        print(f"{metadata.get('id', path.stem)}\t{metadata.get('status', '')}\t{metadata.get('priority', '')}\t{metadata.get('title', path.stem)}")
    print(f"count={count}")
    return 0


def command_preview(args: argparse.Namespace, directory: Path) -> int:
    print("\n".join(preview_lines(args, directory)))
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
    parser = argparse.ArgumentParser(description="Manage ljh research experiment cards (3实验).")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Create a user-confirmed experiment-plan card.")
    add.add_argument("--kind", choices=("experiment", "micro"), default="experiment")
    add.add_argument("--title", required=True)
    add.add_argument("--status", choices=VALID_STATUSES, default="planned")
    add.add_argument("--slug", help="Optional ASCII file-name short name; the stable ID remains canonical.")
    add.add_argument("--priority", choices=VALID_PRIORITIES, default="中")
    add.add_argument("--tags", default="")
    add.add_argument("--objective")
    add.add_argument("--hypothesis")
    add.add_argument("--subjects")
    add.add_argument("--protocol")
    add.add_argument("--metrics")
    add.add_argument("--visuals")
    add.add_argument("--implementation")
    add.add_argument("--expected")
    add.add_argument("--risks")
    add.add_argument("--evidence", action="append", default=[])
    add.add_argument("--research-point", action="append", default=[], help="Related RP-NNN; repeat for multiple points.")

    preview = subparsers.add_parser("preview", help="Show the card that add would create without writing files.")
    preview.add_argument("--kind", choices=("experiment", "micro"), default="experiment")
    preview.add_argument("--title", required=True)
    preview.add_argument("--status", choices=VALID_STATUSES, default="planned")
    preview.add_argument("--priority", choices=VALID_PRIORITIES, default="中")
    preview.add_argument("--tags", default="")
    preview.add_argument("--objective")
    preview.add_argument("--hypothesis")
    preview.add_argument("--subjects")
    preview.add_argument("--protocol")
    preview.add_argument("--metrics")
    preview.add_argument("--visuals")
    preview.add_argument("--implementation")
    preview.add_argument("--expected")
    preview.add_argument("--risks")
    preview.add_argument("--evidence", action="append", default=[])
    preview.add_argument("--research-point", action="append", default=[], help="Related RP-NNN; repeat for multiple points.")

    refine = subparsers.add_parser("refine", help="Append content to one card section.")
    refine.add_argument("--id", required=True)
    refine.add_argument("--section", choices=tuple(SECTION_MAP), required=True)
    refine.add_argument("--text", required=True)
    refine.add_argument("--note")

    status = subparsers.add_parser("status", help="Change a card status and log the transition.")
    status.add_argument("--id", required=True)
    status.add_argument("--status", choices=VALID_STATUSES, required=True)
    status.add_argument("--note")

    conclude = subparsers.add_parser(
        "conclude", help="Record the experiment conclusion; set completed only with --mark-complete."
    )
    conclude.add_argument("--id", required=True)
    conclude.add_argument("--conclusion", required=True)
    conclude.add_argument("--note")
    conclude.add_argument(
        "--mark-complete", action="store_true",
        help="User-approved: also set the card status to completed.",
    )

    listing = subparsers.add_parser("list", help="List experiment cards.")
    listing.add_argument("--status", choices=VALID_STATUSES)
    listing.add_argument("--kind", choices=("experiment", "micro"), default="experiment")

    search = subparsers.add_parser("search", help="Search all card content.")
    search.add_argument("--query", required=True)

    subparsers.add_parser("reindex", help="Rebuild README.md from card metadata.")
    return parser


def main() -> int:
    configure_utf8()
    args = build_parser().parse_args()
    project_root = resolve_project_root(args.project_root)
    require_owned_workspace(project_root)
    directory = experiments_dir(project_root)
    if args.command == "add":
        return command_add(args, directory)
    if args.command == "preview":
        return command_preview(args, directory)
    if args.command == "refine":
        return command_refine(args, directory)
    if args.command == "status":
        return command_status(args, directory)
    if args.command == "conclude":
        return command_conclude(args, directory)
    if args.command == "list":
        return command_list(args, directory)
    if args.command == "search":
        return command_search(args, directory)
    index = rebuild_index(directory)
    print(f"updated={index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
