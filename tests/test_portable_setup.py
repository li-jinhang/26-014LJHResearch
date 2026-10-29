import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "ljh-research-setup"


class PortableSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ljh-portable-setup-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bundle = self.base / "download with spaces/ljh-research-setup"
        shutil.copytree(SKILL, self.bundle, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.binding = self.base / "user config/runtime.json"
        self.runtime = self.base / "user runtime"
        self.env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
        self.env["LJH_RESEARCH_RUNTIME_BINDING"] = str(self.binding)

    def run_command(self, command, check=True):
        return subprocess.run(list(map(str, command)), cwd=self.base, env=self.env,
                              capture_output=True, encoding="utf-8", errors="replace", check=check, timeout=120)

    def installer(self, *extra, check=True):
        return self.run_command([sys.executable, "-I", self.bundle / "scripts/install_runtime.py",
                                 "--runtime-dir", self.runtime, *extra], check=check)

    def test_plan_has_no_writes_and_tampered_wheel_fails_before_installation(self):
        planned = json.loads(self.installer().stdout)
        self.assertTrue(planned["offline"])
        self.assertEqual(len(planned["packages"]), 4)
        self.assertFalse(self.binding.exists())
        self.assertFalse(self.runtime.exists())
        wheel = next((self.bundle / "assets/wheels").glob("*.whl"))
        wheel.write_bytes(wheel.read_bytes() + b"corrupted")
        failed = self.installer("--apply", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("hash mismatch", failed.stderr)
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.binding.exists())

    def test_bundled_code_resources_and_shared_launcher_match_current_source(self):
        manifest = json.loads((SKILL / "assets/wheels/manifest.json").read_text(encoding="utf-8"))
        sources = {"ljh-research-core": ROOT / "src/ljh_research",
                   "ljh-research-local": ROOT / "packages/local-executor/src/ljh_research_local",
                   "ljh-research-controller": ROOT / "packages/controller/src/ljh_research_controller",
                   "ljh-research-panel": ROOT / "packages/panel/src/ljh_research_panel"}
        for package, source in sources.items():
            item = manifest["packages"][package]
            wheel = SKILL / "assets/wheels" / item["filename"]
            self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), item["sha256"])
            with zipfile.ZipFile(wheel) as archive:
                for path in source.rglob("*"):
                    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                        member = source.name + "/" + path.relative_to(source).as_posix()
                        self.assertEqual(archive.read(member).replace(b"\r\n", b"\n"),
                                         path.read_bytes().replace(b"\r\n", b"\n"), member)
        self.assertEqual((SKILL / "scripts/_entry.py").read_bytes(),
                         (ROOT / "src/ljh_research/resources/skill_variants/entry.py").read_bytes())

    def test_copied_skill_installs_offline_and_deploys_both_versions_without_checkout(self):
        if os.name == "nt":
            self.run_command(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                self.bundle / "scripts/bootstrap.ps1", "-Python", sys.executable,
                "-RuntimeDirectory", self.runtime, "-Apply"])
        else:
            self.run_command(["sh", self.bundle / "scripts/bootstrap.sh", "--python", sys.executable,
                              "--runtime-dir", self.runtime, "--apply"])
        installed = Path(json.loads(self.binding.read_text(encoding="utf-8"))["python"])
        imported = self.run_command([installed, "-I", "-c", "import ljh_research; print(ljh_research.__file__)"])
        self.assertTrue(Path(imported.stdout.strip()).is_relative_to(self.runtime))
        # The calling interpreter has neither the core nor the checkout on sys.path.
        client = self.base / "plain client"
        self.run_command([sys.executable, "-I", "-m", "venv", "--without-pip", client])
        client_python = client / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.run_command([client_python, "-c", "import importlib.util; assert importlib.util.find_spec('ljh_research') is None"])
        self.bundle = self.bundle.rename(self.base / "relocated setup")
        setup = self.bundle / "scripts/setup.py"
        project = self.base / "research project"
        project.mkdir()
        created = self.run_command([client_python, setup, "create", "--project-root", project, "--version", "manual", "--approve"])
        self.assertTrue(json.loads(created.stdout)["ok"])
        slot = project / ".agents/skills/ljh-research"
        self.assertIn("# LJH Research Manual", (slot / "SKILL.md").read_text(encoding="utf-8"))
        switched = self.run_command([client_python, setup, "version", "--project-root", project, "--select", "auto", "--approve"])
        self.assertTrue(json.loads(switched.stdout)["ok"])
        self.assertIn("# LJH Research Auto", (slot / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual([p.name for p in slot.parent.iterdir()], ["ljh-research"])
        validated = self.run_command([client_python, setup, "validate", "--project-root", project])
        self.assertEqual(json.loads(validated.stdout)["result"]["status"], "valid")
        # Existing deployments keep working when the setup download disappears.
        self.bundle.rename(self.base / "retired download")
        entry = slot / "scripts/research.py"
        info = self.run_command([client_python, entry, "workspace.get"])
        self.assertEqual(json.loads(info.stdout)["result"]["research_version"], "auto")
        workflow = self.run_command([client_python, entry, "workflow.get", "--params", '{"topic":"layered-memory"}'])
        self.assertTrue(json.loads(workflow.stdout)["ok"])
        self.assertTrue((project / "ljh research docs/.workspace.json").is_file())


if __name__ == "__main__":
    unittest.main()
