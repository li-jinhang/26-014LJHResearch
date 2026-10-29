"""Deterministic protocol demonstrator, explicitly not a scientific model."""
import json
import sys

if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
request = json.load(sys.stdin)
context = request["context"]
task = context["task"]
root = task["authorization"]["allowed_roots"][0]
program = task["authorization"]["allowed_programs"][0]
records = context["research"]["records"]
plan = next((r for r in reversed(records) if r["kind"] == "plan"), None)
if not plan:
    action, params = "research.record", {"record_key": "demo-plan", "kind": "plan",
        "question": "Can the protocol execute one UTF-8 process and preserve its result?",
        "hypotheses": ["H1: protocol preserves UTF-8; stdout contains the checkmark", "H0: encoding or execution fails; stdout lacks the expected text"],
        "evidence": ["Deterministic interface fixture, no scientific investigation"], "next_action": "Create and run one short UTF-8 probe",
        "expected_information": "Whether this local protocol path works", "decision_rule": "Read actual stdout; report interface scope only",
        "stop_rule": "Stop after this single probe is analyzed", "run_keys": ["demo-probe-once"]}
elif not context["runs"] and not any(o.get("proposal", {}).get("action") == "file.write" and "result" in o for o in context["observations"]):
    action, params = "file.write", {"path": root + "/probe.py", "content": "print('接口闭环验证：UTF-8 ✓')\n"}
elif not context["runs"]:
    action, params = "run.submit", {"request_key": "demo-probe-once", "plan_id": plan["id"], "argv": [program, "probe.py"], "cwd": root}
elif records[-1]["kind"] == "plan":
    action, params = "research.record", {"record_key": "demo-analysis", "kind": "analysis", "plan_id": plan["id"],
        "run_ids": [r["id"] for r in context["runs"]], "evidence": [r["id"] for r in context["runs"]],
        "observations": json.dumps([r.get("logs", {}) for r in context["runs"]], ensure_ascii=False), "credibility": "valid",
        "interpretation": "这是一项接口与执行流程验证，运行输出由真实短进程生成。", "limitations": "未调用科研模型，不能作为科学结论。",
        "decision": "stop", "next_action": ""}
else:
    action, params = "task.complete", {"summary": "已验证面板、任务授权、控制模块、本地执行和结果查看的连接。仅为确定性接口演示，未开展科学研究。"}
print(json.dumps({"action": action, "arguments": json.dumps(params, ensure_ascii=False), "rationale": "Deterministic interface demonstration"}, ensure_ascii=False))
