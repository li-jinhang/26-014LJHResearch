import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ljh_research.public import dispatch
from ljh_research.setup.skills import destination


class ProjectDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ljh-project-setup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project with spaces"
        self.root.mkdir()

    def raw(self, method, params=None, human=False, root=None):
        return dispatch({"protocol_version": 1, "project_root": str(root or self.root), "method": method, "params": params or {}},
                        human=human, evidence="Synthetic isolated setup authorization" if human else "")

    def call(self, method, params=None, human=False, root=None):
        value = self.raw(method, params, human, root)
        self.assertTrue(value["ok"], value)
        return value["result"]

    def create(self, version="manual", root=None):
        return self.call("setup.create", {"version": version}, human=True, root=root)

    def slot(self):
        return self.root / ".agents/skills/ljh-research"

    def test_plan_is_read_only_and_create_installs_exactly_one_project_variant(self):
        planned = self.call("setup.plan", {"version": "auto"})
        self.assertTrue(any("DEPLOY .agents/skills/ljh-research version=auto" == c for c in planned["changes"]))
        self.assertEqual(list(self.root.iterdir()), [])
        created = self.create("auto")
        self.assertEqual(Path(created["workspace"]).name, "ljh research docs")
        self.assertFalse((self.root / ".ljh-research").exists())
        self.assertFalse((self.root / "ljh research").exists())
        self.assertEqual([p.name for p in self.slot().parent.iterdir()], ["ljh-research"])
        marker = json.loads((self.slot() / ".deployment.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["research_version"], "auto")
        self.assertIn("name: ljh-research\n", (self.slot() / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(self.call("setup.validate")["skill_deployment"]["status"], "ready")

    def test_switch_replaces_one_slot_backs_up_and_preserves_other_project(self):
        self.create("manual")
        other = self.root.parent / "other"
        other.mkdir()
        self.create("manual", other)
        before = (other / ".agents/skills/ljh-research/SKILL.md").read_bytes()
        extra = self.slot() / "user-notes.txt"
        extra.write_text("preserve", encoding="utf-8")
        self.call("setup.version", {"version": "auto"}, human=True)
        self.assertIn("# LJH Research Auto", (self.slot() / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(extra.read_text(encoding="utf-8"), "preserve")
        self.assertEqual((other / ".agents/skills/ljh-research/SKILL.md").read_bytes(), before)
        self.assertTrue(list((self.root / "ljh research docs/.runtime/setup/skill-backups").glob("*.zip")))
        marker = self.slot() / ".deployment.json"
        unchanged_time = marker.stat().st_mtime_ns
        self.call("setup.deploy", {"version": "auto"}, human=True)
        self.assertEqual(marker.stat().st_mtime_ns, unchanged_time)

    def test_unmanaged_or_edited_skill_is_preserved_and_mode_stays_unchanged(self):
        self.slot().mkdir(parents=True)
        skill = self.slot() / "SKILL.md"
        skill.write_text("User-maintained skill", encoding="utf-8")
        denied = self.raw("setup.create", {"version": "auto"}, human=True)
        self.assertEqual(denied["error"]["code"], "deployment_conflict")
        self.assertFalse((self.root / "ljh research docs").exists())
        self.assertEqual(skill.read_text(encoding="utf-8"), "User-maintained skill")
        skill.unlink()
        self.create()
        changed = skill.read_bytes() + b"\nUser local change\n"
        skill.write_bytes(changed)
        self.assertEqual(self.raw("setup.version", {"version": "auto"}, human=True)["error"]["code"], "deployment_conflict")
        self.assertEqual(skill.read_bytes(), changed)
        self.assertEqual(self.call("workspace.get")["research_version"], "manual")

    def test_global_destination_is_rejected_without_writes(self):
        from ljh_research.errors import ResearchError
        with self.assertRaises(ResearchError) as caught:
            destination(Path.home())
        self.assertEqual(caught.exception.code, "global_deployment_forbidden")

    def test_deployed_launcher_binds_project_from_neutral_cwd_and_rejects_foreign_stdin(self):
        self.create()
        script = self.slot() / "scripts/research.py"
        result = subprocess.run([sys.executable, str(script), "workspace.get"], cwd=self.root.parent,
                                capture_output=True, encoding="utf-8")
        value = json.loads(result.stdout)
        self.assertTrue(value["ok"], value)
        self.assertEqual(value["result"]["project_root"], str(self.root))
        request = {"protocol_version": 1, "method": "task.list", "project_root": str(self.root.parent), "params": {}}
        wrong = subprocess.run([sys.executable, str(script)], input=json.dumps(request), cwd=self.root.parent,
                               capture_output=True, encoding="utf-8")
        self.assertEqual(json.loads(wrong.stdout)["error"]["code"], "project_binding")
        self.assertNotEqual(wrong.returncode, 0)

    def test_missing_managed_file_can_be_repaired(self):
        self.create("auto")
        (self.slot() / "scripts/research.py").unlink()
        self.assertEqual(self.call("setup.validate")["skill_deployment"]["status"], "outdated")
        self.call("setup.repair", human=True)
        self.assertEqual(self.call("setup.version")["skill_deployment"]["status"], "ready")
        self.assertEqual(self.call("setup.version")["research_version"], "auto")

    def legacy_fixture(self, name=".ljh-research"):
        self.create()
        task = self.call("task.create", {"title": "Saved evidence", "objective": "Preserve prior completed work",
            "authorization": {"allowed_roots": ["runs/fixture"], "max_runs": 0, "max_reasoning_calls": 3}})
        task_id = task["task"]["id"]
        self.call("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved"}, human=True)
        lease = self.call("task.claim", {"task_id": task_id, "driver_id": "fixture"})["lease"]
        self.call("reasoning.reserve", {"task_id": task_id, "lease": lease})
        self.call("task.complete", {"task_id": task_id, "lease": lease, "summary": "Bounded saved result"})
        docs = self.root / "ljh research docs"
        reference = docs / "legacy-reference.md"
        reference.write_text(f"[saved]({name}/tasks/{task_id}.md)\n", encoding="utf-8")
        with closing(sqlite3.connect(docs / ".runtime/tasks.sqlite3")) as db, db:
            data = json.loads(db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()[0])
            data["result_note"] = name + "/tasks/" + task_id + ".md"
            db.execute("UPDATE tasks SET data=? WHERE id=?", (json.dumps(data), task_id))
        docs.rename(self.root / name)
        return task_id

    def test_both_legacy_names_migrate_references_and_preserve_consumed_budget(self):
        for name in (".ljh-research", "ljh research"):
            with self.subTest(source=name), tempfile.TemporaryDirectory(prefix="ljh-migration-") as folder:
                previous = self.root
                self.root = Path(folder)
                try:
                    task_id = self.legacy_fixture(name)
                    self.assertTrue(any(c.startswith("STOP legacy workspace") for c in self.call("setup.plan")["changes"]))
                    self.assertFalse(self.raw("setup.create", human=True)["ok"])
                    self.assertFalse((self.root / "ljh research docs").exists())
                    migrated = self.call("setup.migrate", {"source": name}, human=True)
                    self.assertTrue((self.root / migrated["backup"]).is_file())
                    self.assertFalse((self.root / name).exists())
                    final = self.call("task.get", {"task_id": task_id})
                    self.assertEqual(final["reasoning_calls_used"], 1)
                    self.assertEqual(final["summary"], "Bounded saved result")
                    self.assertTrue(final["result_note"].startswith("ljh research docs/"))
                    self.assertIn("](<ljh research docs/", (self.root / "ljh research docs/legacy-reference.md").read_text(encoding="utf-8"))
                finally:
                    self.root = previous

    def test_migration_refuses_active_task_unowned_format_and_existing_destination(self):
        self.legacy_fixture()
        old = self.root / ".ljh-research"
        database = old / ".runtime/tasks.sqlite3"
        with closing(sqlite3.connect(database)) as db, db:
            key, raw = db.execute("SELECT id,data FROM tasks").fetchone()
            task = json.loads(raw)
            task["status"] = "running"
            db.execute("UPDATE tasks SET data=? WHERE id=?", (json.dumps(task), key))
        self.assertEqual(self.raw("setup.migrate", human=True)["error"]["code"], "workspace_busy")
        self.assertTrue(old.is_dir())
        (self.root / "ljh research docs").mkdir()
        self.assertEqual(self.raw("setup.migrate", human=True)["error"]["code"], "migration_conflict")
        (self.root / "ljh research docs").rmdir()
        (old / ".workspace.json").unlink()
        self.assertEqual(self.raw("setup.migrate", human=True)["error"]["code"], "unowned_workspace")

    def test_failed_migration_rolls_back_rename_and_original_metadata(self):
        self.legacy_fixture()
        original = (self.root / ".ljh-research/legacy-reference.md").read_bytes()
        with patch("ljh_research.setup.migrate._rewrite_database", side_effect=OSError("Synthetic write failure")):
            self.assertFalse(self.raw("setup.migrate", human=True)["ok"])
        self.assertFalse((self.root / "ljh research docs").exists())
        self.assertEqual((self.root / ".ljh-research/legacy-reference.md").read_bytes(), original)
        self.assertFalse((self.root / ".ljh-research-migration.lock").exists())


if __name__ == "__main__":
    unittest.main()
