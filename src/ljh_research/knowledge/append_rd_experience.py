#!/usr/bin/env python3
"""Append an R&D experience entry to ljh research docs/03研发经验.md."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import require_owned_workspace, resolve_project_root
from ljh_research.knowledge.layout import EXPERIENCE_FILE, research_root
from ljh_research.knowledge.template_loader import render_template


def build_entry(args: argparse.Namespace) -> str:
    lines = []
    if args.topic:
        lines.extend([f"#### {args.topic}", ""])
    lines.append(f"- 背景：{args.background or '记录研发过程中的重要经验。'}")
    if args.problem:
        lines.append(f"- 问题：{args.problem}")
    lines.append(f"- 观察：{args.text}")
    if args.action:
        lines.append(f"- 决策/行动：{args.action}")
    if args.result:
        lines.append(f"- 结果：{args.result}")
    lines.append(f"- 结论：{args.conclusion or args.text}")
    lines.append(f"- 后续：{args.follow_up or '在后续实验或方案调整时补充验证条件与反例。'}")
    return "\n".join(lines).rstrip() + "\n"


def ensure_experience_file(path: Path, today: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_template("root/03研发经验.md", DATE=today), encoding="utf-8")


def insert_entry(text: str, entry_date: str, entry: str) -> str:
    records_heading = "## 经验记录"
    categories_heading = "## 可复用经验分类"
    if records_heading not in text:
        text = text.rstrip() + f"\n\n{records_heading}\n"
    records_start = text.index(records_heading)
    categories_start = text.find(categories_heading, records_start)
    if categories_start == -1:
        categories_start = len(text)
    before, records, after = text[:records_start], text[records_start:categories_start], text[categories_start:]
    date_heading = f"### {entry_date}"
    if date_heading not in records:
        records = records.rstrip() + f"\n\n{date_heading}\n\n{entry}\n"
    else:
        date_start = records.index(date_heading)
        next_date = records.find("\n### ", date_start + len(date_heading))
        insert_at = next_date if next_date != -1 else len(records)
        records = records[:insert_at].rstrip() + "\n\n" + entry + records[insert_at:]
    return before + records + after.lstrip("\n")


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description="Append an ljh research R&D experience entry.")
    parser.add_argument("--project-root", help="Project root path. Defaults to the current directory.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Entry date, YYYY-MM-DD.")
    parser.add_argument("--topic")
    parser.add_argument("--text", required=True)
    parser.add_argument("--background")
    parser.add_argument("--problem")
    parser.add_argument("--action")
    parser.add_argument("--result")
    parser.add_argument("--conclusion")
    parser.add_argument("--follow-up")
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    require_owned_workspace(project_root)
    import os
    if os.environ.get("LJH_RESEARCH_LEGACY_LAYOUT") != "1":
        from ljh_research.memory.repository import Memory, write
        import uuid
        temporary = research_root(project_root) / ".runtime/memory/inbox" / (uuid.uuid4().hex + ".md")
        write(temporary, (f"# {args.topic or '研发经验'}\n\n日期：{args.date}\n\n" + build_entry(args)).encode("utf-8"))
        try:
            result = Memory(project_root).import_object({"kind": "experience", "title": args.topic or "研发经验",
                "path": temporary.relative_to(project_root).as_posix(), "origin": "Authorized experience entry " + args.date})
            print(f"updated={project_root / result['record']}")
            print(f"experience_id={result['id']}")
            print(f"date={args.date}")
        finally:
            temporary.unlink(missing_ok=True)
        return 0
    experience_path = research_root(project_root) / EXPERIENCE_FILE
    ensure_experience_file(experience_path, args.date)
    text = experience_path.read_text(encoding="utf-8")
    experience_path.write_text(insert_entry(text, args.date, build_entry(args)), encoding="utf-8")
    print(f"updated={experience_path}")
    print(f"date={args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
