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


class FoamIntegrationTests(unittest.TestCase):
    def test_workspace_includes_foam_resources_and_controlled_queries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-foam-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            foam = root / "ljh research docs" / ".foam"
            self.assertIn("status == 'active'", (foam / "queries" / "active-research-points.yaml").read_text(encoding="utf-8"))
            self.assertIn("REPRO-0000", (foam / "templates" / "reproduction.md").read_text(encoding="utf-8"))
            status = run("foam_bridge.py", "--project-root", str(root), "status")
            payload = json.loads(status.stdout)
            self.assertTrue(payload["configured"])


if __name__ == "__main__":
    unittest.main()
