#!/usr/bin/env python3
"""Create, refine, index, and search ljh research reproduction cards (4复现)."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from ljh_research.knowledge.card_schema import STATUSES, card_filename, next_identifier
from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import build_reproduction_index, require_owned_workspace, resolve_project_root
from ljh_research.knowledge.project_conventions import load as load_conventions
from ljh_research.knowledge.template_loader import render_template
from ljh_research.knowledge.layout import REPRODUCTIONS_DIR, research_root

def read_profile(project_root: Path) -> dict:
    try:
        return load_conventions(project_root)
    except ValueError as exc:
        raise SystemExit(f"needs_configuration: {exc}") from exc


VALID_STATUSES = STATUSES["reproduction"]
MAX_ROUNDS = 10
DEFAULT_TOLERANCE = 0.02
SECTION_MAP = {
    "source": "论文与来源",
    "placement": "复现落位",
    "protocol": "数据与评估协议",
    "paper_metrics": "对齐指标与论文值",
    "rounds": "轮次记录",
    "conclusion": "结论",
}

METRIC_PAIR_RE = re.compile(r"^([^=;]+)=(-?\d+(?:\.\d+)?)$")
ROUND_ENTRY_RE = re.compile(r"^- 第 (\d+) 轮（", re.MULTILINE)


def reproduction_dir(project_root: Path) -> Path:
    return research_root(project_root) / REPRODUCTIONS_DIR


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
        raise SystemExit("Reproduction card has invalid frontmatter")
    return text[:end] + f"\n{key}: {value}" + text[end:]


def parse_metric_pairs(value: str) -> dict[str, float]:
    pairs: dict[str, float] = {}
    for part in value.split(";"):
        part = part.strip()
        if not part:
            continue
        match = METRIC_PAIR_RE.match(part)
        if not match:
            raise ValueError(f"invalid metric pair: {part!r} (expected Metric=value)")
        name = match.group(1).strip()
        if name in pairs:
            raise ValueError(f"duplicate metric: {name}")
        pairs[name] = float(match.group(2))
    if not pairs:
        raise ValueError("no metric pairs given")
    return pairs


def format_pairs(pairs: dict[str, float]) -> str:
    return ";".join(f"{name}={value}" for name, value in pairs.items())


def iter_cards(directory: Path):
    if not directory.exists():
        return
    for path in sorted(directory.rglob("REPRO-*.md")):
        yield path, path.read_text(encoding="utf-8")


def next_id(directory: Path) -> str:
    return next_identifier(directory, "REPRO")


def find_card(directory: Path, rep_id: str) -> tuple[Path, str]:
    normalized_id = rep_id.upper()
    matches = list(directory.rglob(f"{normalized_id}-*.md"))
    if len(matches) != 1:
        raise SystemExit(f"Expected one card for {normalized_id}, found {len(matches)}")
    return matches[0], matches[0].read_text(encoding="utf-8")


def _markdown_headings(text: str) -> list[tuple[int, int, int, str]]:
    headings = []
    offset = 0
    fence = None
    for line in text.splitlines(keepends=True):
        start = offset
        offset += len(line)
        body = line.rstrip("\r\n")
        fence_match = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", body)
        if fence is not None:
            if (fence_match and fence_match.group(1)[0] == fence[0]
                    and len(fence_match.group(1)) >= fence[1]
                    and not fence_match.group(2).strip()):
                fence = None
            continue
        if fence_match:
            fence = (fence_match.group(1)[0], len(fence_match.group(1)))
            continue
        match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*))?", body)
        if match:
            title = re.sub(r"(?:[ \t]+|^)#+[ \t]*$", "", match.group(2) or "").strip()
            headings.append((start, offset, len(match.group(1)), title))
    return headings


def _section_bounds(text: str, heading: str) -> tuple[int, int] | None:
    headings = _markdown_headings(text)
    for index, (_, start, level, title) in enumerate(headings):
        if title == heading:
            end = next((position for position, _, depth, _ in headings[index + 1:]
                        if depth <= level), len(text))
            return start, end
    return None


def append_to_section(text: str, heading: str, content: str) -> str:
    addition = content.strip()
    bounds = _section_bounds(text, heading)
    if bounds is None:
        block = f"## {heading}\n\n{addition}\n\n"
        history = next((position for position, _, level, title in _markdown_headings(text)
                        if level == 2 and title == "迭代历史"), None)
        if history is not None:
            return text[:history] + block + text[history:]
        return text.rstrip() + "\n\n" + block
    start, end = bounds
    current = text[start:end].rstrip()
    updated = current + "\n\n" + addition + "\n\n" if current else "\n" + addition + "\n\n"
    return text[:start] + updated + text[end:]


def replace_section(text: str, heading: str, content: str) -> str:
    bounds = _section_bounds(text, heading)
    if bounds is None:
        raise SystemExit(f"Section not found: {heading}")
    start, end = bounds
    return text[:start] + f"\n{content.strip()}\n\n" + text[end:]


def append_history(text: str, message: str, today: str) -> str:
    return append_to_section(text, "迭代历史", f"- {today}：{message}")


def next_round_number(text: str) -> int:
    numbers = [int(number) for number in ROUND_ENTRY_RE.findall(text)]
    return (max(numbers) + 1) if numbers else 1


def render_index(directory: Path) -> str:
    rows = []
    for path, text in iter_cards(directory):
        metadata = parse_frontmatter(text)
        title = metadata.get("title", path.stem)
        rows.append(
            "| {id} | [{title}]({file}) | {method} | {status} | {dataset} | {updated} | {tags} |".format(
                id=metadata.get("id", ""),
                title=title.replace("|", "\\|"),
                file=path.relative_to(directory).as_posix(),
                method=metadata.get("method", ""),
                status=metadata.get("status", "planned"),
                dataset=metadata.get("dataset", ""),
                updated=metadata.get("updated", ""),
                tags=metadata.get("tags", ""),
            )
        )
    base = build_reproduction_index().rstrip()
    return base + ("\n" + "\n".join(rows) if rows else "") + "\n"


def rebuild_index(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / "README.md"
    index.write_text(render_index(directory), encoding="utf-8")
    return index


def card_body(
    args: argparse.Namespace,
    rep_id: str,
    today: str,
    paper_metrics: dict[str, float],
    profile: dict,
) -> str:
    tags = ", ".join(dict.fromkeys(tag.strip() for tag in args.tags.split(",") if tag.strip()))
    metric_list = format_pairs(paper_metrics)
    alignment = ",".join(paper_metrics)
    topic = (args.topic_root_relative or "").strip() or "待补充"
    repo = (args.repo_url or "").strip() or "未公布官方代码（按论文自行实现）"
    return render_template(
        "cards/reproduction.md",
        ID=rep_id,
        PAPER_ID="null",
        TITLE=args.title.strip(),
        METHOD=args.method.strip(),
        STATUS=args.status,
        DATASET=args.dataset.strip(),
        ALIGNMENT_METRICS=alignment,
        PAPER_METRICS=metric_list,
        TOLERANCE=args.tolerance,
        REPO_URL=repo,
        CREATED=today,
        UPDATED=today,
        TAGS=tags,
        TOPIC=topic,
        MODELS_DIR=profile.get("models_dir") or "未配置",
        CONFIGS_DIR=profile.get("configs_dir") or "未配置",
        EXPERIMENTS_DIR=profile.get("experiments_dir") or "未配置",
    )


def command_add(args: argparse.Namespace, directory: Path) -> int:
    project_root = resolve_project_root(args.project_root)
    profile = read_profile(project_root)
    normalized = normalize_title(args.title)
    for path, text in iter_cards(directory):
        if normalize_title(parse_frontmatter(text).get("title", path.stem)) == normalized:
            print("exists=true")
            print(f"card={path}")
            return 0
    try:
        paper_metrics = parse_metric_pairs(args.paper_metrics)
    except ValueError as exc:
        raise SystemExit(f"paper-metrics: {exc}")
    if args.tolerance <= 0:
        raise SystemExit("tolerance must be positive")
    rep_id = next_id(directory)
    today = date.today().isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / card_filename(rep_id, args.slug or args.method, fallback="reproduction")
    path.write_text(card_body(args, rep_id, today, paper_metrics, profile), encoding="utf-8")
    index = rebuild_index(directory)
    print("created=true")
    print(f"id={rep_id}")
    print(f"card={path}")
    print(f"index={index}")
    return 0


def command_refine(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    if args.section == "paper_metrics":
        try:
            paper_metrics = parse_metric_pairs(args.text)
        except ValueError as exc:
            raise SystemExit(f"paper-metrics: {exc}")
        metric_list = format_pairs(paper_metrics)
        alignment = ",".join(paper_metrics)
        text = replace_section(text, SECTION_MAP["paper_metrics"], metric_list)
        text = replace_metadata(text, "paper_metrics", metric_list)
        text = replace_metadata(text, "alignment_metrics", alignment)
        text = replace_metadata(text, "updated", today)
        text = append_history(text, args.note or "更新对齐指标与论文值。", today)
        path.write_text(text, encoding="utf-8")
        rebuild_index(directory)
        print("paper_metrics_updated=true")
    else:
        entry = f"- {today}：{args.text.strip()}"
        text = append_to_section(text, SECTION_MAP[args.section], entry)
        text = replace_metadata(text, "updated", today)
        text = append_history(text, args.note or f"补充“{SECTION_MAP[args.section]}”内容。", today)
        path.write_text(text, encoding="utf-8")
        rebuild_index(directory)
    print(f"updated={path}")
    return 0


def command_round(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    metadata = parse_frontmatter(text)
    if metadata.get("status") == "reproduced":
        raise SystemExit(f"Reproduction {args.id.upper()} is already aligned; no more rounds allowed")
    try:
        paper_metrics = parse_metric_pairs(metadata.get("paper_metrics", ""))
        measured = parse_metric_pairs(args.metrics)
    except ValueError as exc:
        raise SystemExit(f"metrics: {exc}")
    missing = [name for name in paper_metrics if name not in measured]
    if missing:
        raise SystemExit(f"round metrics missing alignment metrics: {', '.join(missing)}")
    extra = [name for name in measured if name not in paper_metrics]
    if extra:
        raise SystemExit(f"round metrics not in paper_metrics: {', '.join(extra)}")
    round_no = next_round_number(text)
    if round_no > MAX_ROUNDS:
        raise SystemExit(f"round cap reached: max {MAX_ROUNDS} rounds")
    try:
        tolerance = float(metadata.get("tolerance", DEFAULT_TOLERANCE))
    except ValueError:
        tolerance = DEFAULT_TOLERANCE
    deviations: dict[str, float] = {}
    for name, paper_value in paper_metrics.items():
        measured_value = measured[name]
        if paper_value == 0:
            deviation = 0.0 if measured_value == 0 else float("inf")
        else:
            deviation = abs(measured_value - paper_value) / abs(paper_value)
        deviations[name] = deviation
    aligned = all(deviation <= tolerance for deviation in deviations.values())
    today = date.today().isoformat()
    meas_str = ";".join(f"{name}={measured[name]}" for name in paper_metrics)
    dev_str = ";".join(f"{name}={deviations[name]:.4f}" for name in paper_metrics)
    action = (args.action or "").strip() or "未记录修改内容"
    log = (args.log or "").strip() or "-"
    entry = f"- 第 {round_no} 轮（{today}）：measured={meas_str}；deviation={dev_str}；log={log}；action={action}。"
    text = append_to_section(text, SECTION_MAP["rounds"], entry)
    text = replace_metadata(text, "updated", today)
    if aligned:
        old_status = metadata.get("status", "running")
        text = replace_metadata(text, "status", "reproduced")
        text = append_history(text, args.note or f"第 {round_no} 轮全部对齐指标达标，状态由“{old_status}”变更为“reproduced”。", today)
    elif round_no >= MAX_ROUNDS:
        old_status = metadata.get("status", "running")
        text = replace_metadata(text, "status", "partial")
        text = append_history(text, args.note or f"第 {round_no} 轮仍未达标（达 10 轮上限），状态由“{old_status}”变更为“partial”。", today)
    else:
        text = append_history(text, args.note or f"记录第 {round_no} 轮结果（未达标，继续循环）。", today)
    path.write_text(text, encoding="utf-8")
    rebuild_index(directory)
    final_status = parse_frontmatter(path.read_text(encoding="utf-8")).get("status", "")
    print(f"round={round_no}")
    print(f"measured={meas_str}")
    print(f"deviation={dev_str}")
    print(f"aligned={'true' if aligned else 'false'}")
    print(f"status={final_status}")
    if not aligned and round_no >= MAX_ROUNDS:
        print("round_cap_reached=true")
    return 0


def command_status(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    old_status = parse_frontmatter(text).get("status", "planned")
    text = replace_metadata(text, "status", args.status)
    text = replace_metadata(text, "updated", today)
    text = append_history(text, args.note or f"状态由“{old_status}”变更为“{args.status}”。", today)
    path.write_text(text, encoding="utf-8")
    rebuild_index(directory)
    print(f"updated={path}")
    return 0


def command_conclude(args: argparse.Namespace, directory: Path) -> int:
    path, text = find_card(directory, args.id)
    today = date.today().isoformat()
    text = append_to_section(text, SECTION_MAP["conclusion"], f"- {today}：{args.conclusion.strip()}")
    text = replace_metadata(text, "updated", today)
    text = append_history(text, "记录复现结论。", today)
    path.write_text(text, encoding="utf-8")
    rebuild_index(directory)
    print(f"updated={path}")
    return 0


def command_list(args: argparse.Namespace, directory: Path) -> int:
    count = 0
    for path, text in iter_cards(directory):
        metadata = parse_frontmatter(text)
        if args.status and metadata.get("status") != args.status:
            continue
        count += 1
        print(
            "{id}\t{status}\t{dataset}\t{title}".format(
                id=metadata.get("id", path.stem),
                status=metadata.get("status", ""),
                dataset=metadata.get("dataset", ""),
                title=metadata.get("title", path.stem),
            )
        )
    print(f"count={count}")
    return 0


def command_search(args: argparse.Namespace, directory: Path) -> int:
    query = args.query.lower()
    matches = []
    for path, text in iter_cards(directory):
        if query in text.lower():
            matches.append((path, parse_frontmatter(text)))
    for path, metadata in matches:
        print(
            "{id}\t{status}\t{title}\t{path}".format(
                id=metadata.get("id", path.stem),
                status=metadata.get("status", ""),
                title=metadata.get("title", path.stem),
                path=path,
            )
        )
    print(f"count={len(matches)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage ljh research reproduction cards (4复现).")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Create a paper reproduction card.")
    add.add_argument("--title", required=True)
    add.add_argument("--method", required=True)
    add.add_argument("--topic-root-relative", help="0知识库/<domain>/<topic>")
    add.add_argument("--repo-url", default="")
    add.add_argument("--dataset", required=True)
    add.add_argument(
        "--paper-metrics",
        required=True,
        help='Metric=value pairs separated by ";" (e.g. "Recall@20=0.1025;NDCG@20=0.0447")',
    )
    add.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    add.add_argument("--status", choices=VALID_STATUSES, default="planned")
    add.add_argument("--slug", help="Optional ASCII filename slug; ID remains canonical.")
    add.add_argument("--tags", default="")

    refine = subparsers.add_parser(
        "refine",
        help="Append to a card section; paper_metrics replaces the section and syncs frontmatter.",
    )
    refine.add_argument("--id", required=True)
    refine.add_argument("--section", choices=tuple(SECTION_MAP), required=True)
    refine.add_argument("--text", required=True)
    refine.add_argument("--note")

    status = subparsers.add_parser("status", help="Change a card status and log the transition.")
    status.add_argument("--id", required=True)
    status.add_argument("--status", choices=VALID_STATUSES, required=True)
    status.add_argument("--note")

    conclude = subparsers.add_parser("conclude", help="Record the reproduction conclusion without changing status.")
    conclude.add_argument("--id", required=True)
    conclude.add_argument("--conclusion", required=True)

    round_cmd = subparsers.add_parser("round", help="Record one metric-alignment round and auto-judge the verdict.")
    round_cmd.add_argument("--id", required=True)
    round_cmd.add_argument("--metrics", required=True)
    round_cmd.add_argument("--log", default="")
    round_cmd.add_argument("--action", default="")
    round_cmd.add_argument("--note")

    listing = subparsers.add_parser("list", help="List reproduction cards.")
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
    directory = reproduction_dir(project_root)
    if args.command == "add":
        return command_add(args, directory)
    if args.command == "refine":
        return command_refine(args, directory)
    if args.command == "status":
        return command_status(args, directory)
    if args.command == "conclude":
        return command_conclude(args, directory)
    if args.command == "round":
        return command_round(args, directory)
    if args.command == "list":
        return command_list(args, directory)
    if args.command == "search":
        return command_search(args, directory)
    index = rebuild_index(directory)
    print(f"updated={index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
