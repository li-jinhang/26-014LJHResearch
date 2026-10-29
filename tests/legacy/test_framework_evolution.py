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


class FrameworkEvolutionTests(unittest.TestCase):
    def test_validated_point_requires_framework_decision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-framework-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            run("research_point.py", "--project-root", str(root), "add", "--title", "Point")
            invalid = run("research_point.py", "--project-root", str(root), "status", "--id", "RP-0001", "--status", "validated", check=False)
            self.assertNotEqual(invalid.returncode, 0)
            run("research_point.py", "--project-root", str(root), "status", "--id", "RP-0001", "--status", "active")
            run("research_point.py", "--project-root", str(root), "status", "--id", "RP-0001", "--status", "validated")
            routed = run("scheduler.py", "--project-root", str(root), "next", "--id", "RP-0001")
            self.assertIn("workflow=validated-framework-adoption", routed.stdout)
            card = root / "ljh research docs" / "2研究点" / "RP-0001-point.md"
            self.assertIn("framework_adoption: pending_decision", card.read_text(encoding="utf-8"))

    def test_completed_experiment_routes_to_active_point(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-framework-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            run("research_point.py", "--project-root", str(root), "add", "--title", "Point")
            run("research_point.py", "--project-root", str(root), "status", "--id", "RP-0001", "--status", "active")
            run("experiment_point.py", "--project-root", str(root), "add", "--title", "Experiment", "--research-point", "RP-0001")
            run("experiment_point.py", "--project-root", str(root), "conclude", "--id", "EXP-0001", "--conclusion", "Done", "--mark-complete")
            routed = run("scheduler.py", "--project-root", str(root), "next", "--experiment", "EXP-0001")
            self.assertIn("event=experiment-completed", routed.stdout)
            self.assertIn("workflow=active-evidence", routed.stdout)


if __name__ == "__main__":
    unittest.main()
