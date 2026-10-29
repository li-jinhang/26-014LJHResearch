#!/usr/bin/env python3
"""Generate evidence-backed research-direction drafts from the project's own memory.

候选方向来自项目自身信息（不内置领域主题包）：
- 2研究点中的「草案」卡片（未实现的潜在方向）；
- 03研发经验.md 中每条经验的「后续」动作；
- 02框架信息.md「风险与开放问题」中的待验证假设/待补充资源；
- 知识库论文笔记「05-对本项目的启发」章节中的启发条目。

脚本只做：提取候选 + 在本地语料中检索证据 + 评分排序。
不写入任何文件；输出为对话草案，用户确认后才落卡。
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ljh_research.workspace_contract import parse_frontmatter, resolve_project_root
from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.profile_config import resolve_project_relative
from ljh_research.knowledge.project_conventions import load as load_conventions
from ljh_research.knowledge.layout import (
    CONSTRAINTS_FILE,
    EXPERIENCE_FILE,
    FRAMEWORK_FILE,
    KNOWLEDGE_DIR,
    PAPERS_DIR,
    RESEARCH_DIR,
    RESEARCH_POINTS_DIR,
    research_root,
)

MAX_FILE_BYTES = 2_000_000
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".txt", ".log", ".json"}

# 研究点卡片的 draft 状态；「已实现/」下的卡片即使仍是 draft，也不重复生成方向。
RESEARCH_POINT_DIR = RESEARCH_POINTS_DIR
IMPLEMENTED_SUBDIR = "已实现"
DRAFT_STATUS = "draft"

# 候选方向来源类型 → 基础评分（novelty, expected_gain, feasibility）
SOURCE_BASE_SCORES = {
    "research_point": (5, 4, 3),   # 研究点草案：高创新、高预期、实现可行性待验证
    "experience_followup": (3, 4, 4),  # 经验后续：已有失败教训，实现可行性较高
    "open_question": (3, 3, 4),    # 开放问题：框架内已提出的待验证问题
    "paper_inspiration": (4, 3, 3),  # 论文启发：来自文献，创新较高但实现未知
}

MAX_KEYWORDS_PER_CANDIDATE = 12


@dataclass(frozen=True)
class Candidate:
    title: str
    gap: str
    innovation: str
    mechanism: str
    implementation: str
    validation: str
    risks: str
    keywords: tuple[str, ...]
    source_path: str
    source_line: int
    source_kind: str
    novelty: int
    expected_gain: int
    feasibility: int


def read_profile(project_root: Path) -> dict:
    try:
        return load_conventions(project_root)
    except ValueError as exc:
        raise SystemExit(f"needs_configuration: {exc}") from exc


def source_category(relative: Path) -> str:
    text = relative.as_posix().lower()
    if text.endswith(EXPERIENCE_FILE) or "/results/" in f"/{text}":
        return "experience"
    if text.startswith(f"{RESEARCH_DIR}/"):
        return "rag"
    return "code"


def iter_source_files(project_root: Path, profile: dict):
    explicit = [
        project_root / "README.md",
        research_root(project_root) / CONSTRAINTS_FILE,
        research_root(project_root) / FRAMEWORK_FILE,
        research_root(project_root) / EXPERIENCE_FILE,
    ]
    yielded: set[Path] = set()
    for path in explicit:
        if path.is_file():
            yielded.add(path.resolve())
            yield path
    roots = []
    for key in ("models_dir", "configs_dir", "experiments_dir"):
        rel = profile.get(key)
        if rel:
            roots.append(resolve_project_relative(project_root, rel, key=key))
    for index, rel in enumerate(profile.get("code_roots") or []):
        roots.append(resolve_project_relative(project_root, rel, key=f"code_roots[{index}]"))
    roots.extend(
        [
            research_root(project_root) / KNOWLEDGE_DIR,
            research_root(project_root) / PAPERS_DIR,
            research_root(project_root) / RESEARCH_POINT_DIR,
            project_root / "results",
        ]
    )
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if "源文件库" in path.parts or "__pycache__" in path.parts:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                resolved = path.resolve()
            except OSError:
                continue
            if resolved not in yielded:
                yielded.add(resolved)
                yield path


def load_corpus(project_root: Path, profile: dict) -> list[tuple[Path, list[str], str]]:
    corpus = []
    for path in iter_source_files(project_root, profile):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        relative = path.relative_to(project_root)
        corpus.append((relative, lines, source_category(relative)))
    return corpus


# ---------------------------------------------------------------- 候选提取


def extract_keywords(*texts: str) -> tuple[str, ...]:
    """Extract a small keyword set from candidate texts for evidence search.

    Keeps English tokens (>=3 chars) and short Chinese substrings (4 chars)
    to stay language-neutral while limiting keyword count.
    """
    joined = " ".join(texts).lower()
    words: set[str] = set()
    for token in re.findall(r"[a-z][a-z0-9_\-]{2,}", joined):
        words.add(token)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", joined):
        if len(chunk) <= 4:
            words.add(chunk)
        else:
            for i in range(len(chunk) - 3):
                words.add(chunk[i : i + 4])
    return tuple(sorted(words))[:MAX_KEYWORDS_PER_CANDIDATE]


def _first_line_after(path: Path, lines: list[str], heading_patterns: tuple[str, ...]) -> str:
    """Return the first non-empty content line after one of the given headings."""
    for idx, line in enumerate(lines):
        if any(pattern in line for pattern in heading_patterns):
            for following in lines[idx + 1 :]:
                stripped = following.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("|"):
                    return stripped[:200]
            break
    return ""


def extract_research_point_candidates(project_root: Path) -> list[Candidate]:
    """草案状态的研究点卡片 → 候选方向。"""
    research_dir = research_root(project_root) / RESEARCH_POINT_DIR
    if not research_dir.is_dir():
        return []
    candidates: list[Candidate] = []
    for path in sorted(research_dir.rglob("*.md")):
        if path.name == "README.md" or IMPLEMENTED_SUBDIR in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta = parse_frontmatter(text)
        if meta.get("status", "").strip() != DRAFT_STATUS:
            continue
        lines = text.splitlines()
        title = meta.get("title", path.stem).strip()
        gap = _first_line_after(
            path, lines, ("## 问题", "## 现有缺口", "## 背景", "## 核心假设", "## 动机")
        ) or title
        innovation = _first_line_after(
            path, lines, ("## 创新", "## 核心思路", "## 方法", "## 总体思路")
        ) or title
        mechanism = _first_line_after(
            path, lines, ("## 预期指标机制", "## 预期机制", "## 机制")
        ) or ""
        implementation = _first_line_after(
            path, lines, ("## 最小实现边界", "## 实现边界", "## 实现")
        ) or ""
        validation = _first_line_after(
            path, lines, ("## 验证方案", "## 单变量验证", "## 实验设计")
        ) or ""
        risks = _first_line_after(
            path, lines, ("## 风险", "## 风险与停止条件", "## 停止条件")
        ) or ""
        base = SOURCE_BASE_SCORES["research_point"]
        candidates.append(
            Candidate(
                title=title,
                gap=gap,
                innovation=innovation,
                mechanism=mechanism,
                implementation=implementation,
                validation=validation,
                risks=risks,
                keywords=extract_keywords(title, gap, innovation, mechanism),
                source_path=str(path.relative_to(project_root)),
                source_line=1,
                source_kind="research_point",
                novelty=base[0],
                expected_gain=base[1],
                feasibility=base[2],
            )
        )
    return candidates


def extract_experience_followups(project_root: Path) -> list[Candidate]:
    """03研发经验.md 中每条经验的「后续」动作 → 候选方向。"""
    path = research_root(project_root) / EXPERIENCE_FILE
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    candidates: list[Candidate] = []
    current_date = ""
    current_problem = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("### "):
            current_date = stripped[4:].strip()
            continue
        if stripped.startswith("- 问题：") or stripped.startswith("- 背景："):
            current_problem = stripped.split("：", 1)[1][:200] if "：" in stripped else stripped
        if not stripped.startswith("- 后续："):
            continue
        followup = stripped.split("：", 1)[1].strip() if "：" in stripped else stripped
        if len(followup) < 8:
            continue
        title = f"{current_date} 经验后续：{followup[:40]}"
        base = SOURCE_BASE_SCORES["experience_followup"]
        candidates.append(
            Candidate(
                title=title,
                gap=current_problem or f"来自 {current_date} 研发经验记录",
                innovation=followup,
                mechanism="",
                implementation="",
                validation="",
                risks="",
                keywords=extract_keywords(followup, current_problem),
                source_path=str(path.relative_to(project_root)),
                source_line=idx + 1,
                source_kind="experience_followup",
                novelty=base[0],
                expected_gain=base[1],
                feasibility=base[2],
            )
        )
    return candidates


def extract_open_questions(project_root: Path) -> list[Candidate]:
    """02框架信息.md「风险与开放问题」中的待验证/待补充条目 → 候选方向。"""
    path = research_root(project_root) / FRAMEWORK_FILE
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    candidates: list[Candidate] = []
    in_risks_section = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            in_risks_section = "风险" in stripped and "开放" in stripped
            continue
        if not in_risks_section:
            continue
        if not (stripped.startswith("- 待验证") or stripped.startswith("- 需要补充") or stripped.startswith("- 风险：")):
            continue
        content = stripped
        if len(content) < 12:
            continue
        title = f"开放问题：{content[:40]}"
        base = SOURCE_BASE_SCORES["open_question"]
        candidates.append(
            Candidate(
                title=title,
                gap=content,
                innovation=content,
                mechanism="",
                implementation="",
                validation="",
                risks="",
                keywords=extract_keywords(content),
                source_path=str(path.relative_to(project_root)),
                source_line=idx + 1,
                source_kind="open_question",
                novelty=base[0],
                expected_gain=base[1],
                feasibility=base[2],
            )
        )
    return candidates


def extract_paper_inspirations(project_root: Path) -> list[Candidate]:
    """知识库论文笔记「05-对本项目的启发」章节的条目 → 候选方向。"""
    kb_root = research_root(project_root) / KNOWLEDGE_DIR
    if not kb_root.is_dir():
        return []
    candidates: list[Candidate] = []
    for path in sorted(kb_root.rglob("*.md")):
        if "05-" not in path.name and "启发" not in path.name:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        relative = path.relative_to(project_root)
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            content = stripped[2:].strip()
            if len(content) < 12 or content.startswith("["):
                continue
            base = SOURCE_BASE_SCORES["paper_inspiration"]
            candidates.append(
                Candidate(
                    title=f"文献启发：{content[:40]}",
                    gap=f"来自论文笔记 {relative} 的启发",
                    innovation=content,
                    mechanism="",
                    implementation="",
                    validation="",
                    risks="",
                    keywords=extract_keywords(content, path.stem),
                    source_path=str(relative),
                    source_line=idx + 1,
                    source_kind="paper_inspiration",
                    novelty=base[0],
                    expected_gain=base[1],
                    feasibility=base[2],
                )
            )
    return candidates


def collect_candidates(project_root: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    candidates.extend(extract_research_point_candidates(project_root))
    candidates.extend(extract_experience_followups(project_root))
    candidates.extend(extract_open_questions(project_root))
    candidates.extend(extract_paper_inspirations(project_root))
    return candidates


# ---------------------------------------------------------------- 证据与评分


def collect_evidence(keywords: tuple[str, ...], corpus: list[tuple[Path, list[str], str]], limit: int = 6):
    matches: list[dict[str, object]] = []
    used_files: set[Path] = set()
    for relative, lines, category in corpus:
        for number, line in enumerate(lines, start=1):
            lowered = line.lower()
            if not any(keyword in lowered for keyword in keywords):
                continue
            if relative in used_files:
                continue
            snippet = " ".join(line.strip().split())[:240]
            if snippet:
                matches.append(
                    {"path": relative.as_posix(), "line": number, "snippet": snippet, "category": category}
                )
                used_files.add(relative)
                break
        if len(matches) >= limit:
            break
    return matches


def score_candidate(candidate: Candidate, evidence: list[dict[str, object]]) -> dict[str, int | float]:
    categories = {item["category"] for item in evidence}
    evidence_strength = min(5, 2 + len(categories) + (1 if len(evidence) >= 4 else 0))
    total = round(
        candidate.novelty * 0.30
        + candidate.expected_gain * 0.30
        + evidence_strength * 0.20
        + candidate.feasibility * 0.20,
        2,
    )
    return {
        "innovation": candidate.novelty,
        "expected_gain": candidate.expected_gain,
        "evidence": evidence_strength,
        "feasibility": candidate.feasibility,
        "total": total,
    }


def generate(project_root: Path, query: str | None, limit: int, profile: dict) -> list[dict[str, object]]:
    corpus = load_corpus(project_root, profile)
    candidates = collect_candidates(project_root)
    query_terms = tuple(query.lower().split()) if query else ()
    results = []
    for candidate in candidates:
        searchable = " ".join((candidate.title, candidate.gap, candidate.innovation)).lower()
        if query_terms and not any(term in searchable for term in query_terms):
            continue
        evidence = collect_evidence(candidate.keywords, corpus)
        categories = {item["category"] for item in evidence}
        if len(evidence) < 2 or not ({"code", "rag"} & categories):
            continue
        scores = score_candidate(candidate, evidence)
        if scores["evidence"] < 3:
            continue
        results.append(
            {
                "title": candidate.title,
                "gap": candidate.gap,
                "innovation": candidate.innovation,
                "expected_mechanism": candidate.mechanism or "待根据本地证据补全。",
                "implementation": candidate.implementation or "待按 02「模型实现与工程约束」设计最小实现边界。",
                "validation": candidate.validation or "待按项目验证协议设计单变量验证。",
                "risks": candidate.risks or "待补充风险与停止条件。",
                "scores": scores,
                "evidence": evidence,
                "source": f"{candidate.source_path}:{candidate.source_line}",
                "source_kind": candidate.source_kind,
            }
        )
    results.sort(key=lambda item: (-float(item["scores"]["total"]), str(item["title"])))
    return results[:limit]


# ---------------------------------------------------------------- 输出


def render_markdown(project_root: Path, candidates: list[dict[str, object]]) -> str:
    lines = [
        "# 高研究价值方向候选草案",
        "",
        f"- 项目：`{project_root}`",
        "- 生成方式：从项目自身研究记忆（研究点草案、研发经验后续、开放问题、论文启发）提炼候选，并在本地代码/文献/经验中检索证据；未运行训练，未访问外部网络。",
        "- 保存规则：本输出不写入 2研究点；用户确认后再调用 `research_point.py add`。",
        "- 说明：指标影响均为待验证假设，不代表已经获得提升；缺省字段由 agent 与用户补全。",
        "",
    ]
    if not candidates:
        lines.append("没有找到同时满足证据数量和高价值阈值的候选方向。请补充本地研究资料或放宽查询关键词。")
        return "\n".join(lines) + "\n"
    for rank, candidate in enumerate(candidates, start=1):
        scores = candidate["scores"]
        lines.extend(
            [
                f"## {rank}. {candidate['title']}",
                "",
                f"- 候选来源：`{candidate['source']}`（{candidate['source_kind']}）",
                f"- 现有缺口：{candidate['gap']}",
                f"- 创新机制：{candidate['innovation']}",
                f"- 预期指标作用机制：{candidate['expected_mechanism']}",
                f"- 最小实现边界：{candidate['implementation']}",
                f"- 单变量验证方案：{candidate['validation']}",
                f"- 风险与停止条件：{candidate['risks']}",
                f"- 评分：创新性 {scores['innovation']}/5，预期收益 {scores['expected_gain']}/5，证据强度 {scores['evidence']}/5，实现可行性 {scores['feasibility']}/5，综合 {scores['total']}/5。",
                "- 本地证据：",
            ]
        )
        for evidence in candidate["evidence"]:
            lines.append(
                f"  - `{evidence['path']}:{evidence['line']}`（{evidence['category']}）：{evidence['snippet']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description="Generate evidence-backed research direction drafts.")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    parser.add_argument("--query", help="Optional keyword filter on candidate titles/gaps.")
    parser.add_argument("--limit", type=int, choices=range(3, 6), default=5, metavar="{3,4,5}")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of Markdown.")
    parser.add_argument("--list-sources", action="store_true", help="List candidate sources without scoring.")
    args = parser.parse_args()
    project_root = resolve_project_root(args.project_root)
    profile = read_profile(project_root)
    if args.list_sources:
        candidates = collect_candidates(project_root)
        for candidate in candidates:
            print(f"{candidate.source_kind}\t{candidate.source_path}:{candidate.source_line}\t{candidate.title}")
        return 0
    candidates = generate(project_root, args.query, args.limit, profile)
    if args.json:
        print(json.dumps({"project_root": str(project_root), "persisted": False, "candidates": candidates}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(project_root, candidates), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
