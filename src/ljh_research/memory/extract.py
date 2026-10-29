"""Conservative extractive first pass; semantic interpretation is agent writeback."""
import re

ASPECTS = {
    "architecture": ("架构", "方法与模型", "architecture", "framework"),
    "innovation": ("创新", "关键机制", "innovation", "contribution"),
    "application": ("启发", "应用", "application"),
    "result": ("实验结论", "结果", "result", "观察"),
    "condition": ("协议", "控制", "条件", "比对对象", "设置", "背景", "condition"),
    "limitation": ("局限", "证据边界", "风险", "反例", "limitation"),
    "hypothesis": ("假设", "研究问题", "问题", "hypothesis"),
    "lesson": ("结论", "经验", "决策", "lesson"),
}
ALIASES = (
    ("强化学习", "rl", "reinforcement learning", "policy learning"),
    ("知识蒸馏", "kd", "knowledge distillation", "distillation"),
    ("多模态推荐系统", "多模态推荐", "multimodal recommendation", "mmrec"),
    ("教师路由", "教师选择", "teacher routing", "teacher selection", "hard routing"),
    ("奖励", "回报", "reward", "return"),
    ("塌缩", "坍缩", "collapse", "collapsed"),
    ("延迟收益", "延迟回报", "delayed reward", "delayed return"),
    ("等权", "equal weight", "equal-weight", "equal_weight"),
    ("互补", "complementary", "complementarity"),
    ("可靠共识", "共识", "consensus"),
    ("评估口径", "评估协议", "evaluation protocol", "validation selection"),
    ("种子", "随机种子", "seed"),
    ("元学习", "meta learning", "meta-learning", "meta-bpr"),
)


def contains(text, term):
    if re.fullmatch(r"[a-zA-Z0-9_-]+", term):
        return re.search(r"(?<![a-zA-Z0-9_])" + re.escape(term) + r"(?![a-zA-Z0-9_])", text, re.I) is not None
    return term.casefold() in text.casefold()


def query_terms(query):
    terms = set()
    cleaned = re.sub(r"为什么|如何|怎么|是否|哪些|什么|请问|进行|相关|的", " ", query.casefold())
    for word in re.findall(r"[a-zA-Z0-9_+.-]+|[\u4e00-\u9fff]+", cleaned):
        terms.add(word)
        if re.search(r"[\u4e00-\u9fff]", word):
            terms.update(word[i:i+2] for i in range(len(word)-1))
    for group in ALIASES:
        if any(contains(query, term) for term in group):
            terms.update(group)
    return sorted(terms, key=lambda t: (-len(t), t))


def outline(text):
    return [{"section": line.lstrip("# ").strip(), "line": number}
            for number, line in enumerate(text.splitlines(), 1) if re.match(r"^#{1,6}\s+", line)]


def candidates(text):
    """Preserve whole source paragraphs/bullets, never truncate away qualifications."""
    lines = text.splitlines()
    heading = ""
    chunk = []
    start = 0
    def emit():
        raw = "\n".join(chunk).strip()
        if not raw or len(raw) > 1800:
            return None
        lowered = heading.casefold() + " " + raw[:25].casefold()
        aspect = next((key for key, labels in ASPECTS.items() if any(label in lowered for label in labels)), "overview")
        if raw.startswith(("---", "|", "<!--", "```")) or re.match(r"^\w+:\s", raw):
            return None
        return {"text": raw, "aspect": aspect, "start_line": start, "end_line": start + len(chunk)-1, "section": heading}
    frontmatter = bool(lines and lines[0] == "---")
    for number, line in enumerate(lines, 1):
        if frontmatter:
            if number > 1 and line == "---":
                frontmatter = False
            continue
        if re.match(r"^#{1,6}\s+", line):
            item = emit()
            if item:
                yield item
            chunk = []
            heading = line.lstrip("# ").strip()
        elif not line.strip() or line.startswith(("- ", "* ")) and chunk:
            item = emit()
            if item:
                yield item
            chunk = [line] if line.strip() else []
            start = number
        else:
            if not chunk:
                start = number
            chunk.append(line)
    item = emit()
    if item:
        yield item
