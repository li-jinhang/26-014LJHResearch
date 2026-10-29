#!/usr/bin/env python3
"""Audit the project's research assets for evidence-backed optimization points.

只读的科研质量审计：对照项目自身文档（README、01/02/03 根笔记）与代码/卡片
（src/models、src/configs/model、src/experiments、2研究点/3实验/4复现），
产出证据支持的「优化点」草案。检查类别（科研向，不含纯工程效率优化）：

- C1 文档-实现漂移：模型/配置/实验脚本与 README、02「当前模型清单」比对；
- C2 基线数字一致性：README 当前基线 vs 02 当前基线数字比对；
- C3 卡片状态失真：研究点已实现目录/implementation_status、EXP 已完成、REP 已对齐 与结论一致性；
- C4 证据链断裂：卡片与根笔记引用的文件/目录是否存在；
- C5 实验控制硬约束：experiments 脚本是否疑似违反 01 硬约束（固定种子、禁种子搜索）；
- C6 开放问题悬置：02「风险与开放问题」待验证/待补充条目是否有卡片覆盖；
- C7 结论未回写：03 经验的「后续」动作是否有对应卡片/文档痕迹。

脚本不写入任何文件；输出为对话草案（Markdown 或 --json），每条优化点附
file:line 证据与建议动作。用户确认后才按现有流程落库（Documentation-sync /
research_point.py / experiment_point.py）。
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import parse_frontmatter, resolve_project_root
from ljh_research.knowledge.generate_research_directions import read_profile
from ljh_research.knowledge.profile_config import resolve_project_relative
from ljh_research.knowledge.layout import (
    CONSTRAINTS_FILE,
    EXPERIENCE_FILE,
    EXPERIMENTS_DIR,
    FRAMEWORK_FILE,
    KNOWLEDGE_DIR,
    PAPERS_DIR,
    RESEARCH_DIR,
    REPRODUCTIONS_DIR,
    RESEARCH_POINTS_DIR,
    research_root,
)

# ------------------------------------------------------------------ 元数据

CHECKS = [
    ("C1", "文档-实现漂移", "仅枚举 01约束文件.md 已声明的模型、配置、实验目录，并与 README/02 比对"),
    ("C2", "基线数字一致性", "README「当前基线结果」与 02「当前基线」的 Recall@K/NDCG@K 数字交叉比对"),
    ("C3", "卡片状态失真", "研究点 implemented、EXP 终态、REPRO 终态与当前判断一致性"),
    ("C4", "证据链断裂", "RP/EXP/REP 卡片与根笔记引用的文件/目录是否存在"),
    ("C5", "实验控制硬约束", "已配置时，experiments 脚本是否疑似违反 01 硬约束（固定种子、禁种子搜索）"),
    ("C6", "开放问题悬置", "02「风险与开放问题」待验证/待补充条目是否有 RP/EXP 卡片覆盖"),
    ("C7", "结论未回写", "03 研发经验的「后续」动作是否有对应卡片或文档更新痕迹"),
]

SEVERITY_WEIGHT = {"高": 3, "中": 2, "低": 1}

# 建议动作标签
SUGGESTION = {
    "C1": "改文档（Documentation-sync：同步模型/配置/实验清单）",
    "C2": "核验并统一基线数字（单一事实来源）",
    "C3": "落卡状态/补结论（状态必须反映科研事实）",
    "C4": "补证据或修复引用路径（信息网络必须连通）",
    "C5": "核验实验协议（对照 01 实验控制硬约束）",
    "C6": "评估后落卡（research_point.py add / experiment_point.py）",
    "C7": "评估后落库（卡片或文档更新）",
}

# 产物类扩展名：缺失多为被清理，属低严重度提示；源码/文档类缺失为高严重度断裂
ARTIFACT_SUFFIXES = {".log", ".pth", ".pt", ".png", ".jpg", ".jpeg", ".pdf", ".html", ".ckpt"}
SOURCE_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".csv", ".ipynb"}

# C6/C7 通用词（不作为证据实体）
STOP_TOKENS = {
    "RL", "KD", "BPR", "SSL", "SVD", "GCN", "CE", "AI", "NLP", "CV", "MR",
    "NDCG", "RECALL", "PRECISION", "LOSS", "INFO", "NCE", "TOP", "K", "MS",
    "MM", "ID", "UI", "KG", "MSE", "KL", "BCE", "MAP", "MRR", "HIT", "HR",
    "EPOCH", "SEED", "GPU", "CPU", "AMP", "OTA", "CF", "BM", "MRD", "DGD",
    "KDARL", "KDRL", "KDRLADV", "TEACHERT", "TEACHERV", "PGLTEACHER",
}


@dataclass(frozen=True)
class Finding:
    check: str          # C1..C7
    severity: str       # 高 / 中 / 低
    title: str
    impact: str         # 对科研判断的影响
    evidence: tuple[tuple[str, int, str], ...]  # (path, line, snippet)
    suggestion: str = ""

    def with_suggestion(self, suggestion: str) -> "Finding":
        return Finding(self.check, self.severity, self.title, self.impact, self.evidence, suggestion)


def _severity_key(finding: Finding) -> tuple[int, str, str]:
    return (-SEVERITY_WEIGHT.get(finding.severity, 0), finding.check, finding.title)


# ------------------------------------------------------------------ 辅助

def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _all_card_texts(project_root: Path) -> str:
    """RP/EXP/REP 卡片全部文本拼接，用于 C6/C7 覆盖判定。"""
    parts: list[str] = []
    for rel in (RESEARCH_POINTS_DIR, EXPERIMENTS_DIR, REPRODUCTIONS_DIR):
        root = research_root(project_root) / rel
        if root.is_dir():
            for md in root.rglob("*.md"):
                if md.name != "README.md":
                    parts.append(_read_text(md))
    return "\n".join(parts)


def _extract_entities(text: str) -> set[str]:
    """提取大写英文实体（模型名/方法名/数据集名），过滤停用词。"""
    tokens = set(re.findall(r"[A-Z][A-Z0-9_]{2,}", text))
    return {t for t in tokens if t not in STOP_TOKENS}


def _configured_directory(project_root: Path, profile: dict, key: str) -> Path | None:
    """Resolve only an external path explicitly declared in 01约束文件.md."""

    relative = profile.get(key)
    if relative is None:
        return None
    return resolve_project_relative(project_root, relative, key=key)


def configuration_findings(project_root: Path, profile: dict) -> list[Finding]:
    """Make skipped scope explicit; never substitute assumed project defaults."""

    findings: list[Finding] = []
    constraints = research_root(project_root) / CONSTRAINTS_FILE
    for key in ("models_dir", "configs_dir", "experiments_dir", "code_roots"):
        value = profile.get(key)
        if value in (None, []):
            findings.append(Finding(
                "CONFIG", "低", f"needs_configuration: {key}",
                f"01约束文件.md 未声明 {key}；依赖该路径的检查已跳过，未猜测 src/ 等默认目录。",
                ((str(constraints.relative_to(project_root)), 1, f"{key}: null"),),
                "在 01约束文件.md 写入经核验的项目相对路径，或保留 null 并接受相关检查 not_applicable。",
            ))
            continue
        if key == "code_roots":
            exists = all(resolve_project_relative(project_root, item, key=key).exists() for item in value)
        else:
            path = _configured_directory(project_root, profile, key)
            exists = path is not None and path.exists()
        if not exists:
            findings.append(Finding(
                "CONFIG", "低", f"not_applicable: {key}",
                f"{key} 已声明但目标当前不存在；相关代码扫描不适用，没有误报为科研证据错误。",
                ((str(constraints.relative_to(project_root)), 1, f"{key}: {value}"),),
                "创建该已声明路径，或在 01约束文件.md 更正已核验的路径。",
            ))
    return findings


# ------------------------------------------------------------------ C1 文档-实现漂移

def check_c1(project_root: Path, profile: dict) -> list[Finding]:
    findings: list[Finding] = []
    docs_paths = [
        project_root / "README.md",
        research_root(project_root) / CONSTRAINTS_FILE,
        research_root(project_root) / FRAMEWORK_FILE,
        research_root(project_root) / EXPERIENCE_FILE,
    ]
    doc_text = "\n".join(_read_text(p) for p in docs_paths if p.is_file())

    # 模型文件
    models_dir = _configured_directory(project_root, profile, "models_dir")
    if models_dir is not None and models_dir.is_dir():
        actual = {
            p.stem for p in models_dir.glob("*.py")
            if not p.name.startswith("__")
        }
        mentioned = set(re.findall(r"[A-Za-z0-9_./\\-]+[\\/]([a-zA-Z0-9_]+)\.py", doc_text))
        for name in sorted(actual - mentioned):
            findings.append(
                Finding(
                    "C1", "中",
                    f"模型文件未入文档：{models_dir.relative_to(project_root).as_posix()}/{name}.py",
                    "新增/遗留模型若未同步到 README 模型一览与 02「当前模型清单」，后续 agent 无法从文档还原模型清单。",
                    ((str(models_dir / f"{name}.py"), 1, f"{name}.py"),),
                )
            )
        for name in sorted(mentioned - actual):
            findings.append(
                Finding(
                    "C1", "高",
                    f"文档提及已删除模型：{name}.py",
                    "文档仍引用不存在的模型文件，会误导后续复现/实验（引用即断裂）。",
                    ((str(project_root / "README.md"), 1, name),),
                )
            )

    # 配置文件：只做删除检测（文档惯例不逐条列配置路径）
    configs_dir = _configured_directory(project_root, profile, "configs_dir")
    if configs_dir is not None and configs_dir.is_dir():
        actual = {p.stem for p in configs_dir.glob("*.yaml") if not p.name.startswith("_")}
        mentioned = set(re.findall(r"[A-Za-z0-9_./\\-]+[\\/]([a-zA-Z0-9_]+)\.yaml", doc_text))
        for name in sorted(mentioned - actual):
            findings.append(
                Finding(
                    "C1", "低",
                    f"文档提及已删除配置：{name}.yaml",
                    "配置路径引用失效，复现时无法按文档还原配置。",
                    ((str(project_root / "README.md"), 1, name),),
                )
            )

    # 实验脚本：顶层脚本与一级子目录，检测「既未入文档也非待清理项」的新增
    exp_dir = _configured_directory(project_root, profile, "experiments_dir")

    def _mentioned(stem: str) -> bool:
        """stem 是否被文档提及：完全匹配，或文档以 <stem> 或 <stem 前缀>* 形式引用。"""
        if stem.lower() in doc_text.lower():
            return True
        # 文档中的通配符模式（如 run_kdrladv_gamma*.py、noKD_*.log）
        for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\*", doc_text):
            prefix = match.group(1).lower()
            if stem.lower().startswith(prefix):
                return True
        return False

    if exp_dir is not None and exp_dir.is_dir():
        for p in sorted(exp_dir.glob("*.py")):
            if _mentioned(p.stem):
                continue
            findings.append(
                Finding(
                    "C1", "低",
                    f"实验脚本未入文档：{exp_dir.relative_to(project_root).as_posix()}/{p.name}",
                    "实验脚本若未在 02「实验脚本」或经验库记录，后续无法判断其归属与是否仍有效。",
                    ((str(p.relative_to(project_root)), 1, p.name),),
                )
            )
        for p in sorted(exp_dir.iterdir()):
            if not p.is_dir() or p.name in ("__pycache__",):
                continue
            name = p.name
            if _mentioned(name):
                continue
            findings.append(
                Finding(
                    "C1", "低",
                    f"实验目录未入文档：{exp_dir.relative_to(project_root).as_posix()}/{name}/",
                    "实验/复现子目录若未在 02「实验脚本」或对应卡片记录，无法追踪其实验编号与结论。",
                    ((str(p.relative_to(project_root)), 1, name),),
                )
            )
    return findings


# ------------------------------------------------------------------ C2 基线数字一致性

BASELINE_RE = re.compile(
    r"([A-Z][A-Z0-9_]{2,})[^0-9\n]{0,16}?test\s+(Recall@\d+|NDCG@\d+)\s*([0-9]+\.[0-9]{3,4})"
)


def _extract_baselines(text: str) -> dict[tuple[str, str], str]:
    """{(model, metric): value} —— 取每行首个匹配，避免把行内历史数字算入。"""
    result: dict[tuple[str, str], str] = {}
    cleaned = text.replace("`", "")
    for line in cleaned.splitlines():
        for match in BASELINE_RE.finditer(line):
            model, metric, value = match.group(1), match.group(2), match.group(3)
            result.setdefault((model, metric), value)
            break  # 每行只取第一个，历史归档数字多在后文
    return result


def check_c2(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    readme = project_root / "README.md"
    framework = research_root(project_root) / FRAMEWORK_FILE
    if not readme.is_file() or not framework.is_file():
        return []
    # 只比较「当前基线」语境：README「当前基线结果」章节 + 02「当前基线」段
    readme_text = _read_text(readme)
    m = re.search(r"##\s*当前基线结果(.*?)(?=\n## |\Z)", readme_text, re.S)
    readme_baseline = m.group(1) if m else ""
    m2 = re.search(r"当前基线(.*?)(?=\n## |\Z)", _read_text(framework), re.S)
    framework_baseline = m2.group(1) if m2 else ""
    a = _extract_baselines(readme_baseline)
    b = _extract_baselines(framework_baseline)
    for key in sorted(set(a) & set(b)):
        if a[key] != b[key]:
            model, metric = key
            findings.append(
                Finding(
                    "C2", "高",
                    f"基线数字不一致：{model} {metric}（README {a[key]} vs 02 {b[key]}）",
                    "同一模型同一指标的基线在 README 与 02 不一致，破坏单一事实来源，削弱结论可信度。",
                    (
                        (str(readme.relative_to(project_root)), 1, f"{model} test {metric} {a[key]}"),
                        (str(framework.relative_to(project_root)), 1, f"{model} test {metric} {b[key]}"),
                    ),
                )
            )
    return findings


# ------------------------------------------------------------------ C3 卡片状态失真

def _conclusion_is_empty(text: str) -> bool:
    """A conclusion/current-judgement section with only a placeholder is incomplete."""
    match = re.search(r"^##\s*(?:(?:实验)?结论|当前判断)\s*$.*?(?=^## |\Z)", text, re.M | re.S)
    if not match:
        return True
    body = match.group(0)
    body = re.sub(r"^##\s*(?:(?:实验)?结论|当前判断)\s*$", "", body, flags=re.M)
    meaningful = [
        ln.strip() for ln in body.splitlines()
        if ln.strip() and ln.strip() != "待补充。" and not ln.strip().startswith("- 待补充")
    ]
    return not meaningful


def check_c3(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    rp_dir = research_root(project_root) / RESEARCH_POINTS_DIR
    implemented_dir = rp_dir / "已实现"
    if implemented_dir.is_dir():
        for md in sorted(implemented_dir.glob("*.md")):
            meta = parse_frontmatter(_read_text(md))
            if meta.get("implementation_status") != "implemented":
                findings.append(
                    Finding(
                        "C3", "中",
                        f"卡片位于 已实现/ 但缺 implementation_status 标记：{md.name}",
                        "implement 流程会同时移动目录并写 implementation_status；两者不一致说明状态未被正确记录。",
                        ((str(md.relative_to(project_root)), 2, f"status: {meta.get('status', '?')}"),),
                    )
                )
    if rp_dir.is_dir():
        for md in sorted(rp_dir.glob("*.md")):
            if md.name == "README.md":
                continue
            meta = parse_frontmatter(_read_text(md))
            if meta.get("implementation_status") == "implemented" and implemented_dir not in md.parents:
                findings.append(
                    Finding(
                        "C3", "中",
                        f"卡片标记已实现但仍在 {RESEARCH_POINTS_DIR} 根目录：{md.name}",
                        "已实现的创新点应移入 已实现/ 子目录，与索引一致。",
                        ((str(md.relative_to(project_root)), 1, "implementation_status: implemented"),),
                    )
                )
    for rel, terminal_statuses in (
        (EXPERIMENTS_DIR, ("completed", "failed", "invalid")),
        (REPRODUCTIONS_DIR, ("reproduced", "partial", "failed")),
    ):
        root = research_root(project_root) / rel
        if not root.is_dir():
            continue
        for md in sorted(root.glob("*.md")):
            if md.name == "README.md":
                continue
            meta = parse_frontmatter(_read_text(md))
            if meta.get("status") not in terminal_statuses:
                continue
            text = _read_text(md)
            if _conclusion_is_empty(text):
                findings.append(
                    Finding(
                        "C3", "高",
                        f"卡片状态 {meta.get('status')} 但无结论记录：{md.name}",
                        "终端状态必须有可读的当前判断；否则状态与内容失真。",
                        ((str(md.relative_to(project_root)), 4, f"status: {meta.get('status')}"),),
                    )
                )
    return findings


# ------------------------------------------------------------------ C4 证据链断裂

REF_RE = re.compile(r"`([^`]+)`|\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _normalize_ref(ref: str) -> str:
    ref = ref.strip().strip("`")
    ref = ref.replace("\\", "/")
    ref = re.split(r"::", ref)[0].strip()
    ref = re.sub(r":\d+$", "", ref)
    ref = re.sub(r"#L?\d+$", "", ref)
    return ref.strip("./").strip()


def _is_path_like(ref: str) -> bool:
    if not ref or ref.startswith(("http://", "https://", "-", "python ", "pip ")):
        return False
    if ref.startswith(f"{RESEARCH_DIR}/"):
        return True
    if " " in ref or "--" in ref:
        return False
    if ref.startswith(("import ", "from ", "self.", "torch.", "np.", "nn.")):
        return False
    # 绝对路径（D:/...）多为来源记录/外部路径，不按项目内引用检查
    if re.match(r"^[A-Za-z]:[\\/]", ref) or ref.startswith(("/", "\\")):
        return False
    # 模板占位符（<MODEL>.yaml / <model>.py）与通配符（*.log）不是真实引用
    if "<" in ref or ">" in ref or "*" in ref:
        return False
    # 纯中文文件名（如「文件.py」）是说明性占位，不是路径
    if not re.search(r"[A-Za-z0-9_]", Path(ref).stem):
        return False
    suffixes = SOURCE_SUFFIXES | ARTIFACT_SUFFIXES
    if any(ref.endswith(s) for s in suffixes):
        return True
    if ref.startswith(("src/", "0知识库/", "1论文/", "data/", "saved/",
                       "preprocessing/", "results/", "configs/", "tmp/", "image/", "_downloads/")):
        return True
    return False


_BASENAME_INDEX: dict[str, list[Path]] | None = None
_INDEX_ROOT: Path | None = None


def _declared_external_roots(project_root: Path, profile: dict) -> list[Path]:
    """Return only existing code locations that 01约束文件.md explicitly declares."""

    roots: list[Path] = []
    for key in ("models_dir", "configs_dir", "experiments_dir", "main_entry", "training_entry"):
        path = _configured_directory(project_root, profile, key)
        if path is not None and path.exists():
            roots.append(path if path.is_dir() else path.parent)
    for index, relative in enumerate(profile.get("code_roots") or []):
        path = resolve_project_relative(project_root, relative, key=f"code_roots[{index}]")
        if path.exists():
            roots.append(path if path.is_dir() else path.parent)
    return list(dict.fromkeys(roots))


def _build_index(project_root: Path, profile: dict) -> dict[str, list[Path]]:
    """Index only workspace files and explicitly declared external code locations."""
    global _BASENAME_INDEX, _INDEX_ROOT
    if _BASENAME_INDEX is not None and _INDEX_ROOT == project_root:
        return _BASENAME_INDEX
    index: dict[str, list[Path]] = {}
    for base in (research_root(project_root), *_declared_external_roots(project_root, profile)):
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            if p.name.startswith("."):
                continue
            index.setdefault(p.name, []).append(p)
    _BASENAME_INDEX, _INDEX_ROOT = index, project_root
    return index


def _is_declared_external(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == root.resolve() or root.resolve() in resolved.parents for root in roots)


def _resolve_ref(project_root: Path, ref: str, profile: dict) -> Path | None:
    """在项目内解析引用路径；返回第一个存在的候选（文件或目录）。"""
    candidates: list[Path] = []
    external_roots = _declared_external_roots(project_root, profile)
    if ref.startswith("_downloads/"):
        candidates.append(research_root(project_root) / ref)
    elif ref.startswith(f"{RESEARCH_DIR}/"):
        candidates.append(project_root / ref)
    elif ref.startswith(("0知识库/", "1论文/", "2研究点/", "3实验/", "4复现/")):
        candidates.append(research_root(project_root) / ref)
    else:
        candidate = project_root / ref
        if _is_declared_external(candidate, external_roots):
            candidates.append(candidate)
    for cand in candidates:
        if cand.exists():
            return cand
    # 相对/裸名引用：用 basename 索引搜索（如 源文件库/x.pdf、DDKD.yaml）
    if not ref.startswith(("src/", "data/", "saved/", "preprocessing/", "results/",
                           "configs/", "tmp/", "image/", "_downloads/", f"{RESEARCH_DIR}/",
                           "0知识库/", "1论文/", "2研究点/", "3实验/", "4复现/")):
        index = _build_index(project_root, profile)
        parts = ref.split("/")
        fname = parts[-1]
        dirpart = parts[-2] if len(parts) > 1 else None
        for hit in index.get(fname, []):
            if dirpart is None or hit.parent.name == dirpart:
                return hit
    return None


def check_c4(project_root: Path, profile: dict) -> list[Finding]:
    findings: list[Finding] = []
    roots: list[Path] = []
    for rel in (RESEARCH_POINTS_DIR, EXPERIMENTS_DIR, REPRODUCTIONS_DIR):
        root = research_root(project_root) / rel
        if root.is_dir():
            roots.append(root)
    for rel in (KNOWLEDGE_DIR, PAPERS_DIR):
        root = research_root(project_root) / rel
        if root.is_dir():
            roots.append(root)
    for root in roots:
        for md in sorted(root.rglob("*.md")):
            if md.name == "README.md" and root.name not in (KNOWLEDGE_DIR, PAPERS_DIR):
                # 知识库 README 也要检查；卡片库 README 是纯索引，跳过
                continue
            lines = _read_lines(md)
            hits: list[tuple[int, str, str]] = []
            for number, line in enumerate(lines, start=1):
                for match in REF_RE.finditer(line):
                    ref = match.group(1) or match.group(2)
                    ref = _normalize_ref(ref)
                    if not _is_path_like(ref):
                        continue
                    resolved = _resolve_ref(project_root, ref, profile)
                    if resolved is not None:
                        continue
                    hits.append((number, ref, line.strip()[:120]))
                    if len(hits) >= 3:  # 每张卡最多报 3 条，避免刷屏
                        break
                if len(hits) >= 3:
                    break
            for number, ref, snippet in hits:
                suffix = Path(ref).suffix.lower()
                severity = "低" if suffix in ARTIFACT_SUFFIXES else "高"
                findings.append(
                    Finding(
                        "C4", severity,
                        f"证据引用不存在：{ref}",
                        "卡片/笔记引用的文件或目录缺失，证据链断裂，无法按引用核验事实。",
                        ((str(md.relative_to(project_root)), number, snippet),),
                    )
                )
    return findings


# ------------------------------------------------------------------ C5 实验控制硬约束

def check_c5(project_root: Path, profile: dict) -> list[Finding]:
    findings: list[Finding] = []
    exp_dir = _configured_directory(project_root, profile, "experiments_dir")
    fixed_seed = profile.get("fixed_seed")
    if exp_dir is None or not exp_dir.is_dir() or fixed_seed is None:
        return []
    seed_value = str(fixed_seed)
    seed_policy = profile.get("seed_selection")
    seed_loop_re = re.compile(r"\bfor\s+seed\s+in\b", re.I)
    seed_list_re = re.compile(r'"seed"\s*:\s*\[([^\]]*)\]|seed\s*=\s*\[([^\]]*)\]|\bseeds?\s*=\s*\[([^\]]*)\]')
    cli_seed_re = re.compile(r"--seed[^\n]*?default\s*=\s*(\d+)")
    for py in sorted(exp_dir.rglob("*.py")):
        lines = _read_lines(py)
        for number, line in enumerate(lines, start=1):
            if seed_policy == "forbidden" and seed_loop_re.search(line):
                findings.append(
                    Finding(
                        "C5", "高",
                        f"疑似种子循环搜索：{py.name}",
                        f"01 硬约束：随机种子固定为 {seed_value}、不是超参数或优化维度；for-seed 循环疑似违反。",
                        ((str(py.relative_to(project_root)), number, line.strip()[:120]),),
                    )
                )
                continue
            m = seed_list_re.search(line)
            if m:
                body = next(g for g in m.groups() if g is not None)
                values = re.findall(r"\d+", body)
                uniq = set(values)
                if seed_policy == "forbidden" and len(uniq) > 1:
                    findings.append(
                        Finding(
                            "C5", "高",
                            f"疑似种子网格搜索：{py.name}",
                            "多个种子值作为配置列表出现，疑似种子网格搜索（01 硬约束禁止）。",
                            ((str(py.relative_to(project_root)), number, line.strip()[:120]),),
                        )
                    )
                elif uniq and uniq != {seed_value}:
                    findings.append(
                        Finding(
                            "C5", "中",
                            f"疑似更换固定种子：{py.name}（seed={next(iter(uniq))}）",
                            f"非 {seed_value} 种子单值配置需确认是否违反『随机种子固定为 {seed_value}』。",
                            ((str(py.relative_to(project_root)), number, line.strip()[:120]),),
                        )
                    )
                continue
            cm = cli_seed_re.search(line)
            if cm and cm.group(1) != seed_value:
                findings.append(
                    Finding(
                        "C5", "低",
                        f"CLI --seed 默认值非 {seed_value}：{py.name}",
                        f"01 硬约束要求随机种子固定为 {seed_value}，CLI 默认值建议与其一致。",
                        ((str(py.relative_to(project_root)), number, line.strip()[:120]),),
                    )
                )
    return findings


# ------------------------------------------------------------------ C6 开放问题悬置

def check_c6(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    framework = research_root(project_root) / FRAMEWORK_FILE
    if not framework.is_file():
        return []
    text = _read_text(framework)
    m = re.search(r"##\s*风险与开放问题(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        return []
    cards = _all_card_texts(project_root)
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not (stripped.startswith("- 待验证") or stripped.startswith("- 需要补充")):
            continue
        if re.search(r"(RP-\d+|EXP-\d+|PRE-\d+)", stripped):
            continue  # 已有显式卡片引用
        entities = _extract_entities(stripped)
        if not entities:
            continue
        uncovered = sorted(e for e in entities if e not in cards)
        if not uncovered:
            continue
        findings.append(
            Finding(
                "C6", "中",
                f"开放问题无卡片覆盖：{'/'.join(uncovered)}",
                "02 标注的待验证/待补充条目，其关键实体未见对应研究点或实验卡片，方向未进入跟踪。",
                ((str(framework.relative_to(project_root)), number, stripped[:120]),),
            )
        )
    return findings


# ------------------------------------------------------------------ C7 结论未回写

def check_c7(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    experience = research_root(project_root) / EXPERIENCE_FILE
    if not experience.is_file():
        return []
    lines = _read_lines(experience)
    cards = _all_card_texts(project_root)
    framework_text = _read_text(research_root(project_root) / FRAMEWORK_FILE)
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("- 后续："):
            continue
        followup = stripped.split("：", 1)[1].strip()
        if len(followup) < 8:
            continue
        if re.search(r"(RP-\d+|EXP-\d+|PRE-\d+)", followup):
            continue  # 后续已显式指向卡片
        entities = _extract_entities(followup)
        if not entities:
            continue
        uncovered = sorted(e for e in entities if e not in cards and e not in framework_text)
        if not uncovered:
            continue
        findings.append(
            Finding(
                "C7", "低",
                f"经验后续未见落库痕迹：{'/'.join(uncovered)}",
                "03 经验承诺的后续动作（实体未在任何卡片或 02 中出现），可能尚未落库或被遗漏。",
                ((str(experience.relative_to(project_root)), number, stripped[:120]),),
            )
        )
    return findings


# ------------------------------------------------------------------ 汇总与输出

def generate(project_root: Path, profile: dict) -> list[Finding]:
    findings: list[Finding] = configuration_findings(project_root, profile)
    findings.extend(check_c1(project_root, profile))
    findings.extend(check_c2(project_root))
    findings.extend(check_c3(project_root))
    findings.extend(check_c4(project_root, profile))
    findings.extend(check_c5(project_root, profile))
    findings.extend(check_c6(project_root))
    findings.extend(check_c7(project_root))
    result: list[Finding] = []
    for finding in findings:
        result.append(finding.with_suggestion(SUGGESTION[finding.check]) if not finding.suggestion else finding)
    result.sort(key=_severity_key)
    return result


def render_markdown(project_root: Path, findings: list[Finding]) -> str:
    lines = [
        "# 项目优化点审查草案",
        "",
        f"- 项目：`{project_root}`",
        "- 生成方式：只读静态审计（对照 README 与 01/02/03 根笔记、src 代码目录、RP/EXP/REP 卡片）；未运行训练，未访问外部网络。",
        "- 保存规则：本输出不写入任何库；每条优化点需 agent 亲自核验证据、与用户确认后再按建议动作落库。",
        "- 说明：C5 为静态启发式判定，需人工核验脚本语义；优化点不代表任何指标提升已发生。",
        "",
    ]
    if not findings:
        lines.append("未发现科研优化点。可在项目更新后重跑，或调整检查范围。")
        return "\n".join(lines) + "\n"
    for index, finding in enumerate(findings, start=1):
        lines.extend(
            [
                f"## {index}. [{finding.severity}] {finding.check} {finding.title}",
                "",
                f"- 科研影响：{finding.impact}",
                f"- 建议动作：{finding.suggestion}",
                "- 证据：",
            ]
        )
        for path, line_number, snippet in finding.evidence:
            lines.append(f"  - `{path}:{line_number}`：{snippet}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description="Audit project research assets for optimization points.")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    parser.add_argument("--query", help="Optional keyword filter on finding titles.")
    parser.add_argument("--limit", type=int, default=0, help="Max findings to show (0 = all).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of Markdown.")
    parser.add_argument("--list-checks", action="store_true", help="List audit check categories and exit.")
    parser.add_argument("--min-severity", choices=["高", "中", "低"], default="低",
                        help="Minimum severity to report (default: 低).")
    args = parser.parse_args()
    if args.list_checks:
        for code, name, detail in CHECKS:
            print(f"{code}\t{name}\t{detail}")
        return 0
    project_root = resolve_project_root(args.project_root)
    profile = read_profile(project_root)
    findings = generate(project_root, profile)
    min_weight = SEVERITY_WEIGHT[args.min_severity]
    findings = [f for f in findings if SEVERITY_WEIGHT[f.severity] >= min_weight]
    if args.query:
        lowered = args.query.lower()
        findings = [f for f in findings if lowered in f.title.lower() or lowered in f.impact.lower()]
    if args.limit > 0:
        findings = findings[: args.limit]
    if args.json:
        payload = {
            "project_root": str(project_root),
            "persisted": False,
            "checks": [{"code": c, "name": n} for c, n, _ in CHECKS],
            "findings": [
                {
                    "check": f.check,
                    "severity": f.severity,
                    "title": f.title,
                    "impact": f.impact,
                    "suggestion": f.suggestion,
                    "evidence": [{"path": p, "line": ln, "snippet": sn} for p, ln, sn in f.evidence],
                }
                for f in findings
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(project_root, findings), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
