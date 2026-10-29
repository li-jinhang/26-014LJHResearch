"""Uniform layers and owned empty-workspace resources, without runtime effects."""
import json

MARKER = ".memory.json"
KINDS = {
    "paper": ("PAPER", "1论文", "知识提炼/论文卡片", "源文件库"),
    "research_point": ("RP", "2研究点", "知识提炼/单项", "卡片"),
    "experiment": ("EXP", "3实验", "知识提炼/单项", "实验记录"),
    "reproduction": ("REPRO", "4复现", "知识提炼/单项", "复现记录"),
    "experience": ("RD", "5经验", "知识提炼/单项", "原始记录"),
}
MEMORY_DIRECTORIES = ("0知识库/方法与问题", "0知识库/当前认识与证据缺口", "1论文/源文件库", "1论文/提取内容", "5经验/原始记录") + tuple(
    f"{folder}/{part}" for _, folder, single, detail in KINDS.values()
    for part in {single, detail, "知识提炼/领域专题"})


def expected_files():
    data = {MARKER: json.dumps({"kind": "ljh-layered-memory", "schema_version": 1}, indent=2) + "\n",
            "00记忆导航.md": "# 科研记忆导航\n\n先按问题检索主题与单项提炼，再按引用读取证据片段。索引只覆盖已登记对象，不代表项目全部资料。\n\n各集合均有证据详情、单项提炼和主题提炼；跨类型知识见 `0知识库/方法与问题/`。\n"}
    for directory in MEMORY_DIRECTORIES:
        data[directory + "/README.md"] = "# " + directory + "\n\n<!-- ljh-memory-owned -->\n\n本目录由分层记忆模块管理。原件按类型保存，领域通过标签和专题引用关联。通过 memory.search 查找，再用 memory.read 按需展开。\n"
    for folder in ("0知识库", "1论文", "5经验"):
        data[folder + "/README.md"] = "# " + folder + "\n\n先通过 memory.search 按问题检索，再展开主题与对象。原件/完整记录与知识提炼分开，专题允许多来源、多领域关联。\n"
    return data
