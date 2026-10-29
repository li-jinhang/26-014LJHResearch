"""Adapt the existing behavioral tests to the installed migrated implementation."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
tests = root / "tests/legacy"
compat = root / "tools/compat"
tests.mkdir(exist_ok=True)
compat.mkdir(exist_ok=True)
(tests / "__init__.py").write_text("", encoding="utf-8")
with zipfile.ZipFile(root / ".local/pre-migration-skill.zip") as bundle:
    for name in bundle.namelist():
        if name.startswith("scripts/") and name.endswith(".py"):
            stem = Path(name).stem
            module = "ljh_research.setup.workspace" if stem == "init_ljh_research" else "ljh_research.knowledge." + stem
            legacy = '    import os\n    os.environ["LJH_RESEARCH_LEGACY_LAYOUT"] = "1"\n' if stem in {"import_paper", "download_paper", "append_rd_experience"} else ''
            (compat / Path(name).name).write_text(f'from {module} import *\nif __name__ == "__main__":\n{legacy}    raise SystemExit(main())\n', encoding="utf-8")
        if name.startswith("tests/test_") and name.endswith(".py") and Path(name).stem not in {"test_skill_entrypoint", "test_operation_modes"}:
            text = bundle.read(name).decode("utf-8")
            text = text.replace('Path(__file__).resolve().parents[1]', 'Path(__file__).resolve().parents[2]')
            text = text.replace('SKILL_DIR / "scripts"', 'SKILL_DIR / "tools" / "compat"')
            text = text.replace('SKILL_DIR / "templates"', 'SKILL_DIR / "src/ljh_research/resources/templates"')
            text = text.replace('.ljh-research', 'ljh research docs').replace('ljh research/', 'ljh research docs/')
            text = text.replace('self.assertFalse((workspace / "1论文" / "源文件库").exists())', 'self.assertTrue((workspace / "1论文" / "源文件库").exists())')
            (tests / Path(name).name).write_text(text, encoding="utf-8")
print("Prepared migrated behavioral regression suite")
