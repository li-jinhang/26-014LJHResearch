from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_DIR / "tools" / "compat"


def run_script(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args], cwd=str(SKILL_DIR), check=check,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def create(root: Path) -> None:
    run_script("init_ljh_research.py", "create", "--project-root", str(root))


class LjhResearchTests(unittest.TestCase):
    def test_card_ids_statuses_and_ascii_filenames(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-research-test-") as temp:
            root = Path(temp)
            create(root)
            point = run_script("research_point.py", "--project-root", str(root), "add", "--title", "测试研究点")
            experiment = run_script(
                "experiment_point.py", "--project-root", str(root), "add", "--title", "测试实验", "--research-point", "RP-0001"
            )
            reproduction = run_script(
                "reproduction.py", "--project-root", str(root), "add", "--title", "测试论文", "--method", "Test Method",
                "--dataset", "demo", "--paper-metrics", "score=1",
            )
            self.assertIn("id=RP-0001", point.stdout)
            self.assertIn("id=EXP-0001", experiment.stdout)
            self.assertIn("id=REPRO-0001", reproduction.stdout)
            workspace = root / "ljh research docs"
            self.assertTrue((workspace / "2研究点" / "RP-0001-research-point.md").is_file())
            self.assertTrue((workspace / "3实验" / "EXP-0001-experiment.md").is_file())
            repro = workspace / "4复现" / "REPRO-0001-test-method.md"
            self.assertTrue(repro.is_file())
            self.assertIn("status: planned", repro.read_text(encoding="utf-8"))
            run_script("reproduction.py", "--project-root", str(root), "round", "--id", "REPRO-0001", "--metrics", "score=1")
            self.assertIn("status: reproduced", repro.read_text(encoding="utf-8"))

    def test_import_uses_stable_paper_id_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-research-test-") as temp:
            root = Path(temp)
            create(root)
            source = root / "paper.txt"
            source.write_text("A small readable paper.", encoding="utf-8")
            run_script(
                "import_paper.py", "--project-root", str(root), "--source", str(source), "--title", "Test Paper",
                "--method", "Test Method", "--topic-root-relative", "0知识库/Test/Topic",
            )
            workspace = root / "ljh research docs"
            knowledge = workspace / "0知识库" / "Test" / "Topic" / "知识库" / "PAPER-0001" / "README.md"
            extraction = workspace / "1论文" / "Test" / "Topic" / "提取内容" / "PAPER-0001.md"
            self.assertTrue(knowledge.is_file())
            self.assertTrue(extraction.is_file())
            self.assertIn("id: PAPER-0001", knowledge.read_text(encoding="utf-8"))
            self.assertTrue((workspace / "1论文" / "源文件库").exists())

    def test_direction_generator_reads_only_declared_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-research-test-") as temp:
            root = Path(temp)
            create(root)
            run_script("project_profile.py", "--project-root", str(root), "--set", 'models_dir="models"')
            models = root / "models"
            models.mkdir()
            (models / "student.py").write_text("# graph distillation teacher confidence", encoding="utf-8")
            card = root / "ljh research docs" / "2研究点" / "RP-0001-graph.md"
            card.write_text(
                "---\nid: RP-0001\ntitle: Graph direction\ntype: research-point\nstatus: draft\n---\n\n"
                "## 核心假设\n\ngraph distillation teacher confidence can improve ranking.\n",
                encoding="utf-8",
            )
            before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
            result = run_script("generate_research_directions.py", "--project-root", str(root), "--limit", "3")
            after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
            self.assertEqual(before, after)
            self.assertIn("高研究价值方向候选草案", result.stdout)


if __name__ == "__main__":
    unittest.main()
