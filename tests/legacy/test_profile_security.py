from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_DIR / "tools" / "compat"


def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=str(SKILL_DIR), check=False,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


class ProfileSecurityTests(unittest.TestCase):
    def test_convention_paths_reject_parent_and_absolute_traversal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-profile-test-") as temp:
            root = Path(temp)
            self.assertEqual(run("init_ljh_research.py", "create", "--project-root", str(root)).returncode, 0)
            parent = run("project_profile.py", "--project-root", str(root), "--set", "models_dir=../outside")
            absolute = run("project_profile.py", "--project-root", str(root), "--set", "models_dir=C:/outside")
            self.assertNotEqual(parent.returncode, 0)
            self.assertIn("must not contain '..'", parent.stderr)
            self.assertNotEqual(absolute.returncode, 0)
            self.assertIn("must stay relative", absolute.stderr)
            self.assertFalse((root.parent / "outside").exists())

    def test_missing_conventions_are_reported_without_legacy_json_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-profile-test-") as temp:
            root = Path(temp)
            result = run("generate_research_directions.py", "--project-root", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("needs_configuration", result.stderr)
            self.assertFalse((root / "ljh research docs" / ".skill-config.json").exists())


if __name__ == "__main__":
    unittest.main()
