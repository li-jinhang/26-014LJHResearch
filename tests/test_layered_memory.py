import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ljh_research.public import dispatch


class LayeredMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ljh-memory-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.call("setup.create", human=True)
        (self.root / "inputs").mkdir()

    def raw(self, method, params=None, human=False):
        return dispatch({"protocol_version": 1, "project_root": str(self.root), "method": method, "params": params or {}},
                        human=human, evidence="Synthetic isolated memory verification" if human else "")

    def call(self, method, params=None, human=False):
        value = self.raw(method, params, human)
        self.assertTrue(value["ok"], value)
        return value["result"]

    def add(self, kind="paper", text=None, topics=None, name="sample.md", title="Teacher routing"):
        path = self.root / "inputs" / name
        path.write_text(text or "# Method\n\n## Architecture\n\nTeacher routing uses a policy to choose teachers.\n\n## 实验条件\n\nDataset B, fixed seed and validation selection.\n\n## 实验结论\n\nNo improvement under the declared protocol; this does not refute all routing methods.\n", encoding="utf-8")
        return self.call("memory.import", {"kind": kind, "title": title, "path": "inputs/" + name,
                         "topics": topics if topics is not None else ["知识蒸馏", "强化学习"]}, human=True)

    def test_flat_storage_multi_topic_and_global_identity(self):
        one = self.add()
        another = self.add(name="other.md", text="# Architecture\n\nA different distillation architecture.\n", topics=["多模态推荐系统"])
        self.assertNotEqual(one["id"], another["id"])
        self.assertEqual(len(list((self.root / "ljh research docs/1论文/源文件库").glob("PAPER-*.md"))), 2)
        self.assertFalse((self.root / "ljh research docs/1论文/计算机").exists())
        self.assertTrue((self.root / "ljh research docs/1论文/知识提炼/领域专题/强化学习.md").is_file())
        again = self.call("memory.import", {"kind": "paper", "title": "Same source", "path": "inputs/sample.md", "topics": ["多模态推荐系统"]}, human=True)
        self.assertEqual(again["id"], one["id"])
        self.assertTrue(again["existing"])
        self.assertEqual(self.call("memory.status")["objects"], 2)

    def test_keyword_alias_and_purpose_search_respect_hard_context_budget(self):
        self.add()
        experiment = self.add(kind="experiment", name="experiment.md", title="Teacher selection results")
        result = self.call("memory.search", {"query": "教师选择", "purpose": "experiment_design", "budget_chars": 1600})
        self.assertEqual(result["hits"][0]["id"], experiment["id"])
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 1600)
        self.assertEqual(result["coverage"], "registered_objects_only")
        self.assertTrue(self.call("memory.search", {"query": "teacher routing"})["hits"])
        self.assertEqual(self.call("memory.search", {"query": "nonexistentmechanism"})["matched_objects"], 0)

    def test_negative_result_retains_conditions_and_provenance(self):
        obj = self.add(kind="experiment")
        summary = self.call("memory.read", {"id": obj["id"], "budget_chars": 18000})
        point = next(p for p in summary["points"] if p["aspect"] == "result")
        self.assertIn("does not refute all", point["text"])
        self.assertTrue(any("Dataset B" in c for c in point["conditions"]))
        self.assertEqual(point["evidence_type"], "project_record")
        self.assertTrue(point["citations"])

    def test_hierarchical_drill_down_returns_exact_evidence_range(self):
        obj = self.add()
        topic = self.call("memory.read", {"topic": "强化学习", "kind": "paper", "budget_chars": 10000})
        self.assertEqual(topic["level"], "topic")
        summary = self.call("memory.read", {"id": obj["id"], "budget_chars": 18000})
        point = next(p for p in summary["points"] if p["aspect"] == "architecture")
        cite = point["citations"][0]
        detail = self.call("memory.read", {"id": obj["id"], "view": "detail", "source_id": cite["source_id"], "start_line": cite["start_line"], "end_line": cite["end_line"]})
        self.assertEqual(detail["source_sha256"], cite["source_sha256"])
        self.assertIn(cite["quote"], detail["content"])
        outline = self.call("memory.read", {"id": obj["id"], "view": "detail", "source_id": cite["source_id"]})
        self.assertEqual(outline["level"], "outline")
        self.assertNotIn("content", outline)

    def test_semantic_writeback_requires_real_quote_and_distinguishes_inference(self):
        obj = self.add()
        detail = self.call("memory.read", {"id": obj["id"], "view": "detail", "source_id": "TEXT", "section": "Architecture"})
        citation = {k:detail[k] for k in ("source_id", "source_sha256", "start_line", "end_line")}
        citation["quote"] = "Teacher routing uses a policy to choose teachers."
        point = {"text": "The recorded architecture uses a policy-based teacher selector.", "aspect": "architecture", "evidence_type": "agent_inference",
                 "keywords": ["教师路由"], "conditions": ["Interpretation of this source only"], "citations": [citation]}
        bad = self.raw("memory.extract", {"id": obj["id"], "claims": [{**point, "citations": [{**citation, "quote": "invented result"}]}]}, human=True)
        self.assertEqual(bad["error"]["code"], "invalid_citation")
        result = self.call("memory.extract", {"id": obj["id"], "claims": [point]}, human=True)
        self.assertEqual(result["mode"], "agent_semantic")
        self.assertGreater(result["points"], 1)
        repeated = self.call("memory.extract", {"id": obj["id"], "claims": [point]}, human=True)
        self.assertFalse(repeated["changed"])

    def test_source_changes_invalidate_object_topic_and_old_citations(self):
        obj = self.add(kind="experience")
        summary = self.call("memory.read", {"id": obj["id"], "budget_chars": 18000})
        point = summary["points"][0]
        source = self.root / "ljh research docs/5经验/原始记录" / (obj["id"] + ".md")
        source.write_text(source.read_text(encoding="utf-8") + "\nNew contrary evidence.\n", encoding="utf-8")
        self.assertEqual(self.call("memory.search", {"query": "teacher routing"})["hits"][0]["freshness"], "stale")
        topic = self.call("memory.read", {"topic": "强化学习", "kind": "experience"})
        self.assertEqual(topic["freshness"], "stale")
        self.assertNotIn("content", topic)
        old = self.raw("memory.extract", {"id": obj["id"], "claims": [point]}, human=True)
        self.assertEqual(old["error"]["code"], "stale_source")
        paper = self.add(kind="paper", name="changed-paper.md", text="# Architecture\n\nOriginal paper architecture.\n")
        raw = self.root / "ljh research docs/1论文/源文件库" / (paper["id"] + ".md")
        raw.write_text("# Architecture\n\nRevised architecture in a new original version.\n", encoding="utf-8")
        refreshed = self.raw("memory.extract", {"id": paper["id"]}, human=True)
        self.assertEqual(refreshed["error"]["code"], "source_changed")
        self.assertEqual(self.call("memory.read", {"id": paper["id"]})["freshness"]["state"], "stale")

    def test_mutation_requires_authority_and_source_scope(self):
        (self.root / "inputs/scope.md").write_text("# Evidence\n\nA fact.\n", encoding="utf-8")
        denied = self.raw("memory.import", {"kind": "experience", "title": "Scope", "path": "inputs/scope.md"})
        self.assertFalse(denied["ok"])
        task = self.call("task.create", {"title": "Memory task", "objective": "Read permitted sources", "authorization": {"allowed_roots": ["runs"], "max_runs": 0}})
        self.call("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved"}, human=True)
        lease = self.call("task.claim", {"task_id": task["task"]["id"], "driver_id": "fixture"})["lease"]
        denied = self.raw("memory.import", {"kind": "experience", "title": "Scope", "path": "inputs/scope.md", "task_id": task["task"]["id"], "lease": lease})
        self.assertEqual(denied["error"]["code"], "undeclared_path")

    def test_deleted_derived_index_can_be_rebuilt_without_losing_knowledge(self):
        obj = self.add()
        index = self.root / "ljh research docs/.runtime/memory/index.json"
        index.unlink()
        self.assertEqual(self.call("memory.search", {"query": "teacher selection"})["hits"][0]["id"], obj["id"])
        self.call("memory.rebuild", human=True)
        self.assertTrue(index.is_file())

    def test_user_authored_topic_is_preserved_as_a_visible_conflict(self):
        self.add()
        topic = self.root / "ljh research docs/1论文/知识提炼/领域专题/强化学习.md"
        topic.write_text("# User-authored topic\n", encoding="utf-8")
        result = self.raw("memory.rebuild", human=True)
        self.assertEqual(result["error"]["code"], "memory_conflict")
        self.assertEqual(topic.read_text(encoding="utf-8"), "# User-authored topic\n")

    def test_default_paper_cli_uses_flat_layout_and_existing_root_source_search(self):
        source = self.root / "inputs/cli.md"
        source.write_text("# Architecture\n\nKnowledge distillation transfers predictions.\n", encoding="utf-8")
        process = subprocess.run([sys.executable, "-m", "ljh_research.knowledge.import_paper", "--project-root", str(self.root), "--source", str(source), "--title", "Flat import test", "--method", "KD", "--topic-root-relative", "0知识库/Test/Topic"], capture_output=True, encoding="utf-8")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertFalse((self.root / "ljh research docs/1论文/Test").exists())
        match = self.call("knowledge.invoke", {"tool": "search_source_file", "arguments": ["--query", "Flat import test"]})
        self.assertIn("found=true", match["output"])

    def test_card_conclusion_capture_and_experience_use_layered_memory(self):
        point = self.call("knowledge.invoke", {"tool": "experiment_point", "arguments": ["add", "--title", "Controlled comparison"]}, human=True)
        self.assertTrue(point["memory_updates"])
        self.assertEqual(self.call("memory.status")["by_kind"]["experiment"], 1)
        old = (self.root / "ljh research docs/03研发经验.md").read_bytes()
        result = self.call("knowledge.invoke", {"tool": "append_rd_experience", "arguments": ["--topic", "Seed selection", "--text", "Fixed seed controls the comparison; no seed selection."]}, human=True)
        self.assertIn("experience_id=RD-", result["output"])
        self.assertEqual(self.call("memory.status")["by_kind"]["experience"], 1)
        self.assertEqual((self.root / "ljh research docs/03研发经验.md").read_bytes(), old)

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "PDF extraction is an optional extra")
    def test_blank_pdf_never_becomes_a_completed_paper_read(self):
        from pypdf import PdfWriter
        pdf = self.root / "inputs/blank.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with pdf.open("wb") as stream:
            writer.write(stream)
        result = self.call("memory.import", {"kind": "paper", "title": "Blank PDF", "path": "inputs/blank.pdf"}, human=True)
        self.assertEqual(result["extraction"]["points"], 0)
        self.assertIn(result["id"], self.call("memory.status")["pending_ids"])

    def test_semantic_revision_retains_unrelated_points_and_archives_superseded(self):
        obj = self.add()
        before = self.call("memory.read", {"id": obj["id"], "budget_chars": 18000})
        selected = before["points"][0]
        replacement = {**selected, "text": "A concise architecture description grounded in the same source.", "extraction_mode": "agent_semantic"}
        self.call("memory.extract", {"id": obj["id"], "claims": [replacement], "supersedes": [selected["point_id"]]}, human=True)
        after = self.call("memory.read", {"id": obj["id"], "budget_chars": 18000})
        self.assertEqual(len(before["points"]), len(after["points"]))
        self.assertFalse(any(p["point_id"] == selected["point_id"] for p in after["points"]))
        self.assertTrue(list((self.root / "ljh research docs/.runtime/memory/history" / obj["id"]).glob("*.md")))

    def test_later_reading_notes_extend_existing_paper_without_copying_original(self):
        obj = self.add()
        before = self.call("memory.read", {"id": obj["id"], "budget_chars": 18000})
        point = {**before["points"][0], "text": "Previously interpreted architecture.", "extraction_mode": "agent_semantic"}
        self.call("memory.extract", {"id": obj["id"], "claims": [point]}, human=True)
        (self.root / "inputs/later.md").write_text("# Innovation\n\nCounterfactual routing is a new reading observation.\n", encoding="utf-8")
        result = self.call("memory.import", {"kind": "paper", "title": "Teacher routing", "path": "inputs/sample.md", "reading_notes": ["inputs/later.md"]}, human=True)
        self.assertEqual(result["id"], obj["id"])
        self.assertEqual(len(list((self.root / "ljh research docs/1论文/源文件库").glob("PAPER-*.md"))), 1)
        self.assertTrue(self.call("memory.search", {"query": "Counterfactual"})["hits"])
        after = self.call("memory.read", {"id": obj["id"], "budget_chars": 18000})
        self.assertTrue(any(p["text"] == point["text"] for p in after["points"]))

    def test_invalid_topic_does_not_poison_existing_record(self):
        obj = self.add()
        result = self.raw("memory.import", {"kind": "paper", "title": "Teacher routing", "path": "inputs/sample.md", "topics": ["../escape"]}, human=True)
        self.assertEqual(result["error"]["code"], "invalid_topic")
        self.assertNotIn("../escape", self.call("memory.read", {"id": obj["id"]})["topics"])


if __name__ == "__main__":
    unittest.main()
