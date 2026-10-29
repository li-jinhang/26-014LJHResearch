from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_DIR / "tools" / "compat"


def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=str(SKILL_DIR), check=True,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


class AuditOptimizationPointTests(unittest.TestCase):
    def test_unconfigured_scope_is_explicit_in_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-audit-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            markdown = run("audit_optimization_points.py", "--project-root", str(root))
            self.assertIn("needs_configuration: models_dir", markdown.stdout)
            self.assertNotIn("src/models", markdown.stdout)
            payload = json.loads(run("audit_optimization_points.py", "--project-root", str(root), "--json").stdout)
            self.assertTrue(any(item["title"] == "needs_configuration: experiments_dir" for item in payload["findings"]))

    def test_declared_seed_and_experiment_path_are_audited(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-audit-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            run("project_profile.py", "--project-root", str(root), "--set", 'experiments_dir="experiments"')
            run("project_profile.py", "--project-root", str(root), "--set", "fixed_seed=42")
            experiment = root / "experiments"
            experiment.mkdir()
            (experiment / "run.py").write_text("seed = [1, 2]\n", encoding="utf-8")
            result = run("audit_optimization_points.py", "--project-root", str(root))
            self.assertIn("疑似种子网格搜索", result.stdout)
            self.assertIn("C5", result.stdout)

    def test_list_checks_is_utf8_safe(self) -> None:
        result = run("audit_optimization_points.py", "--list-checks")
        self.assertIn("C1\t文档-实现漂移", result.stdout)


if __name__ == "__main__":
    unittest.main()
