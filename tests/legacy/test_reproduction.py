from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_DIR / "tools" / "compat"


def run(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=str(SKILL_DIR), check=check,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


class ReproductionTests(unittest.TestCase):
    def test_card_rounds_and_terminal_statuses(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-repro-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            created = run(
                "reproduction.py", "--project-root", str(root), "add", "--title", "Paper", "--method", "Test Method",
                "--dataset", "demo", "--paper-metrics", "Recall=0.1;NDCG=0.05",
            )
            self.assertIn("id=REPRO-0001", created.stdout)
            card = root / "ljh research docs" / "4复现" / "REPRO-0001-test-method.md"
            first = run(
                "reproduction.py", "--project-root", str(root), "round", "--id", "REPRO-0001",
                "--metrics", "Recall=0.11;NDCG=0.05",
            )
            self.assertIn("status=planned", first.stdout)
            aligned = run(
                "reproduction.py", "--project-root", str(root), "round", "--id", "REPRO-0001",
                "--metrics", "Recall=0.1;NDCG=0.05",
            )
            self.assertIn("status=reproduced", aligned.stdout)
            self.assertIn("status: reproduced", card.read_text(encoding="utf-8"))
            denied = run(
                "reproduction.py", "--project-root", str(root), "round", "--id", "REPRO-0001",
                "--metrics", "Recall=0.1;NDCG=0.05", check=False,
            )
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("already aligned", denied.stderr)

    def test_status_refine_and_invalid_metrics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-repro-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            invalid = run(
                "reproduction.py", "--project-root", str(root), "add", "--title", "Bad", "--method", "Bad",
                "--dataset", "demo", "--paper-metrics", "Recall", check=False,
            )
            self.assertNotEqual(invalid.returncode, 0)
            run(
                "reproduction.py", "--project-root", str(root), "add", "--title", "Paper", "--method", "Method",
                "--dataset", "demo", "--paper-metrics", "score=1",
            )
            run("reproduction.py", "--project-root", str(root), "status", "--id", "REPRO-0001", "--status", "blocked")
            run("reproduction.py", "--project-root", str(root), "conclude", "--id", "REPRO-0001", "--conclusion", "Waiting for data.")
            listed = run("reproduction.py", "--project-root", str(root), "list", "--status", "blocked")
            self.assertIn("REPRO-0001", listed.stdout)



    @staticmethod
    def section_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("reproduction_heading_test", SCRIPTS / "reproduction.py")
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(SCRIPTS))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        return module

    def test_real_template_protocol_and_metric_updates_preserve_rounds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-repro-headings-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            run("reproduction.py", "--project-root", str(root), "add", "--title", "Paper",
                "--method", "Method", "--dataset", "demo", "--paper-metrics", "score=1")
            card = root / "ljh research docs" / "4复现" / "REPRO-0001-method.md"
            run("reproduction.py", "--project-root", str(root), "round", "--id", "REPRO-0001",
                "--metrics", "score=1.1", "--action", "ROUND_SENTINEL")
            before = card.read_text(encoding="utf-8")
            self.assertIn("### 数据与评估协议", before)
            self.assertIn("### 对齐指标与论文值", before)
            self.assertIn("### 轮次记录", before)
            preserved = before[before.index("### 对齐指标与论文值"):before.index("## 迭代历史")]
            run("reproduction.py", "--project-root", str(root), "refine", "--id", "REPRO-0001",
                "--section", "protocol", "--text", "PROTOCOL_SENTINEL")
            appended = card.read_text(encoding="utf-8")
            protocol = appended.split("### 数据与评估协议", 1)[1].split("### 对齐指标与论文值", 1)[0]
            self.assertIn("PROTOCOL_SENTINEL", protocol)
            self.assertEqual(preserved, appended[appended.index("### 对齐指标与论文值"):appended.index("## 迭代历史")])
            remaining = appended[appended.index("### 轮次记录"):appended.index("## 迭代历史")]
            run("reproduction.py", "--project-root", str(root), "refine", "--id", "REPRO-0001",
                "--section", "paper_metrics", "--text", "score=2")
            replaced = card.read_text(encoding="utf-8")
            self.assertEqual(remaining, replaced[replaced.index("### 轮次记录"):replaced.index("## 迭代历史")])
            self.assertEqual(protocol, replaced.split("### 数据与评估协议", 1)[1].split("### 对齐指标与论文值", 1)[0])
            self.assertIn("ROUND_SENTINEL", replaced)
            self.assertIn("paper_metrics: score=2.0", replaced)
            metrics = replaced.split("### 对齐指标与论文值", 1)[1].split("### 轮次记录", 1)[0]
            self.assertEqual(metrics.strip(), "score=2.0")

    def test_section_boundaries_follow_actual_heading_levels(self) -> None:
        module = self.section_module()
        text = ("## 外层\n\nINTRO\n\n### 协议扩展\n\nPREFIX\n\n### 协议\n\nOLD\n\n"
                "#### 子节\n\nCHILD\n\n### 指标\n\nMETRIC\n\n## 结果\n\nRESULT\n")
        appended = module.append_to_section(text, "协议", "ADDED")
        self.assertLess(appended.index("CHILD"), appended.index("ADDED"))
        self.assertLess(appended.index("ADDED"), appended.index("### 指标"))
        self.assertEqual(text.split("### 协议\n", 1)[0], appended.split("### 协议\n", 1)[0])
        self.assertEqual(text[text.index("### 指标"):], appended[appended.index("### 指标"):])
        outer = module.append_to_section(text, "外层", "OUTER_ADDED")
        self.assertLess(outer.index("METRIC"), outer.index("OUTER_ADDED"))
        self.assertLess(outer.index("OUTER_ADDED"), outer.index("## 结果"))
        higher_boundary = module.replace_section("### 协议\nOLD\n## 结果\nKEEP\n", "协议", "NEW")
        self.assertEqual(higher_boundary.split("## 结果", 1)[1], "\nKEEP\n")

    def test_fenced_and_inline_heading_text_is_not_a_section(self) -> None:
        module = self.section_module()
        prefix = ("## 开头\n正文中 ## 协议\n    ### 协议\n"
                  "````text\n## 协议\n```\n### 协议\n````\n"
                  "~~~text\n### 协议\n~~~\n")
        text = prefix + "### 协议 ###\n\nOLD\n\n### 后续\n\nKEEP\n"
        changed = module.replace_section(text, "协议", "NEW")
        self.assertTrue(changed.startswith(prefix + "### 协议 ###\n"))
        self.assertIn("\nNEW\n", changed)
        self.assertNotIn("OLD", changed)
        self.assertEqual(text[text.index("### 后续"):], changed[changed.index("### 后续"):])

    def test_missing_section_remains_before_real_history(self) -> None:
        module = self.section_module()
        text = "## 核心\n\n```\n## 迭代历史\n```\n\n## 迭代历史\n\nHISTORY\n"
        changed = module.append_to_section(text, "新章节", "NEW")
        self.assertTrue(changed.startswith("## 核心\n\n```\n## 迭代历史\n```\n\n"))
        self.assertLess(changed.index("## 新章节"), changed.rindex("## 迭代历史"))
        self.assertTrue(changed.endswith("## 迭代历史\n\nHISTORY\n"))

if __name__ == "__main__":
    unittest.main()
