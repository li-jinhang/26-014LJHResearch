from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_DIR / "tools" / "compat"
TEMPLATES = SKILL_DIR / "src/ljh_research/resources/templates"


def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=str(SKILL_DIR), check=True,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


class TemplateResourceTests(unittest.TestCase):
    def test_high_frequency_templates_share_machine_metadata_and_body_skeleton(self) -> None:
        for path in (
            TEMPLATES / "cards" / "research-point.md", TEMPLATES / "cards" / "experiment.md",
            TEMPLATES / "cards" / "reproduction.md", TEMPLATES / "papers" / "paper-knowledge.md",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn("schema_version: 1", text)
            self.assertIn("title:", text)
            self.assertIn("type:", text)
            self.assertIn("## 摘要", text)
            self.assertIn("## 来源与证据", text)
            self.assertIn("## 核心内容", text)
            self.assertIn("## 当前判断", text)

    def test_rendered_cards_contain_no_template_tokens(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-template-test-") as temp:
            root = Path(temp)
            run("init_ljh_research.py", "create", "--project-root", str(root))
            run("research_point.py", "--project-root", str(root), "add", "--title", "Template point")
            card = next((root / "ljh research docs" / "2研究点").glob("RP-*.md"))
            text = card.read_text(encoding="utf-8")
            self.assertNotIn("{{", text)
            self.assertNotIn("}}", text)


if __name__ == "__main__":
    unittest.main()
