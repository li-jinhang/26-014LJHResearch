import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from ljh_research.public import dispatch


class ControllerTests(unittest.TestCase):
    def test_controller_reads_memory_and_writes_back_grounded_semantics(self):
        with tempfile.TemporaryDirectory(prefix="ljh-memory-controller-") as folder:
            root = Path(folder)
            def call(method, params=None, human=False):
                result = dispatch({"protocol_version": 1, "project_root": str(root), "method": method, "params": params or {}},
                                  human=human, evidence="Isolated deterministic memory-driver test" if human else "")
                self.assertTrue(result["ok"], result)
                return result["result"]
            call("setup.create", {"version": "auto"}, human=True)
            (root / "fixture.md").write_text("# Lesson\n\n## Result\n\nThe fixture records delayed reward under a fixed protocol.\n", encoding="utf-8")
            obj = call("memory.import", {"kind": "experience", "title": "Delayed reward fixture", "path": "fixture.md", "topics": ["强化学习"]}, human=True)
            provider = root / "provider.py"
            provider.write_text('''import json,sys
sys.stdin.reconfigure(encoding="utf-8"); sys.stdout.reconfigure(encoding="utf-8")
c=json.load(sys.stdin)["context"]; n=c["reasoning_call"]
last=c["observations"][-1]["result"] if c["observations"] else {}
if n==1:
 action,args="memory.search",{"query":"delayed reward","budget_chars":2000}
elif n==2:
 action,args="memory.read",{"id":last["hits"][0]["id"],"budget_chars":5000}
elif n==3:
 action,args="memory.read",{"id":last["id"],"view":"detail","source_id":"S01","section":"Result"}
elif n==4:
 citation={k:last[k] for k in ["source_id","source_sha256","start_line","end_line"]}; citation["quote"]="The fixture records delayed reward under a fixed protocol."
 action,args="memory.extract",{"id":last["id"],"claims":[{"text":"This fixture describes delayed reward.","aspect":"lesson","evidence_type":"agent_inference","conditions":["Deterministic protocol fixture only"],"keywords":["delayed reward"],"citations":[citation]}]}
elif n==5:
 action,args="research.record",{"record_key":"fixture-plan","kind":"plan","question":"Can existing memory answer this fixture?","hypotheses":["Known evidence is sufficient","A new run is needed"],"evidence":["Registered fixture"],"next_action":"Use saved evidence","expected_information":"No new execution required","decision_rule":"Read actual source first","stop_rule":"Stop after source-grounded writeback","run_keys":[]}
elif n==6:
 action,args="research.record",{"record_key":"fixture-analysis","kind":"analysis","plan_id":c["research"]["records"][-1]["id"],"run_ids":[],"observations":"Existing source was read","credibility":"valid","interpretation":"No new execution is needed for this fixture","limitations":"Not a scientific model evaluation","decision":"stop","next_action":"","evidence":["Registered fixture"]}
else:
 action,args="task.complete",{"summary":"Memory protocol fixture completed without scientific training"}
print(json.dumps({"action":action,"arguments":json.dumps(args),"rationale":"Deterministic contract verification"}))
''', encoding="utf-8")
            call("settings.update", {"reasoning": {"kind": "command", "command": [sys.executable, str(provider)], "timeout_seconds": 10}}, human=True)
            task = call("task.create", {"title": "Memory protocol", "objective": "Read delayed reward evidence and update memory",
                "authorization": {"allowed_roots": ["runs"], "max_runs": 0, "max_reasoning_calls": 8}})
            call("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved"}, human=True)
            from ljh_research_controller.__main__ import run
            run(root, task["task"]["id"], "memory-fixture")
            final = call("task.get", {"task_id": task["task"]["id"]})
            self.assertEqual(final["status"], "completed")
            self.assertEqual(final["runs_used"], 0)
            self.assertEqual(final["reasoning_calls_used"], 7)
            self.assertEqual(call("memory.read", {"id": obj["id"]})["extraction"], "agent_semantic")

    def test_reasoning_exhaustion_seals_without_automatic_budget_extension(self):
        with tempfile.TemporaryDirectory(prefix="ljh-budget-stop-") as folder:
            root = Path(folder)
            def call(method, params=None, human=False):
                result = dispatch({"protocol_version": 1, "project_root": str(root), "method": method, "params": params or {}},
                                  human=human, evidence="Synthetic isolated approval" if human else "")
                self.assertTrue(result["ok"], result)
                return result["result"]
            call("setup.create", {"version": "auto"}, human=True)
            provider = Path(__file__).resolve().parents[1] / "examples/demo_reasoning.py"
            call("settings.update", {"reasoning": {"kind": "command", "command": [sys.executable, str(provider)], "timeout_seconds": 15}}, human=True)
            task = call("task.create", {"title": "Budget boundary", "objective": "Preserve partial work without another model call",
                "authorization": {"allowed_roots": ["runs/demo"], "allowed_programs": [sys.executable], "max_runs": 1, "max_reasoning_calls": 1, "max_run_seconds": 10}})
            task_id = task["task"]["id"]
            call("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved"}, human=True)
            from ljh_research_controller.__main__ import run
            run(root, task_id, "budget-fixture")
            final = call("task.get", {"task_id": task_id})
            self.assertEqual(final["status"], "blocked")
            self.assertEqual(final["reasoning_calls_used"], 1)
            self.assertEqual(final["runs_used"], 0)
            self.assertEqual(len(call("research.context", {"task_id": task_id})["records"]), 1)
            self.assertFalse(any(d["kind"] == "budget_extension" for d in call("decision.list", {"task_id": task_id})))

    @unittest.skipUnless(shutil.which("node"), "Node is optional, used only to verify a foreign-language plugin")
    def test_external_javascript_controller_binding_is_used(self):
        with tempfile.TemporaryDirectory(prefix="ljh-foreign-driver-") as folder:
            root = Path(folder)
            def call(method, params=None, human=False):
                value = dispatch({"protocol_version": 1, "project_root": str(root), "method": method, "params": params or {}},
                                 human=human, evidence="Synthetic plugin test approval" if human else "")
                self.assertTrue(value["ok"], value)
                return value["result"]
            call("setup.create", {"version": "auto"}, human=True)
            plugin = root / "foreign-controller.mjs"
            plugin.write_text("let raw=''; for await (const chunk of process.stdin) raw+=chunk; const r=JSON.parse(raw); console.log(JSON.stringify({protocol_version:1,request_id:r.request_id,ok:true,result:{driver:'javascript',method:r.method,task_id:r.params.task_id}}));", encoding="utf-8")
            call("settings.update", {"controller": {"command": [shutil.which("node"), str(plugin)]}}, human=True)
            task = call("task.create", {"title": "Foreign controller", "objective": "Use a language-neutral plugin",
                "authorization": {"allowed_roots": ["runs/foreign"], "allowed_programs": [], "max_runs": 0}})
            call("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved"}, human=True)
            result = call("controller.start", {"task_id": task["task"]["id"]}, human=True)
            self.assertEqual(result["driver"], "javascript")
            self.assertEqual(result["method"], "start")

    def test_reference_controller_executes_public_demo_without_a_real_model(self):
        with tempfile.TemporaryDirectory(prefix="ljh-controller-") as folder:
            root = Path(folder)
            def call(method, params=None, human=False):
                value = dispatch({"protocol_version": 1, "project_root": str(root), "method": method, "params": params or {}},
                                 human=human, evidence="Synthetic test approval" if human else "")
                self.assertTrue(value["ok"], value)
                return value["result"]
            call("setup.create", {"version": "auto"}, human=True)
            provider = Path(__file__).resolve().parents[1] / "examples/demo_reasoning.py"
            call("settings.update", {"reasoning": {"kind": "command", "command": [sys.executable, str(provider)], "timeout_seconds": 15}}, human=True)
            task = call("task.create", {"title": "Protocol demo", "objective": "No scientific model is called",
                "authorization": {"allowed_roots": ["runs/demo"], "allowed_programs": [sys.executable], "max_runs": 1, "max_reasoning_calls": 6, "max_run_seconds": 10}})
            call("decision.resolve", {"decision_id": task["decision"]["id"], "decision": "approved"}, human=True)
            started = call("controller.start", {"task_id": task["task"]["id"]}, human=True)
            self.assertNotIn("ljh research docs", started["log"])
            deadline = time.time() + 30
            while time.time() < deadline:
                final = call("task.get", {"task_id": task["task"]["id"]})
                if final["status"] == "completed":
                    break
                time.sleep(.2)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(final["runs_used"], 1)
            self.assertEqual(final["reasoning_calls_used"], 5)
            self.assertIsNone(final["owner"])
            self.assertIn("未开展科学研究", final["summary"])
            self.assertTrue((root / final["result_note"]).is_file())


if __name__ == "__main__":
    unittest.main()
