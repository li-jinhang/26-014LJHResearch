"""Verify installed wheels from a neutral cwd, without source/skill imports."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
python = root / ".local/wheel-env" / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")
with tempfile.TemporaryDirectory(prefix="ljh-wheel-") as folder:
    def call(method, params=None, human=False):
        request = {"protocol_version": 1, "project_root": folder, "method": method, "params": params or {}}
        command = [str(python), "-m", "ljh_research.cli"]
        if human:
            command += ["--human", "--evidence", "Isolated wheel verification"]
        result = subprocess.run(command, input=json.dumps(request), capture_output=True, encoding="utf-8", cwd=folder)
        payload = json.loads(result.stdout)
        assert payload["ok"], payload
        return payload["result"]
    call("setup.create", human=True)
    assert call("setup.validate")["status"] == "valid"
    point = call("knowledge.invoke", {"tool": "research_point", "arguments": ["add", "--title", "Wheel relocation check"]}, human=True)
    assert "RP-0001" in point["output"]
    assert call("workflow.get", {"version": "auto"})["workflow_revision"] == 1
    call("setup.version", {"version": "auto"}, human=True)
    assert call("workspace.get")["skill_name"] == "ljh-research"
    project = Path(folder)
    assert (project / "ljh research docs/.workspace.json").is_file()
    local_entry = project / ".agents/skills/ljh-research/scripts/research.py"
    assert local_entry.is_file()
    launched = subprocess.run([str(python), str(local_entry), "workspace.get"], capture_output=True,
                              encoding="utf-8", cwd=project.parent, check=True)
    assert json.loads(launched.stdout)["result"]["project_root"] == str(project)
    sample = project / "memory-wheel.md"
    sample.write_text("# Architecture\n\nKnowledge distillation selects a teacher under fixed conditions.\n", encoding="utf-8")
    memory = call("memory.import", {"kind": "paper", "title": "Wheel memory check", "path": sample.name, "topics": ["知识蒸馏"]}, human=True)
    assert call("memory.search", {"query": "teacher", "budget_chars": 1800})["hits"]
    assert call("memory.read", {"id": memory["id"], "view": "detail", "source_id": "TEXT", "section": "Architecture"})["level"] == "evidence"
    imported = subprocess.run([str(python), "-c", "import ljh_research; print(ljh_research.__file__)"], capture_output=True, text=True, cwd=folder, check=True)
    report = {"installed_core": imported.stdout.strip(), "neutral_working_directory": True,
              "workspace_create_validate": True, "card_resources": True, "packaged_workflows": True, "version_selection": True,
              "project_local_deployment": True, "canonical_document_directory": "ljh research docs", "project_bound_launcher": True,
              "layered_memory_import_search_drilldown": True,
              "wheels": {p.name: {"file_count": len(zipfile.ZipFile(p).namelist()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                         for p in (root / "dist").glob("*.whl")}}
    (root / "docs/evidence/wheel-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
