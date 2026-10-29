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


class ExperimentPointTests(unittest.TestCase):
    def test_experiment_lifecycle_and_index(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-exp-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            run("research_point.py", "--project-root", str(root), "add", "--title", "point")
            created = run(
                "experiment_point.py", "--project-root", str(root), "add", "--title", "Complement experiment",
                "--research-point", "RP-0001", "--status", "planned",
            )
            self.assertIn("id=EXP-0001", created.stdout)
            run("experiment_point.py", "--project-root", str(root), "status", "--id", "EXP-0001", "--status", "running")
            run(
                "experiment_point.py", "--project-root", str(root), "conclude", "--id", "EXP-0001",
                "--conclusion", "A and B are complementary.", "--mark-complete",
            )
            card = root / "ljh research docs" / "3实验" / "EXP-0001-complement-experiment.md"
            text = card.read_text(encoding="utf-8")
            self.assertIn("status: completed", text)
            self.assertIn('research_points: ["RP-0001"]', text)
            self.assertIn("A and B are complementary.", text)
            self.assertIn("EXP-0001", run("experiment_point.py", "--project-root", str(root), "list", "--status", "completed").stdout)

    def test_preview_and_micro_card_use_controlled_statuses(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-exp-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            preview = run("experiment_point.py", "--project-root", str(root), "preview", "--title", "Probe", "--kind", "micro")
            self.assertIn("status=planned", preview.stdout)
            run("experiment_point.py", "--project-root", str(root), "add", "--title", "Probe", "--kind", "micro")
            card = root / "ljh research docs" / "3实验" / "MEXP-0001-probe.md"
            self.assertIn("type: micro_experiment", card.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
