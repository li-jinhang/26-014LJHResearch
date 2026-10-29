from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPT = SKILL_DIR / "tools" / "compat" / "operation_guard.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=SKILL_DIR / "tools" / "compat",
        text=True,
        capture_output=True,
        check=False,
    )


class OperationGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()
        (self.root / "models").mkdir()
        (self.root / "models" / "main.py").write_text("MODEL = 'base'\n", encoding="utf-8")
        (self.root / "README.md").write_text("baseline\n", encoding="utf-8")
        self.state = Path(self.temp_dir.name) / "guard-state.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def snapshot(self) -> None:
        result = run("--project-root", str(self.root), "snapshot", "--state", str(self.state))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_allows_new_isolated_experiment_tree(self) -> None:
        self.snapshot()
        target = run(
            "--project-root", str(self.root), "check-new-target", "--target", "experiments/EXP-001", "--under", "experiments",
        )
        self.assertEqual(target.returncode, 0, target.stderr)
        experiment = self.root / "experiments" / "EXP-001"
        experiment.mkdir(parents=True)
        (experiment / "run.py").write_text("print('smoke')\n", encoding="utf-8")

        verified = run(
            "--project-root", str(self.root), "verify", "--state", str(self.state),
            "--under", "experiments", "--allow-new-root", "experiments/EXP-001",
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertIn("protected=true", verified.stdout)

    def test_rejects_changed_existing_file(self) -> None:
        self.snapshot()
        (self.root / "models" / "main.py").write_text("MODEL = 'changed'\n", encoding="utf-8")

        verified = run("--project-root", str(self.root), "verify", "--state", str(self.state), "--under", "experiments")
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("changed=models/main.py", verified.stdout)
        self.assertIn("protected=false", verified.stdout)

    def test_rejects_unplanned_new_project_file(self) -> None:
        self.snapshot()
        (self.root / "README-extra.md").write_text("unexpected\n", encoding="utf-8")

        verified = run("--project-root", str(self.root), "verify", "--state", str(self.state), "--under", "experiments")
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("unexpected_added=README-extra.md", verified.stdout)

    def test_rejects_existing_or_research_targets(self) -> None:
        self.assertNotEqual(
            run(
                "--project-root", str(self.root), "check-new-target", "--target", "models/main.py", "--under", "experiments",
            ).returncode,
            0,
        )
        self.assertNotEqual(
            run(
                "--project-root", str(self.root), "check-new-target", "--target", "ljh research docs/3实验/EXP-001", "--under", "experiments",
            ).returncode,
            0,
        )
        self.assertNotEqual(
            run(
                "--project-root", str(self.root), "check-new-target", "--target", "models/new.py", "--under", "experiments",
            ).returncode,
            0,
        )


if __name__ == "__main__":
    unittest.main()
