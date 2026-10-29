"""One-time source migration, preserving the exact pre-migration skill in a ZIP.

This imports the user's current working files, not Git HEAD, so unpublished fixes
are preserved. It does not modify the installed skills.
"""
from pathlib import Path
import ast
import hashlib
import json
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("C:/Users/QH/.agents/skills/ljh-research")
DEST = ROOT / "src/ljh_research/knowledge"
DEST.mkdir(parents=True, exist_ok=True)
archive = ROOT / ".local/pre-migration-skill.zip"
archive.parent.mkdir(exist_ok=True)
if archive.exists():
    raise SystemExit("Migration snapshot already exists; refusing to overwrite")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for path in SOURCE.rglob("*"):
        if path.is_file() and not {".git", "__pycache__"}.intersection(path.relative_to(SOURCE).parts):
            bundle.write(path, path.relative_to(SOURCE).as_posix())

names = {p.stem for p in (SOURCE / "scripts").glob("*.py")}
provenance = {}
for path in (SOURCE / "scripts").glob("*.py"):
    provenance[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    text = path.read_text(encoding="utf-8")
    for name in names:
        target = "ljh_research.workspace_contract" if name == "init_ljh_research" else "ljh_research.knowledge." + name
        text = re.sub(r"(?m)^from " + re.escape(name) + r" import ", "from " + target + " import ", text)
    # Script-to-script calls must also work from a wheel, independent of skill paths.
    text = re.sub(r'str\(Path\(__file__\).with_name\("([a-z_]+)\.py"\)\)',
                  lambda m: '"-m", "ljh_research.knowledge.' + m[1] + '"', text)
    if path.stem == "init_ljh_research":
        (ROOT / "src/ljh_research/setup/workspace.py").write_text(text, encoding="utf-8")
    else:
        (DEST / path.name).write_text(text, encoding="utf-8")
(DEST / "__init__.py").write_text('"""Migrated research operations, preserving current local implementation."""\n', encoding="utf-8")
shutil.copytree(SOURCE / "templates", ROOT / "src/ljh_research/resources/templates")
(ROOT / "docs/adr").mkdir(parents=True, exist_ok=True)
for path in (SOURCE / "docs/adr").glob("*.md"):
    shutil.copy2(path, ROOT / "docs/adr" / path.name)
shutil.copy2(SOURCE / "CONTEXT.md", ROOT / "CONTEXT.md")
(ROOT / "docs/migration-provenance.json").write_text(json.dumps({
    "source": str(SOURCE), "basis": "working-tree", "sha256": provenance,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Imported current research code and templates; source skills untouched.")
