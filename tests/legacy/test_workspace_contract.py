from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_DIR / "tools" / "compat"


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        cwd=str(SKILL_DIR),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class WorkspaceContractTests(unittest.TestCase):
    def test_plan_is_read_only_then_create_is_explicit_and_traceable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
            root = Path(temp)
            plan = run_script("init_ljh_research.py", "plan", "--project-root", str(root))
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("CREATE ljh research docs/", plan.stdout)
            self.assertFalse((root / "ljh research docs").exists())

            created = run_script(
                "init_ljh_research.py", "create", "--project-root", str(root), "--automatic-task", "initialize"
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            workspace = root / "ljh research docs"
            self.assertTrue((workspace / ".workspace.json").is_file())
            self.assertTrue((workspace / "01约束文件.md").read_text(encoding="utf-8").startswith("---\n"))
            logs = list((workspace / "logs").glob("*.log"))
            self.assertEqual(len(logs), 1)
            self.assertIn("CREATE path=ljh research docs/01约束文件.md", logs[0].read_text(encoding="utf-8"))
            self.assertFalse(any((workspace / "1论文").rglob("PAPER-*.md")))

            validated = run_script("init_ljh_research.py", "validate", "--project-root", str(root))
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertIn("workspace_status=valid", validated.stdout)
            self.assertIn("needs_configuration=models_dir", validated.stdout)

    def test_repair_requires_an_owned_workspace_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
            root = Path(temp)
            self.assertEqual(run_script("init_ljh_research.py", "create", "--project-root", str(root)).returncode, 0)
            workspace = root / "ljh research docs"
            missing = workspace / "2研究点" / "README.md"
            missing.unlink()
            check = run_script("init_ljh_research.py", "validate", "--project-root", str(root))
            self.assertEqual(check.returncode, 2)
            self.assertIn("2研究点/README.md: missing", check.stdout)
            repaired = run_script("init_ljh_research.py", "repair", "--project-root", str(root))
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            self.assertTrue(missing.is_file())

            unowned_root = root / "other"
            (unowned_root / "ljh research docs").mkdir(parents=True)
            denied = run_script("init_ljh_research.py", "repair", "--project-root", str(unowned_root))
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("not owned", denied.stderr)

    def test_conventions_are_the_only_profile_source_and_reject_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
            root = Path(temp)
            self.assertEqual(run_script("init_ljh_research.py", "create", "--project-root", str(root)).returncode, 0)
            updated = run_script(
                "project_profile.py", "--project-root", str(root), "--set", 'models_dir="src/models"'
            )
            self.assertEqual(updated.returncode, 0, updated.stderr)
            constraints = (root / "ljh research docs" / "01约束文件.md").read_text(encoding="utf-8")
            self.assertIn('models_dir: "src/models"', constraints)
            self.assertFalse((root / "ljh research docs" / ".skill-config.json").exists())
            unsafe = run_script(
                "project_profile.py", "--project-root", str(root), "--set", 'models_dir="../outside"'
            )
            self.assertNotEqual(unsafe.returncode, 0)
            self.assertIn("must not contain '..'", unsafe.stderr)

    def test_workspace_path_cannot_be_used_as_project_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
            root = Path(temp)
            self.assertEqual(run_script("init_ljh_research.py", "create", "--project-root", str(root)).returncode, 0)
            nested = run_script("init_ljh_research.py", "plan", "--project-root", str(root / "ljh research docs"))
            self.assertNotEqual(nested.returncode, 0)
            self.assertIn("must be the project root", nested.stderr)

    def test_feature_writes_stop_when_workspace_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
            root = Path(temp)
            denied = run_script(
                "research_point.py", "--project-root", str(root), "add", "--title", "No workspace"
            )
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("workspace is missing", denied.stderr)
            self.assertFalse((root / "ljh research docs").exists())


    def test_convention_writes_reject_unowned_and_corrupt_markers_without_changes(self) -> None:
        markers = {
            "missing": None,
            "invalid_json": b"{broken",
            "invalid_utf8": b"\xff\xfe\x80",
            "wrong_kind": b'{"kind":"other","schema_version":1}',
            "wrong_version": b'{"kind":"ljh-research-workspace","schema_version":2}',
            "boolean_version": b'{"kind":"ljh-research-workspace","schema_version":true}',
        }
        for label, marker in markers.items():
            with self.subTest(marker=label), tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
                root = Path(temp)
                created = run_script("init_ljh_research.py", "create", "--project-root", str(root))
                self.assertEqual(created.returncode, 0, created.stderr)
                path = root / "ljh research docs" / ".workspace.json"
                if marker is None:
                    path.unlink()
                else:
                    path.write_bytes(marker)

                def snapshot() -> tuple[dict[str, str], set[str]]:
                    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in root.rglob("*") if p.is_file()}
                    directories = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_dir()}
                    return files, directories

                before = snapshot()
                for name, value in (("project_profile.py", 'models_dir="src/new-models"'),
                                    ("experiments_dir.py", "new-experiments/nested")):
                    denied = run_script(name, "--project-root", str(root), "--set", value)
                    self.assertNotEqual(denied.returncode, 0, denied.stdout)
                    self.assertIn("not owned", denied.stderr)
                    self.assertNotIn("Traceback", denied.stderr)
                    self.assertEqual(snapshot(), before)
                validated = run_script("init_ljh_research.py", "validate", "--project-root", str(root))
                self.assertEqual(validated.returncode, 2, validated.stderr)
                self.assertIn("workspace_status=unowned", validated.stdout)
                self.assertNotIn("Traceback", validated.stderr)
                self.assertEqual(snapshot(), before)

    def test_direct_convention_write_and_update_require_ownership(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        from project_conventions import DEFAULTS, update, write
        with tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
            root = Path(temp)
            for operation in (lambda: write(root, dict(DEFAULTS)),
                              lambda: update(root, "models_dir", "src/models")):
                with self.assertRaisesRegex(ValueError, "not owned"):
                    operation()
                self.assertEqual(list(root.iterdir()), [])

    def test_owned_convention_updates_preserve_body_and_allow_experiment_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ljh-workspace-") as temp:
            root = Path(temp)
            self.assertEqual(run_script("init_ljh_research.py", "create", "--project-root", str(root)).returncode, 0)
            path = root / "ljh research docs" / "01约束文件.md"
            original = path.read_text(encoding="utf-8")
            body = original.split("\n---\n", 1)[1] + "\nUser notes: 保留已有正文。\n"
            path.write_text(original.split("\n---\n", 1)[0] + "\n---\n" + body, encoding="utf-8")
            marker = root / "ljh research docs" / ".workspace.json"
            marker_before = marker.read_bytes()
            updated = run_script("experiments_dir.py", "--project-root", str(root), "--set", "runs/approved")
            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertTrue((root / "runs" / "approved").is_dir())
            self.assertEqual(path.read_text(encoding="utf-8").split("\n---\n", 1)[1], body)
            self.assertEqual(marker.read_bytes(), marker_before)
            self.assertEqual(json.loads(marker_before)["kind"], "ljh-research-workspace")



if __name__ == "__main__":
    unittest.main()
