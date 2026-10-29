import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from ljh_research.public import dispatch


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ljh-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.call("setup.create", human=True)

    def raw(self, method, params=None, human=False):
        return dispatch({"protocol_version": 1, "project_root": str(self.root), "method": method, "params": params or {}},
                        human=human, evidence="Synthetic test approval" if human else "")

    def call(self, method, params=None, human=False):
        value = self.raw(method, params, human)
        self.assertTrue(value["ok"], value)
        return value["result"]

    def task(self, approve=True, max_runs=2):
        created = self.call("task.create", {"title": "Controlled test", "objective": "Verify runtime contracts",
            "authorization": {"allowed_roots": ["runs/test"], "allowed_programs": [sys.executable],
                              "max_runs": max_runs, "max_reasoning_calls": 8, "max_run_seconds": 15}})
        if approve:
            self.call("decision.resolve", {"decision_id": created["decision"]["id"], "decision": "approved"}, human=True)
        return created

    def claim(self, task_id, driver="agent"):
        return self.call("task.claim", {"task_id": task_id, "driver_id": driver})

    def test_driver_cannot_approve_or_claim_without_user_authorization(self):
        task = self.task(approve=False)
        denied = self.raw("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved", "human": True})
        self.assertEqual(denied["error"]["code"], "human_required")
        self.assertFalse(self.raw("task.claim", {"task_id": task["task"]["id"], "driver_id": "x"})["ok"])

    def test_malformed_authorization_is_a_structured_error(self):
        result = self.raw("task.create", {"title": "bad", "objective": "bad", "authorization": []})
        self.assertEqual(result["error"]["code"], "invalid_authorization")

    def test_single_owner_atomic_claim_and_single_workspace_queue(self):
        first, second = self.task(), self.task()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda name: self.raw("task.claim", {"task_id": first["task"]["id"], "driver_id": name}), ["a", "b"]))
        self.assertEqual(sum(x["ok"] for x in results), 1)
        denied = self.raw("task.claim", {"task_id": second["task"]["id"], "driver_id": "c"})
        self.assertEqual(denied["error"]["code"], "workspace_busy")

    def test_explicit_takeover_fences_previous_owner_and_preserves_budget(self):
        task_id = self.task()["task"]["id"]
        first = self.claim(task_id)
        self.call("reasoning.reserve", {"task_id": task_id, "lease": first["lease"]})
        self.assertFalse(self.raw("task.claim", {"task_id": task_id, "driver_id": "other", "takeover": True})["ok"])
        second = self.call("task.claim", {"task_id": task_id, "driver_id": "other", "takeover": True}, human=True)
        denied = self.raw("reasoning.reserve", {"task_id": task_id, "lease": first["lease"]})
        self.assertEqual(denied["error"]["code"], "not_owner")
        self.assertEqual(second["task"]["reasoning_calls_used"], 1)

    def test_configuration_snapshot_and_path_revision_guards(self):
        task_id = self.task()["task"]["id"]
        owner = self.claim(task_id)
        self.call("config.update", {"key": "framework", "value": "new-default"}, human=True)
        self.assertIsNone(self.call("task.get", {"task_id": task_id})["config_snapshot"]["framework"])
        base = {"task_id": task_id, "lease": owner["lease"], "content": "first"}
        self.assertFalse(self.raw("file.write", {**base, "path": "../outside.txt"})["ok"])
        first = self.call("file.write", {**base, "path": "runs/test/file.txt"})
        denied = self.raw("file.write", {**base, "path": "runs/test/file.txt", "content": "second"})
        self.assertEqual(denied["error"]["code"], "revision_conflict")
        self.call("file.write", {**base, "path": "runs/test/file.txt", "content": "second", "expected_sha256": first["sha256"]})

    def test_execution_survives_driver_pause_and_submission_is_idempotent(self):
        task_id = self.task(max_runs=1)["task"]["id"]
        owner = self.claim(task_id)
        (self.root / "runs/test").mkdir(parents=True)
        params = {"task_id": task_id, "lease": owner["lease"], "request_key": "one",
                  "argv": [sys.executable, "-c", "import time; time.sleep(1); print('结果恢复 ✓ real-run-finished')"], "cwd": "runs/test"}
        run = self.call("run.submit", params)
        again = self.call("run.submit", params)
        self.assertEqual(run["id"], again["id"])
        changed = self.raw("run.submit", {**params, "timeout_seconds": 5})
        self.assertEqual(changed["error"]["code"], "idempotency_conflict")
        self.assertEqual(self.call("task.get", {"task_id": task_id})["runs_used"], 1)
        denied = self.raw("run.submit", {**params, "request_key": "second"})
        self.assertEqual(denied["error"]["code"], "budget_exhausted")
        self.call("task.pause", {"task_id": task_id}, human=True)
        deadline = time.time() + 15
        while time.time() < deadline:
            current = self.call("run.refresh", {"run_id": run["id"]})
            if current["status"] in {"succeeded", "failed"}:
                break
            time.sleep(.3)
        self.assertEqual(current["status"], "succeeded", current)
        self.assertIn("real-run-finished", self.call("run.logs", {"run_id": run["id"]})["stdout"])
        self.assertEqual(self.call("task.get", {"task_id": task_id})["status"], "paused")

    def test_cli_protocol_is_json_without_human_text(self):
        request = {"protocol_version": 1, "request_id": "test", "project_root": str(self.root), "method": "task.list", "params": {}}
        result = subprocess.run([sys.executable, "-m", "ljh_research.cli"], input=json.dumps(request), capture_output=True, encoding="utf-8")
        parsed = json.loads(result.stdout)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["request_id"], "test")


if __name__ == "__main__":
    unittest.main()
