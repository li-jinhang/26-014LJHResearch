"""Read-only real-source sampling; all generated memory stays in an isolated pilot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from ljh_research.public import dispatch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=r"D:\_Projects\26-001DistillingRecommendation\ljh research")
    parser.add_argument("--pilot", default=str(Path(__file__).resolve().parents[1] / ".local/layered-memory-pilot-20261029-verified"))
    args = parser.parse_args()
    application = Path(__file__).resolve().parents[1]
    source = Path(args.source).resolve()
    pilot = Path(args.pilot).resolve()
    assert pilot.is_relative_to(application / ".local") and not pilot.is_relative_to(source)
    before = snapshot(source)
    pilot.mkdir(parents=True, exist_ok=True)
    def call(method, params=None, human=False):
        value = dispatch({"protocol_version": 1, "project_root": str(pilot), "method": method, "params": params or {}},
                         human=human, evidence="User authorized small-sample layered-memory validation inside the application project" if human else "")
        assert value["ok"], value
        return value["result"]
    if not (pilot / "ljh research docs").exists():
        call("setup.create", {"version": "auto"}, human=True)
    else:
        call("setup.repair", human=True)
    fixtures = pilot / "fixtures"
    fixtures.mkdir(exist_ok=True)
    copied = []
    def copy(relative, target):
        original = source / relative
        destination = fixtures / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            assert sha(destination) == sha(original)
        else:
            shutil.copy2(original, destination)
        copied.append({"source": str(original), "copy": str(destination), "sha256": sha(original)})
        return destination.relative_to(pilot).as_posix()
    paper_base = "1论文/计算机/多模态推荐系统/源文件库/"
    note_base = "0知识库/计算机/多模态推荐系统/知识库/"
    paper_specs = [
        ("Reinforced-Multi-Teacher-Selection-for-Knowledge-Distillation-AAAI2021.pdf", "18-RL-KD论文", ["知识蒸馏", "强化学习"], ["01-论文问题与总体架构.md", "02-方法与模型.md", "03-关键机制与细节.md"]),
        ("Automated-Curriculum-Learning-for-Neural-Networks-ICML2017.pdf", "19-AutomatedCurriculumLearning论文", ["课程学习", "强化学习"], ["01-论文问题与总体架构.md", "02-方法与模型.md", "03-关键机制与细节.md"]),
    ]
    objects = []
    for index, (pdf, folder, topics, notes) in enumerate(paper_specs, 1):
        raw = copy(paper_base + pdf, f"paper-{index}/original.pdf")
        attachments = [copy(note_base + folder + "/" + n, f"paper-{index}/" + n) for n in notes]
        objects.append(call("memory.import", {"kind": "paper", "title": folder.split("-", 1)[1], "path": raw,
                        "reading_notes": attachments, "topics": topics, "origin": str(source / (paper_base + pdf))}, human=True))
    experiments = ["PRE-002-Oracle上限诊断-样本级教师加权天花板.md", "EXP-007-DDKDRLT-reliable-consensus-and-complementary-residual-ablation.md"]
    for name in experiments:
        raw = copy("3实验/" + name, "experiments/" + name)
        identifier = re.match(r"[A-Z]+-\d+", name)[0]
        objects.append(call("memory.import", {"kind": "experiment", "id": identifier, "title": name[:-3], "path": raw,
                        "topics": ["多模态推荐系统", "知识蒸馏", "强化学习"], "origin": str(source / "3实验" / name)}, human=True))
    history = (source / "03研发经验.md").read_text(encoding="utf-8")
    for index, title in enumerate(["PGLKD策略奖励平衡诊断", "随机种子硬性控制约束"], 1):
        match = re.search(r"(?m)^(#{2,6})\s+" + re.escape(title) + r"\s*$", history)
        assert match, title
        following = re.search(r"(?m)^#{1," + str(len(match[1])) + r"}\s+", history[match.end():])
        end = match.end() + following.start() if following else len(history)
        fragment = history[match.start():end].strip() + "\n"
        destination = fixtures / f"experience-{index}.md"
        destination.write_text(fragment, encoding="utf-8")
        copied.append({"source": str(source / "03研发经验.md"), "source_section": title, "source_sha256": sha(source / "03研发经验.md"), "copy": str(destination), "copy_sha256": sha(destination)})
        objects.append(call("memory.import", {"kind": "experience", "title": title, "path": destination.relative_to(pilot).as_posix(),
                        "topics": ["实验纪律"] if index == 2 else ["知识蒸馏", "强化学习"], "origin": str(source / "03研发经验.md") + "#" + title}, human=True))
    queries = [
        {"query": "teacher selection delayed reward", "purpose": "innovation", "kind": "paper"},
        {"query": "奖励塌缩", "purpose": "debug", "kind": "experience"},
        {"query": "随机种子 选择纪律", "purpose": "experiment_design", "kind": "experience"},
        {"query": "共识 互补 rho", "purpose": "result_analysis", "kind": "experiment"},
    ]
    searches = []
    for query in queries:
        result = call("memory.search", {**query, "budget_chars": 4000})
        assert result["hits"], query
        assert len(json.dumps(result, ensure_ascii=False)) <= 4000
        searches.append({"request": query, "response": result})
    paper = objects[0]["id"]
    view = call("memory.read", {"topic": "强化学习", "kind": "paper", "budget_chars": 10000})
    single = call("memory.read", {"id": paper, "budget_chars": 14000})
    point = next(p for p in single["points"] if p["aspect"] == "architecture")
    cite = point["citations"][0]
    evidence = call("memory.read", {"id": paper, "view": "detail", "source_id": cite["source_id"],
                                  "start_line": cite["start_line"], "end_line": cite["end_line"], "budget_chars": 4000})
    assert cite["quote"] in evidence["content"] and cite["source_sha256"] == evidence["source_sha256"]
    # This is agent-authored semantic writeback from the exact quoted sample,
    # distinct from the program's automatic extractive first pass.
    semantic = {"text": "这份已有研读笔记将方法概括为：冻结教师提供软标签，样本级选择策略决定参与蒸馏的教师集合，学生表现形成延迟回报。",
                "aspect": "architecture", "keywords": ["教师选择", "延迟回报"], "evidence_type": "reading_note",
                "conditions": ["仅归纳当前引用的已有研读笔记；未在本轮重新验证论文实验或向图推荐迁移的效果。"], "citations": [cite]}
    learned = call("memory.extract", {"id": paper, "claims": [semantic]}, human=True)
    assert learned["mode"] == "agent_semantic"
    after = snapshot(source)
    assert before == after, "Actual research source changed"
    report = {"pilot_root": str(pilot), "source_root": str(source), "source_file_count": len(before), "actual_source_unchanged": True,
              "source_manifest_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
              "objects": objects, "copied_samples": copied, "searches": searches,
              "drill_down": {"topic": view, "object_id": paper, "point_id": point["point_id"], "evidence": evidence},
              "agent_semantic_writeback": learned, "automatic_extraction": "source-grounded structural excerpts; no external model called",
              "scientific_training_started": False, "status": call("memory.status")}
    (pilot / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (application / "docs/evidence/layered-memory-pilot.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["pilot_root", "source_file_count", "actual_source_unchanged", "status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
