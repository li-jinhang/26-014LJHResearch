import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from ljh_research.public import Client, ResearchError
from .providers import propose


def run(root, task_id, driver_id):
    client = Client(root)
    snapshot = client.call("task.get", task_id=task_id)
    if snapshot.get("research_version", "manual") != "auto":
        raise ValueError("The continuous research controller requires an auto task; use bounded agent actions for manual")
    binding = snapshot["bindings_snapshot"]["reasoning"]
    if not binding.get("command"):
        raise ValueError("Configure a reasoning provider before starting this task")
    claimed = client.call("task.claim", task_id=task_id, driver_id=driver_id)
    lease = claimed["lease"]
    last_heartbeat = time.monotonic()
    observations = snapshot.get("recent_observations", [])
    try:
        while True:
            task = client.call("task.get", task_id=task_id)
            if task["status"] != "running" or task["owner"] != driver_id:
                return
            if time.monotonic() - last_heartbeat > 30:
                client.call("task.heartbeat", task_id=task_id, lease=lease)
                last_heartbeat = time.monotonic()
            runs = [client.call("run.refresh", run_id=r["id"]) for r in task["runs"]]
            if any(r["status"] in {"unknown", "submitting"} for r in runs):
                client.call("decision.request", task_id=task_id, lease=lease, kind="execution_reconciliation",
                            payload={"message": "Verify uncertain execution before further research", "runs": runs})
                return
            if any(r["status"] == "running" for r in runs):
                time.sleep(1)
                continue
            for item in runs:
                item["logs"] = client.call("run.logs", run_id=item["id"])
            workspace = client.call("workspace.get")
            context = {"task": task, "runs": runs, "observations": observations[-6:],
                       "workspace": {k:v for k,v in workspace.items() if k != "cards"},
                       "research": client.call("research.context", task_id=task_id),
                       "decisions": client.call("decision.list", task_id=task_id)}
            try:
                reservation = client.call("reasoning.reserve", task_id=task_id, lease=lease)
            except ResearchError as exc:
                if exc.code == "budget_exhausted":
                    client.call("task.stop", task_id=task_id, lease=lease, outcome="blocked",
                                reason="Reasoning budget exhausted. Preserved existing evidence; final scientific analysis may be incomplete. Any further work needs a concrete user-authorized task.")
                    return
                raise
            context["reasoning_call"] = reservation["call"]
            heartbeat_stop = threading.Event()
            heartbeat_errors = []
            def keep_lease():
                while not heartbeat_stop.wait(30):
                    try:
                        client.call("task.heartbeat", task_id=task_id, lease=lease)
                    except Exception as exc:
                        heartbeat_errors.append(exc)
                        return
            heartbeat_thread = threading.Thread(target=keep_lease, daemon=True)
            heartbeat_thread.start()
            try:
                proposal = propose(binding, context, root)
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=5)
            if heartbeat_errors:
                raise heartbeat_errors[0]
            # Every action is checked by the same public core as coding-agent actions.
            params = {**proposal["arguments"], "task_id": task_id, "lease": lease}
            try:
                result = client.call(proposal["action"], **params)
                observations.append({"proposal": proposal, "result": result})
            except ResearchError as exc:
                observations.append({"proposal": proposal, "error": {"code": exc.code, "message": str(exc)}})
            if proposal["action"] in {"decision.request", "task.complete", "task.finish", "task.stop", "task.pause"} and "result" in observations[-1]:
                return
            observation = observations[-1]
            if len(json.dumps(observation, ensure_ascii=False)) <= 40000:
                client.call("reasoning.record", task_id=task_id, lease=lease, observation=observation)
    except Exception as exc:
        try:
            client.call("task.pause", task_id=task_id, lease=lease, reason=str(exc)[:4000])
        except Exception:
            pass
        raise


def launch(root, task_id):
    """Public controller launcher used by any upstream interface."""
    task = Client(root).call("task.get", task_id=task_id)
    if not task["bindings_snapshot"]["reasoning"].get("command"):
        raise ValueError("Configure a reasoning provider before creating a reference-controller task")
    if os.name == "nt":
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "LJHResearch/controller-logs"
    else:
        folder = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "ljh-research/controller-logs"
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / (task_id + ".log")
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with log.open("ab") as stream:
        process = subprocess.Popen([sys.executable, "-m", "ljh_research_controller", "--project-root", str(root), "--task", task_id],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, close_fds=True, **options)
    return {"pid": process.pid, "log": str(log), "task_id": task_id}


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if len(sys.argv) == 1:
        request = {}
        try:
            request = json.load(sys.stdin)
            if request.get("protocol_version") != 1 or request.get("method") != "start":
                raise ValueError("Expected controller protocol v1 start request")
            params = request["params"]
            result = {"ok": True, "result": launch(Path(params["project_root"]).resolve(), params["task_id"])}
        except (ValueError, KeyError, OSError, ResearchError) as exc:
            result = {"ok": False, "error": {"message": str(exc)}}
        result.update(protocol_version=1, request_id=request.get("request_id"))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1
    parser = argparse.ArgumentParser(description="Replaceable LJH Research reference controller")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    try:
        if args.background:
            result = launch(Path(args.project_root).resolve(), args.task)
        else:
            run(Path(args.project_root).resolve(), args.task, "reference:" + str(os.getpid()))
            result = {"task_id": args.task, "status": "controller_exited"}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, ResearchError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
