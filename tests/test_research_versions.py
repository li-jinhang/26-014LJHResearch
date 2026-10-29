import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ljh_research.public import dispatch


class ResearchVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ljh-versions-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.call("setup.create", {"version": "manual"}, human=True)

    def raw(self, method, params=None, human=False):
        return dispatch({"protocol_version": 1, "project_root": str(self.root), "method": method, "params": params or {}},
                        human=human, evidence="Synthetic isolated test authorization" if human else "")

    def call(self, method, params=None, human=False):
        result = self.raw(method, params, human)
        self.assertTrue(result["ok"], result)
        return result["result"]

    def task(self, **auth):
        task = self.call("task.create", {"title": "Bounded test", "objective": "Answer the isolated test question",
            "authorization": {"allowed_roots": ["runs/check"], "allowed_programs": [sys.executable],
                "max_runs": 2, "max_reasoning_calls": 20, "max_run_seconds": 15, "max_task_seconds": 60, **auth}})
        self.call("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved"}, human=True)
        owner = self.call("task.claim", {"task_id": task["task"]["id"], "driver_id": "fixture"})
        return {"task_id": task["task"]["id"], "lease": owner["lease"]}

    def plan(self, owner, **changes):
        return self.call("research.record", {**owner, "record_key": "plan-1", "kind": "plan",
            "question": "Does the candidate beat the saved baseline?",
            "hypotheses": ["H1 predicts improvement over baseline", "H0 predicts no improvement"],
            "evidence": ["Saved baseline=1; deterministic fixture only"], "next_action": "Read one controlled probe",
            "expected_information": "Distinguish improvement from no improvement", "decision_rule": "Equal baseline supports only a limited negative result",
            "stop_rule": "Stop if this bounded question is answered", "run_keys": ["one-probe"], **changes})

    def analysis(self, owner, plan_id, **changes):
        return self.call("research.record", {**owner, "record_key": "analysis-1", "kind": "analysis", "plan_id": plan_id,
            "run_ids": [], "observations": "Saved evidence is sufficient for this bounded question", "credibility": "valid",
            "interpretation": "No additional execution is justified", "limitations": "This is a synthetic decision scenario",
            "decision": "stop", "next_action": "", "evidence": ["Saved controlled result"], **changes})

    def wait_run(self, run_id):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            run = self.call("run.refresh", {"run_id": run_id})
            if run["status"] in {"succeeded", "failed", "cancelled"}:
                return run
            time.sleep(.1)
        self.fail("Execution did not reach a verified terminal state")

    def test_setup_selects_one_source_and_freezes_existing_tasks(self):
        first = self.task(max_runs=0)
        self.assertEqual(self.call("workspace.get")["skill_name"], "ljh-research")
        self.assertEqual(self.raw("setup.version", {"version": "auto"})["error"]["code"], "human_required")
        self.call("setup.version", {"version": "auto"}, human=True)
        current = self.call("workspace.get")
        self.assertEqual(current["config"]["update_mode"], "automatic")
        self.assertEqual(current["research_version"], "auto")
        self.assertEqual(self.call("task.get", {"task_id": first["task_id"]})["research_version"], "manual")
        self.assertEqual(self.raw("workflow.get", {"task_id": first["task_id"], "version": "auto"})["error"]["code"], "version_mismatch")
        self.call("task.complete", {**first, "summary": "Manual scope delivered"})
        second = self.task(max_runs=0)
        self.assertEqual(self.call("task.get", {"task_id": second["task_id"]})["research_version"], "auto")

    def test_setup_cli_version_and_readable_guides_before_initialization(self):
        request = subprocess.run([sys.executable, "-m", "ljh_research.setup.cli", "version", "--project-root", str(self.root), "--select", "auto", "--approve"],
                                 capture_output=True, encoding="utf-8")
        self.assertEqual(request.returncode, 0, request.stderr)
        self.assertEqual(json.loads(request.stdout)["result"]["research_version"], "auto")
        value = dispatch({"protocol_version": 1, "project_root": str(self.root / "unprepared"), "method": "workflow.get", "params": {"version": "auto"}})
        self.assertTrue(value["ok"], value)
        self.assertTrue(value["result"]["content"])

    def test_manual_stop_kills_execution_and_fences_old_owner(self):
        owner = self.task()
        folder = self.root / "runs/check"
        folder.mkdir(parents=True)
        run = self.call("run.submit", {**owner, "request_key": "long", "argv": [sys.executable, "-c", "import time; from pathlib import Path; print('started',flush=True); time.sleep(12); Path('escaped.txt').write_text('bad')"], "cwd": "runs/check"})
        self.addCleanup(lambda: self.raw("task.stop", {"task_id": owner["task_id"], "reason": "Test cleanup"}, human=True))
        stopped = self.call("task.stop", {"task_id": owner["task_id"], "reason": "User says end this task"}, human=True)
        self.assertIn(stopped["task"]["status"], {"stopping", "cancelled"})
        self.assertEqual(self.wait_run(run["id"])["status"], "cancelled")
        self.assertEqual(self.call("task.get", {"task_id": owner["task_id"]})["status"], "cancelled")
        again = self.call("task.stop", {"task_id": owner["task_id"]}, human=True)
        self.assertTrue(again["termination_verified"])
        self.assertFalse((folder / "escaped.txt").exists())
        self.assertFalse(self.raw("task.claim", {"task_id": owner["task_id"], "driver_id": "old"})["ok"])
        self.assertFalse(self.raw("file.write", {**owner, "path": "runs/check/restarted.txt", "content": "bad"})["ok"])
        self.assertEqual(self.call("task.get", {"task_id": owner["task_id"]})["runs_used"], 1)

    def test_terminal_task_and_pending_decision_cannot_resurrect(self):
        owner = self.task(max_runs=0)
        decision = self.call("decision.request", {**owner, "kind": "research_decision", "payload": {"question": "Need data"}})
        self.assertEqual(self.raw("task.claim", {"task_id": owner["task_id"], "driver_id": "bypass"})["error"]["code"], "decision_pending")
        self.call("task.stop", {"task_id": owner["task_id"]}, human=True)
        self.assertFalse(self.raw("decision.resolve", {"decision_id": decision["id"], "decision": "approved"}, human=True)["ok"])
        self.assertFalse(self.raw("task.pause", {"task_id": owner["task_id"]}, human=True)["ok"])
        other = self.task(max_runs=0)
        self.call("task.finish", {**other, "outcome": "blocked", "summary": "Required data is absent; current bounded task is sealed"})
        self.assertFalse(self.raw("task.claim", {"task_id": other["task_id"], "driver_id": "retry"})["ok"])
        self.assertFalse(self.raw("task.cancel", {"task_id": other["task_id"]}, human=True)["ok"])

    def test_manual_cannot_launch_continuous_controller(self):
        owner = self.task(max_runs=0)
        self.call("task.pause", {"task_id": owner["task_id"]}, human=True)
        self.assertEqual(self.raw("controller.start", {"task_id": owner["task_id"]}, human=True)["error"]["code"], "manual_task")

    def test_manual_can_use_an_explicitly_bound_custom_bounded_controller(self):
        self.call("settings.update", {"controller": {"command": [sys.executable, "bounded_controller.py"], "supported_versions": ["manual"]}}, human=True)
        owner = self.task(max_runs=0)
        self.call("task.pause", {"task_id": owner["task_id"]}, human=True)
        with patch("ljh_research.service.plugin_call", return_value={"driver": "bounded-custom"}) as plugin:
            self.assertEqual(self.call("controller.start", {"task_id": owner["task_id"]}, human=True)["driver"], "bounded-custom")
        self.assertEqual(plugin.call_args.args[1], "start")

    def test_deadline_bounds_process_and_does_not_reset_on_resume(self):
        owner = self.task(max_task_seconds=3)
        expires = self.call("task.get", {"task_id": owner["task_id"]})["expires_at"]
        self.call("task.pause", {"task_id": owner["task_id"]}, human=True)
        owner = {"task_id": owner["task_id"], "lease": self.call("task.claim", {"task_id": owner["task_id"], "driver_id": "resume"})["lease"]}
        self.assertEqual(self.call("task.get", {"task_id": owner["task_id"]})["expires_at"], expires)
        (self.root / "runs/check").mkdir(parents=True)
        run = self.call("run.submit", {**owner, "request_key": "deadline", "argv": [sys.executable, "-c", "import time; time.sleep(12)"], "cwd": "runs/check"})
        self.assertLessEqual(run["timeout_seconds"], 3)
        self.assertEqual(self.wait_run(run["id"])["status"], "failed")
        time.sleep(max(0, expires - time.time() + .05))
        self.assertEqual(self.call("task.get", {"task_id": owner["task_id"]})["status"], "failed")

    def test_unknown_cancellation_stays_stopping_until_reconciled(self):
        owner = self.task()
        (self.root / "runs/check").mkdir(parents=True)
        with patch("ljh_research.service.plugin_call", side_effect=lambda command, method, params: {"status": "unknown"}):
            run = self.call("run.submit", {**owner, "request_key": "uncertain", "argv": [sys.executable, "probe.py"], "cwd": "runs/check"})
            result = self.call("task.stop", {"task_id": owner["task_id"]}, human=True)
        self.assertFalse(result["termination_verified"])
        self.assertEqual(result["task"]["status"], "stopping")
        self.assertIn(run["id"], result["outstanding_run_ids"])
        self.call("run.reconcile", {"run_id": run["id"], "status": "cancelled"}, human=True)
        self.assertEqual(self.call("task.get", {"task_id": owner["task_id"]})["status"], "cancelled")

    def test_stop_racing_with_submission_also_cancels_late_acknowledgment(self):
        owner = self.task()
        (self.root / "runs/check").mkdir(parents=True)
        submitted, release = threading.Event(), threading.Event()
        state = {"launched": False, "cancelled": False}
        def plugin(command, method, params):
            if method == "submit":
                submitted.set()
                if not release.wait(5):
                    raise RuntimeError("Test deadlock")
                state["launched"] = True
                return {"status": "running"}
            if method == "cancel" and state["launched"]:
                state["cancelled"] = True
            return {"status": "cancelled" if state["cancelled"] else "unknown"}
        result = []
        with patch("ljh_research.service.plugin_call", side_effect=plugin):
            thread = threading.Thread(target=lambda: result.append(self.raw("run.submit", {**owner, "request_key": "racing", "argv": [sys.executable, "probe.py"], "cwd": "runs/check"})))
            thread.start()
            try:
                self.assertTrue(submitted.wait(5))
                self.assertEqual(self.call("task.stop", {"task_id": owner["task_id"]}, human=True)["task"]["status"], "stopping")
            finally:
                release.set()
                thread.join(6)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result[0]["ok"], result)
        self.assertTrue(state["cancelled"])
        self.assertEqual(self.call("task.get", {"task_id": owner["task_id"]})["status"], "cancelled")

    def test_auto_requires_plan_analysis_and_can_finish_on_credible_negative(self):
        self.call("setup.version", {"version": "auto"}, human=True)
        owner = self.task()
        (self.root / "runs/check").mkdir(parents=True)
        args = {**owner, "request_key": "one-probe", "argv": [sys.executable, "-c", "print('baseline=1 candidate=1')"], "cwd": "runs/check"}
        self.assertEqual(self.raw("run.submit", args)["error"]["code"], "research_plan_required")
        plan = self.plan(owner)
        self.assertEqual(self.plan(owner)["id"], plan["id"])
        self.assertFalse(self.raw("research.record", {**owner, **{k:v for k,v in plan.items() if k not in {"id","recorded_at"}}, "record_key":"another"})["ok"])
        run = self.call("run.submit", {**args, "plan_id": plan["id"]})
        self.assertEqual(self.wait_run(run["id"])["status"], "succeeded")
        self.assertIn("baseline=1", self.call("run.logs", {"run_id": run["id"]})["stdout"])
        self.assertEqual(self.raw("task.complete", {**owner, "summary": "Premature"})["error"]["code"], "analysis_required")
        self.analysis(owner, plan["id"], run_ids=[run["id"]], observations="baseline=1 candidate=1", interpretation="No gain in this bounded fixture; no claim about the entire direction")
        self.assertFalse(self.raw("run.submit", {**args, "request_key": "extra", "plan_id": plan["id"]})["ok"])
        self.call("task.complete", {**owner, "summary": "Candidate did not beat baseline under this fixture; no further informative run is justified"})
        final = self.call("task.get", {"task_id": owner["task_id"]})
        self.assertEqual(final["runs_used"], 1)
        self.assertEqual(final["status"], "completed")

    def test_saved_evidence_can_answer_auto_task_without_new_training(self):
        self.call("setup.version", {"version": "auto"}, human=True)
        owner = self.task(max_runs=0)
        plan = self.plan(owner, run_keys=[])
        self.analysis(owner, plan["id"])
        self.call("task.complete", {**owner, "summary": "Saved evidence answers the question; no new run"})
        context = self.call("research.context", {"task_id": owner["task_id"]})
        self.assertEqual([r["kind"] for r in context["records"]], ["plan", "analysis"])
        self.assertEqual(self.call("task.get", {"task_id": owner["task_id"]})["runs_used"], 0)

    def test_context_preserves_source_identity_and_discloses_truncation(self):
        source = self.root / "ljh research docs/known-evidence.md"
        source.write_text("known result\n" + "x" * 5000, encoding="utf-8")
        created = self.call("task.create", {"title": "Context recovery", "objective": "Reuse known evidence",
            "evidence_paths": ["ljh research docs/known-evidence.md"],
            "authorization": {"allowed_roots": ["runs/check"], "max_runs": 0}})
        initial = self.call("research.context", {"task_id": created["task"]["id"]})
        self.assertNotIn("content", initial["evidence"][0])
        context = self.call("research.context", {"task_id": created["task"]["id"], "include_evidence": True})
        excerpt = context["evidence"][0]
        self.assertTrue(excerpt["truncated"])
        self.assertEqual(len(excerpt["content"]), 4000)
        full = self.call("file.read", {"path": excerpt["path"]})
        self.assertEqual(full["sha256"], excerpt["sha256"])
        self.assertEqual(len(full["content"]), len(source.read_text(encoding="utf-8")))

    def test_unperformed_plan_cannot_be_called_a_valid_result(self):
        self.call("setup.version", {"version": "auto"}, human=True)
        owner = self.task(max_runs=0)
        plan = self.plan(owner)
        result = self.raw("research.record", {**owner, "record_key": "bad-valid", "kind": "analysis", "plan_id": plan["id"],
            "run_ids": [], "observations": "No execution occurred", "credibility": "valid", "interpretation": "Cannot validate",
            "limitations": "No data", "decision": "stop", "next_action": "", "evidence": []})
        self.assertEqual(result["error"]["code"], "incomplete_plan")
        self.analysis(owner, plan["id"], credibility="partial", observations="The intended run was not performed",
                      interpretation="Budget is insufficient; no scientific refutation")
        self.call("task.finish", {**owner, "outcome": "blocked", "summary": "No evidence to test this hypothesis"})


if __name__ == "__main__":
    unittest.main()
