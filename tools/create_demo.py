"""Create an explicitly labeled local demo; leaves its authorization pending."""
import json
from pathlib import Path
import sys
from ljh_research.public import dispatch

root = Path(__file__).resolve().parents[1]
project = root / ".local/demo-project"
project.mkdir(parents=True, exist_ok=True)


def call(method, params=None, human=False):
    value = dispatch({"protocol_version": 1, "project_root": str(project), "method": method, "params": params or {}},
                     human=human, evidence="User authorized implementation verification in this isolated demo" if human else "")
    if not value["ok"]:
        raise RuntimeError(value)
    return value["result"]


if not (project / "ljh research docs").exists():
    call("setup.create", {"version": "auto"}, human=True)
call("setup.version", {"version": "auto"}, human=True)
call("config.update", {"key": "domain", "value": "科研工具接口验证"}, human=True)
call("config.update", {"key": "experiments_dir", "value": "runs"}, human=True)
call("settings.update", {"reasoning": {"kind": "command", "command": [sys.executable, str(root / "examples/demo_reasoning.py")], "timeout_seconds": 30}}, human=True)
created = call("task.create", {"title": "公开接口闭环演示", "objective": "验证授权、控制模块、UTF-8 执行与结果查看；不进行科学研究。",
    "authorization": {"allowed_roots": ["runs/demo"], "allowed_programs": [sys.executable], "max_runs": 1, "max_reasoning_calls": 6, "max_run_seconds": 15}})
(root / ".local/demo-task.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"project_root": str(project), "task_id": created["task"]["id"], "decision_id": created["decision"]["id"], "authorization": "pending"}, ensure_ascii=False))
