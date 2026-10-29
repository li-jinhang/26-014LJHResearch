"""Application operations. All drivers and HTTP adapters use this same boundary."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

from .errors import ResearchError, require
from .store import Store, identity
from .plugins import call as plugin_call
from .knowledge.project_conventions import load as load_config, update as update_config
from .knowledge.profile_config import resolve_project_relative
from .workspace_contract import require_owned_workspace, parse_frontmatter
from . import workflow


TERMINAL = {"succeeded", "failed", "cancelled"}
TASK_TERMINAL = {"completed", "cancelled", "failed", "blocked"}


class Service:
    def __init__(self, root, human=False, evidence=""):
        self.root = Path(root).expanduser().resolve()
        self.workspace = require_owned_workspace(self.root)
        self.store = Store(self.root)
        self.human = human
        self.evidence = evidence

    def human_only(self):
        require(self.human and self.evidence.strip(), "human_required", "Explicit user decision evidence is required")

    def path(self, value, roots=None):
        require(isinstance(value, str) and value and value != ".", "invalid_path", "A project-relative path is required")
        try:
            path = resolve_project_relative(self.root, value, key="path")
        except ValueError as exc:
            raise ResearchError("invalid_path", str(exc)) from exc
        if roots is not None:
            permitted = [resolve_project_relative(self.root, r, key="allowed_root") for r in roots]
            require(any(path == r or r in path.parents for r in permitted), "outside_authorization", "Path is outside task authorization")
            require(self.workspace != path and self.workspace not in path.parents, "protected_path", "Use research operations to update workspace records")
        return path

    def settings(self, db):
        try:
            data = self.store.get(db, "settings", "bindings")
            data.setdefault("controller", {"command": [sys.executable, "-m", "ljh_research_controller"]})
            return data
        except ResearchError as exc:
            if exc.code != "not_found":
                raise
            return {"id": "bindings", "executor": {"command": [sys.executable, "-m", "ljh_research_local"]},
                    "controller": {"command": [sys.executable, "-m", "ljh_research_controller"]},
                    "reasoning": {"kind": "command", "command": [], "timeout_seconds": 120}}

    def checked_owner(self, db, params, authorized=True):
        task = self.store.get(db, "tasks", params["task_id"])
        require(task["status"] not in TASK_TERMINAL, "task_terminal", "Task has already ended")
        require(params.get("lease") and secrets.compare_digest(task.get("lease", ""), params["lease"]),
                "not_owner", "Claim the task or explicitly take over before acting")
        require(task.get("lease_until", 0) > time.time(), "lease_expired", "Renew or explicitly take over the task")
        require(task["status"] == "running", "task_not_running", "Task is not accepting new actions")
        require(not task.get("expires_at") or time.time() < task["expires_at"], "task_deadline", "Authorized task deadline reached")
        if authorized:
            require(task.get("authorized"), "authorization_required", "Task authorization has not been approved")
            require(not task.get("revoked"), "authorization_revoked", "Task authorization was revoked")
        return task

    @staticmethod
    def public_task(task):
        data = {k: v for k, v in task.items() if k != "lease"}
        data["driver_online"] = bool(task.get("lease") and task.get("lease_until", 0) > time.time() and task["status"] == "running")
        return data

    def dispatch(self, method, p):
        # No always-on scheduler is required: expired tasks fence actions on access.
        # Submitted process timeouts are also capped by this persisted deadline.
        if p.get("task_id") and method != "task.stop":
            with self.store.transaction() as db:
                task = self.store.get(db, "tasks", p["task_id"])
            if task.get("expires_at") and time.time() >= task["expires_at"] and task["status"] not in TASK_TERMINAL | {"stopping"}:
                self._stop(task["id"], "Authorized task deadline reached", "failed")
        handlers = {
            "workspace.get": self.workspace_get, "config.update": self.config_update,
            "settings.get": self.settings_get, "settings.update": self.settings_update,
            "controller.start": self.controller_start,
            "task.create": self.task_create, "task.get": self.task_get, "task.list": self.task_list,
            "task.claim": self.task_claim, "task.heartbeat": self.task_heartbeat,
            "task.pause": self.task_pause, "task.cancel": self.task_cancel,
            "task.complete": self.task_complete, "task.finish": self.task_finish,
            "task.stop": self.task_stop, "task.revoke": self.task_revoke,
            "workflow.get": self.workflow_get, "setup.version": self.setup_version,
            "research.context": self.research_context, "research.record": self.research_record,
            **{f"memory.{name}": (lambda p, operation=name: self.memory_operation(operation, p)) for name in
               ("import", "extract", "search", "read", "rebuild", "status")},
            "decision.request": self.decision_request, "decision.list": self.decision_list,
            "decision.resolve": self.decision_resolve,
            "run.submit": self.run_submit, "run.refresh": self.run_refresh, "run.list": self.run_list,
            "run.cancel": self.run_cancel, "run.logs": self.run_logs,
            "run.reconcile": self.run_reconcile,
            "file.read": self.file_read, "file.write": self.file_write,
            "evidence.record": self.evidence_record, "reasoning.reserve": self.reasoning_reserve,
            "reasoning.record": self.reasoning_record,
            "event.list": self.event_list,
        }
        require(method in handlers, "unknown_method", "Unknown operation", {"method": method})
        return handlers[method](p)

    def workspace_get(self, p):
        config = load_config(self.root)
        cards = []
        for folder in ("2研究点", "3实验", "4复现"):
            for path in sorted((self.workspace / folder).rglob("*.md")):
                meta = parse_frontmatter(path.read_text(encoding="utf-8"))
                if meta.get("id") and meta.get("type") != "memory_object":
                    cards.append({**meta, "path": path.relative_to(self.root).as_posix()})
        from .setup.skills import inspect
        try:
            deployed = inspect(self.root, workflow.version(config))
        except ResearchError as exc:
            deployed = {"status": "conflict", "message": str(exc), "details": exc.details}
        return {"project_root": str(self.root), "workspace": str(self.workspace), "config": config, "cards": cards,
                "research_version": workflow.version(config), "skill_name": "ljh-research", "skill_deployment": deployed,
                "capabilities": {"local_execution": importlib.util.find_spec("ljh_research_local") is not None,
                    "controller": importlib.util.find_spec("ljh_research_controller") is not None,
                    "python": sys.executable, "python_version": sys.version.split()[0],
                    "scope_enforcement": "protocol validation; local processes are not an OS sandbox"}}

    def config_update(self, p):
        self.human_only()
        if p["key"] == "update_mode":
            require(p["value"] in {"manual", "automatic"}, "invalid_version", "update_mode must be manual or automatic")
            self.setup_version({"version": "auto" if p["value"] == "automatic" else "manual"})
            return load_config(self.root)
        values = update_config(self.root, p["key"], p["value"])
        with self.store.transaction() as db:
            self.store.event(db, None, "config.updated", {"key": p["key"], "evidence": self.evidence})
        return values

    def settings_get(self, p):
        with self.store.transaction() as db:
            return self.settings(db)

    def settings_update(self, p):
        self.human_only()
        require(set(p) <= {"executor", "reasoning", "controller"}, "invalid_settings", "Unknown binding fields")
        with self.store.transaction() as db:
            data = self.settings(db)
            for key, value in p.items():
                require(isinstance(value, dict), "invalid_settings", "Binding must be an object")
                command = value.get("command", [])
                require(isinstance(command, list) and all(isinstance(x, str) and x for x in command),
                        "invalid_settings", "Commands use argv arrays, not shell strings")
                if key in {"executor", "controller"}:
                    require(command, "invalid_settings", "Executor command is empty")
                    if key == "controller":
                        versions = value.get("supported_versions", ["auto"])
                        require(isinstance(versions, list) and versions and all(v in {"manual", "auto"} for v in versions),
                                "invalid_settings", "Controller supported_versions must declare manual and/or auto")
                else:
                    require(value.get("kind", "command") in {"command", "codex", "claude"}, "invalid_settings", "Unknown reasoning adapter")
                    require(1 <= value.get("timeout_seconds", 120) <= 3600, "invalid_settings", "Invalid reasoning timeout")
                data[key] = value
            self.store.put(db, "settings", data)
            self.store.event(db, None, "bindings.updated", {"fields": list(p)})
            return data

    def controller_start(self, p):
        self.human_only()
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", p["task_id"])
            require(task["authorized"] and not task["revoked"] and task["status"] in {"queued", "paused"},
                    "task_not_ready", "Task must be authorized and ready")
            binding = task["bindings_snapshot"].get("controller")
            require(binding and binding.get("command"), "needs_configuration", "No controller binding in this task; configure before creating a task")
            require(task.get("research_version", "manual") in binding.get("supported_versions", ["auto"]), "manual_task",
                    "This controller does not support the selected version; manual requires a bounded controller explicitly configured with supported_versions")
        return plugin_call(binding["command"], "start", {"project_root": str(self.root), "task_id": task["id"]})

    def task_create(self, p):
        require(isinstance(p.get("title"), str) and isinstance(p.get("objective"), str), "invalid_task", "Title and objective must be text")
        title = p.get("title", "").strip()
        require(title and p.get("objective", "").strip(), "invalid_task", "Title and objective are required")
        auth = p.get("authorization", {})
        require(isinstance(auth, dict), "invalid_authorization", "authorization must be an object")
        allowed_roots = auth.get("allowed_roots", [])
        require(isinstance(allowed_roots, list) and allowed_roots, "invalid_authorization", "Declare at least one allowed write root")
        for root in allowed_roots:
            self.path(root, [root])
        programs = auth.get("allowed_programs", [])
        require(isinstance(programs, list) and all(isinstance(x, str) and x for x in programs), "invalid_authorization", "Invalid allowed programs")
        normalized = {"allowed_roots": allowed_roots, "allowed_programs": [str(Path(shutil.which(x) or x).resolve()) for x in programs],
                      "max_runs": auth.get("max_runs", 3), "max_reasoning_calls": auth.get("max_reasoning_calls", 20),
                      "max_run_seconds": auth.get("max_run_seconds", 600), "max_task_seconds": auth.get("max_task_seconds", 3600)}
        for name in ("max_runs", "max_reasoning_calls", "max_run_seconds", "max_task_seconds"):
            require(type(normalized[name]) is int and 0 <= normalized[name] <= 100000,
                    "invalid_authorization", f"Invalid {name}")
        require(normalized["max_run_seconds"] > 0, "invalid_authorization", "Execution timeout must be positive")
        require(normalized["max_task_seconds"] > 0, "invalid_authorization", "Task deadline must be positive")
        evidence_paths = p.get("evidence_paths", [])
        require(isinstance(evidence_paths, list) and len(evidence_paths) <= 8 and all(isinstance(x, str) for x in evidence_paths),
                "invalid_task", "Declare at most eight evidence_paths; read more artifacts explicitly when needed")
        for path in evidence_paths:
            self.file_read({"path": path})
        stop_condition = p.get("stop_condition", "Stop when budget is exhausted or objective is answered")
        require(isinstance(stop_condition, str) and stop_condition.strip(), "invalid_task", "A stopping condition is required")
        config = load_config(self.root)
        selected = workflow.version(config)
        now = time.time()
        with self.store.transaction() as db:
            task = {"id": identity("TASK"), "title": title, "objective": p["objective"],
                    "stop_condition": stop_condition, "research_version": selected,
                    "workflow_revision": workflow.REVISION, "evidence_paths": evidence_paths,
                    "created_at": now, "status": "queued", "authorized": False, "revoked": False,
                    "authorization": normalized, "config_snapshot": config,
                    "bindings_snapshot": self.settings(db), "runs_used": 0, "reasoning_calls_used": 0,
                    "owner": None, "lease": "", "lease_until": 0, "ownership_epoch": 0}
            self.store.put(db, "tasks", task)
            decision = {"id": identity("DEC"), "task_id": task["id"], "kind": "task_authorization", "status": "pending",
                        "payload": {"objective": task["objective"], "stop_condition": task["stop_condition"],
                                    "research_version": selected, "evidence_paths": evidence_paths,
                                    "termination": "Stop requests revoke ownership and cancel task runs; completion seals this task",
                                    "authorization": normalized}, "created_at": now}
            self.store.put(db, "decisions", decision)
            self.store.event(db, task["id"], "task.created", {"decision_id": decision["id"]})
            return {"task": self.public_task(task), "decision": decision}

    def task_get(self, p):
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", p["task_id"])
            result = {**self.public_task(task), "runs": self.store.runs(db, task["id"])}
            if task.get("result_note"):
                note = self.root / task["result_note"]
                if note.is_file():
                    result["summary"] = note.read_text(encoding="utf-8").rsplit("## 任务结论\n\n", 1)[-1].strip()
            return result

    def task_list(self, p):
        with self.store.transaction() as db:
            tasks = [self.public_task(json.loads(row[0])) for row in db.execute("SELECT data FROM tasks ORDER BY rowid")]
            for task in tasks:
                task["active_runs"] = sum(r["status"] not in TERMINAL for r in self.store.runs(db, task["id"]))
            return tasks

    def task_claim(self, p):
        require(isinstance(p.get("driver_id"), str) and p["driver_id"].strip(), "invalid_driver", "driver_id is required")
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", p["task_id"])
            require(task["status"] not in TASK_TERMINAL | {"stopping"}, "task_terminal", "Task has ended or is stopping")
            require(task["status"] != "awaiting_decision", "decision_pending", "Resolve pending decisions before reclaiming this task")
            require(task["authorized"] and not task["revoked"], "authorization_required", "User authorization is required")
            if task.get("lease"):
                require(p.get("takeover") is True and self.human, "takeover_required", "Explicit user takeover is required")
                self.human_only()
            for row in db.execute("SELECT data FROM tasks WHERE id != ?", (task["id"],)):
                other = json.loads(row[0])
                active_runs = any(r["status"] not in TERMINAL for r in self.store.runs(db, other["id"]))
                require(not (other["status"] in {"running", "awaiting_decision", "stopping"} or active_runs),
                        "workspace_busy", "Another task owns this workspace", {"task_id": other["id"]})
            task.update(owner=p["driver_id"], lease=secrets.token_urlsafe(32), lease_until=time.time() + 300,
                        ownership_epoch=task["ownership_epoch"] + 1, status="running")
            if "max_task_seconds" in task["authorization"]:
                task.setdefault("expires_at", time.time() + task["authorization"]["max_task_seconds"])
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "task.claimed", {"owner": task["owner"], "epoch": task["ownership_epoch"]})
            return {"task": self.public_task(task), "lease": task["lease"]}

    def task_heartbeat(self, p):
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            task["lease_until"] = time.time() + 300
            self.store.put(db, "tasks", task)
            return {"lease_until": task["lease_until"]}

    def task_pause(self, p):
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", p["task_id"]) if self.human else self.checked_owner(db, p)
            require(task["status"] not in TASK_TERMINAL | {"stopping"}, "task_terminal", "Task has ended or is stopping")
            if self.human:
                self.human_only()
            task.update(status="paused", lease="", owner=None, lease_until=0, last_error=p.get("reason"))
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "task.paused", {"running_experiments_preserved": True})
            return self.public_task(task)

    def task_cancel(self, p):
        self.human_only()
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", p["task_id"])
            require(task["status"] not in TASK_TERMINAL | {"stopping"}, "task_terminal", "Task has ended or is stopping")
            task.update(status="cancelled", revoked=True, lease="", lease_until=0, owner=None)
            self._close_decisions(db, task["id"])
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "task.cancelled", {"running_experiments_preserved": True})
            return self.public_task(task)

    def task_revoke(self, p):
        result = self.task_pause(p) if self.human else None
        self.human_only()
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", p["task_id"])
            task["revoked"] = True
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "authorization.revoked", {"evidence": self.evidence})
            return self.public_task(task)

    def task_complete(self, p):
        return self.task_finish({**p, "outcome": "completed"})

    def task_finish(self, p):
        require(p.get("outcome") in {"completed", "failed", "blocked"}, "invalid_outcome", "Choose completed, failed or blocked")
        require(p.get("summary", "").strip(), "summary_required", "Record a result and limitations")
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            require(all(r["status"] in TERMINAL for r in self.store.runs(db, task["id"])), "runs_active", "Reconcile all runs before completing the task")
            if task.get("research_version") == "auto" and p["outcome"] == "completed":
                history = self._research_records(task)
                require(history and history[-1]["kind"] == "analysis" and history[-1]["decision"] == "stop",
                        "analysis_required", "Record the final credibility assessment and stop decision before completing automatic research")
            note = self._note(task)
            note.parent.mkdir(exist_ok=True)
            with note.open("a", encoding="utf-8") as stream:
                if note.stat().st_size == 0:
                    stream.write(f"# {task['title']}\n\n")
                stream.write("## 任务结论\n\n" + p["summary"] + "\n")
            task.update(status=p["outcome"], result_note=note.relative_to(self.root).as_posix(), lease="", lease_until=0, owner=None)
            self._close_decisions(db, task["id"])
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "task." + p["outcome"], {"result_note": task["result_note"]})
            return self.public_task(task)

    def _close_decisions(self, db, task_id):
        for row in db.execute("SELECT data FROM decisions").fetchall():
            decision = json.loads(row[0])
            if decision["task_id"] == task_id and decision["status"] == "pending":
                decision.update(status="cancelled", resolved_at=time.time(), evidence="Task ended")
                self.store.put(db, "decisions", decision)

    def _settle_stop(self, db, task):
        if task["status"] == "stopping" and all(r["status"] in TERMINAL for r in self.store.runs(db, task["id"])):
            task.update(status=task["stop_outcome"], stopped_at=time.time())
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "task.stopped", {"outcome": task["status"], "reason": task["stop_reason"]})

    def _cancel_execution(self, run):
        if run["status"] in TERMINAL:
            return run
        try:
            plugin_call(run["executor"]["command"], "cancel", {"project_root": str(self.root), "run_id": run["id"]})
            return self.run_refresh({"run_id": run["id"]})
        except ResearchError as exc:
            # A rejected/missing cancel acknowledgment is never proof of termination.
            with self.store.transaction() as db:
                current = self.store.get(db, "runs", run["id"])
                current["stop_error"] = str(exc)
                self.store.update_run(db, current)
            return current

    def _stop(self, task_id, reason, outcome):
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", task_id)
            if task["status"] not in TASK_TERMINAL | {"stopping"}:
                task.update(status="stopping", revoked=True, lease="", owner=None, lease_until=0,
                            stop_reason=reason, stop_outcome=outcome, stop_requested_at=time.time())
                self.store.put(db, "tasks", task)
                self._close_decisions(db, task_id)
                self.store.event(db, task_id, "task.stop_requested", {"reason": reason, "outcome": outcome})
            runs = self.store.runs(db, task_id)
        if task["status"] == "stopping":
            for run in runs:
                self._cancel_execution(run)
            with self.store.transaction() as db:
                task = self.store.get(db, "tasks", task_id)
                self._settle_stop(db, task)
                runs = self.store.runs(db, task_id)
        return {"task": self.public_task(task), "runs": runs,
                "termination_verified": all(r["status"] in TERMINAL for r in runs),
                "outstanding_run_ids": [r["id"] for r in runs if r["status"] not in TERMINAL]}

    def task_stop(self, p):
        reason = p.get("reason", "User requested task termination" if self.human else "")
        require(isinstance(reason, str) and reason.strip(), "stop_reason_required", "Record why the task must end")
        outcome = p.get("outcome", "cancelled")
        require(outcome in {"cancelled", "failed", "blocked"}, "invalid_outcome", "Stop outcome must be cancelled, failed or blocked")
        with self.store.transaction() as db:
            task = self.store.get(db, "tasks", p["task_id"])
            if self.human:
                self.human_only()
            else:
                self.checked_owner(db, p)
        return self._stop(task["id"], reason, outcome)

    def setup_version(self, p):
        from .setup.skills import deploy, inspect, restore
        if "version" in p:
            require(p["version"] in {"manual", "auto"}, "invalid_version", "Choose manual or auto")
            self.human_only()
            with self.store.transaction() as db:
                deployment, original = deploy(self.root, p["version"])
                try:
                    update_config(self.root, "update_mode", "automatic" if p["version"] == "auto" else "manual")
                except BaseException:
                    if original is not None:
                        restore(self.root, original)
                    raise
                self.store.event(db, None, "research.version_selected", {"version": p["version"], "skill_path": deployment["path"], "evidence": self.evidence})
        selected = workflow.version(load_config(self.root))
        return {"research_version": selected, "skill_name": "ljh-research", "skill_deployment": inspect(self.root, selected),
                "available_versions": ["manual", "auto"], "applies_to": "new_tasks_only; project-local skill replaced by selected version"}

    def workflow_get(self, p):
        if p.get("task_id"):
            with self.store.transaction() as db:
                task = self.store.get(db, "tasks", p["task_id"])
            selected = task.get("research_version", "manual")
            require(not p.get("version") or p["version"] == selected, "version_mismatch", "Use the existing task's frozen research version")
        else:
            selected = p.get("version", workflow.version(load_config(self.root)))
        return workflow.guide(selected, p.get("topic"))

    def _note(self, task):
        note = self.workspace / "tasks" / (task["id"] + ".md")
        require(note.resolve().is_relative_to(self.workspace.resolve()), "invalid_path", "Task note escapes workspace")
        return note

    def _research_records(self, task):
        note = self._note(task)
        return workflow.records(note.read_text(encoding="utf-8")) if note.is_file() else []

    def research_record(self, p):
        record = workflow.validate_record(p)
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            history = self._research_records(task)
            for old in history:
                if old["record_key"] == record["record_key"]:
                    require({k: v for k, v in old.items() if k not in {"id", "recorded_at"}} == record,
                            "idempotency_conflict", "record_key was used for different scientific content")
                    return old
            latest = history[-1] if history else None
            if record["kind"] == "plan":
                require(not latest or latest["kind"] == "analysis" and latest["decision"] != "stop",
                        "analysis_required", "Analyze the previous plan before selecting another action; a stop decision seals this investigation")
                require(not set(record["run_keys"]).intersection(r["request_key"] for r in self.store.runs(db, task["id"])),
                        "idempotency_conflict", "A new plan must not reuse an earlier execution key")
            else:
                require(latest and latest["kind"] == "plan" and latest["id"] == record["plan_id"],
                        "plan_required", "Analyze the current recorded plan")
                runs = [r for r in self.store.runs(db, task["id"]) if r.get("plan_id") == latest["id"]]
                require(all(r["status"] in TERMINAL for r in runs), "runs_active", "Reconcile planned runs before analysis")
                require(set(record["run_ids"]) == {r["id"] for r in runs}, "invalid_evidence", "Analysis must account for every submitted run in this plan")
                if record["credibility"] == "valid":
                    require(set(latest["run_keys"]) == {r["request_key"] for r in runs}, "incomplete_plan", "Unperformed planned runs require a partial/invalid assessment")
            record.update(id=identity("PLAN" if record["kind"] == "plan" else "ANALYSIS"), recorded_at=time.time())
            note = self._note(task)
            note.parent.mkdir(exist_ok=True)
            text = note.read_text(encoding="utf-8") if note.exists() else f"# {task['title']}\n\n研究目标：{task['objective']}\n\n"
            text += "## 科研决策记录\n\n```ljh-research-cycle\n" + json.dumps(record, ensure_ascii=False, indent=2) + "\n```\n\n"
            temp = note.with_suffix(".tmp")
            try:
                temp.write_text(text, encoding="utf-8")
                os.replace(temp, note)
            finally:
                temp.unlink(missing_ok=True)
            self.store.event(db, task["id"], "research.recorded", {"record_id": record["id"], "kind": record["kind"], "path": note.relative_to(self.root).as_posix()})
            return record

    def research_context(self, p):
        task = self.task_get(p)
        selected = task.get("research_version", "manual")
        history = self._research_records(task)
        artifacts = []
        for path in task.get("evidence_paths", []):
            try:
                data = self.file_read({"path": path, "task_id": task["id"]})
                if p.get("include_evidence"):
                    artifacts.append({**data, "content": data["content"][:4000], "truncated": len(data["content"]) > 4000})
                else:
                    artifacts.append({"path": data["path"], "sha256": data["sha256"], "content_omitted": True,
                                      "read_more": {"method": "file.read", "path": data["path"]}})
            except (ResearchError, UnicodeError) as exc:
                artifacts.append({"path": path, "unavailable": str(exc)})
        workspace = self.workspace_get({})
        note = self._note(task)
        text = note.read_text(encoding="utf-8") if note.exists() else ""
        from .memory.repository import Memory
        try:
            relevant_memory = Memory(self.root).search({"query": task["objective"][:500], "budget_chars": 6000, "limit": 5})
        except ResearchError as exc:
            relevant_memory = {"state": "needs_preparation", "message": str(exc)}
        recent = p.get("recent_records", 2)
        require(type(recent) is int and 1 <= recent <= 6, "invalid_limit", "recent_records must be 1..6")
        from .memory.extract import query_terms, contains
        terms = query_terms(task["objective"])
        related_cards = [c for c in workspace["cards"] if any(contains(c.get("title", "") + " " + c["id"], term) for term in terms)]
        return {"research_version": selected, "workflow": self.workflow_get({"task_id": task["id"]}),
                "memory": relevant_memory,
                "conclusion_discipline": workflow.guide(selected, "conclusion-discipline")["content"],
                "records": history[-recent:], "records_omitted": max(0, len(history) - recent),
                "evidence": artifacts, "task_note": {"path": note.relative_to(self.root).as_posix(), "content_omitted": bool(text)},
                "available_cards": related_cards[:8], "cards_omitted": max(0, len(workspace["cards"]) - min(8, len(related_cards))),
                "evidence_status": "Explicit sources are excerpts, not exhaustive evidence search; file.read retrieves full declared artifacts"}

    def memory_operation(self, operation, p):
        from .memory.repository import Memory
        memory = Memory(self.root)
        functions = {"import": memory.import_object, "extract": memory.extract,
                     "search": memory.search, "read": memory.read,
                     "rebuild": lambda p: memory.rebuild(), "status": lambda p: memory.status()}
        if operation in {"read", "search", "status"}:
            return functions[operation](p)
        with self.store.transaction() as db:
            if self.human:
                self.human_only()
            else:
                task = self.checked_owner(db, p)
                if operation == "import":
                    for path in [p.get("path", ""), *p.get("reading_notes", [])]:
                        source = self.path(path)
                        roots = [self.workspace] + [self.path(x) for x in task["authorization"]["allowed_roots"] + task["config_snapshot"]["code_roots"]]
                        require(any(source == root or root in source.parents for root in roots), "undeclared_path", "Memory source must be in declared project/task roots")
            result = functions[operation](p)
            self.store.event(db, p.get("task_id"), "memory." + operation, {"id": result.get("id"), "mode": result.get("mode")})
            return result

    def decision_request(self, p):
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            kind = p.get("kind", "research_decision")
            require(kind not in {"task_authorization"}, "invalid_decision", "Initial authorization uses task.create")
            decision = {"id": identity("DEC"), "task_id": task["id"], "kind": kind,
                        "payload": p.get("payload", {}), "status": "pending", "created_at": time.time()}
            self.store.put(db, "decisions", decision)
            task.update(status="awaiting_decision", lease="", owner=None, lease_until=0)
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "decision.requested", {"decision_id": decision["id"], "kind": kind})
            return decision

    def decision_list(self, p):
        with self.store.transaction() as db:
            items = [json.loads(row[0]) for row in db.execute("SELECT data FROM decisions ORDER BY rowid")]
            return [d for d in items if not p.get("task_id") or d["task_id"] == p["task_id"]]

    def decision_resolve(self, p):
        self.human_only()
        require(p.get("decision") in {"approved", "rejected"}, "invalid_decision", "Choose approved or rejected")
        with self.store.transaction() as db:
            decision = self.store.get(db, "decisions", p["decision_id"])
            require(decision["status"] == "pending", "decision_resolved", "Decision has already been resolved")
            task = self.store.get(db, "tasks", decision["task_id"])
            require(task["status"] not in TASK_TERMINAL | {"stopping"}, "task_terminal", "Ended tasks cannot be reactivated by a decision")
            decision.update(status=p["decision"], resolved_at=time.time(), evidence=self.evidence)
            if decision["kind"] == "task_authorization":
                task["authorized"] = p["decision"] == "approved"
                if not task["authorized"]:
                    task["status"] = "cancelled"
            elif task["status"] == "awaiting_decision":
                task["status"] = "paused"
            if decision["kind"] == "budget_extension" and p["decision"] == "approved":
                for key in ("max_runs", "max_reasoning_calls", "max_run_seconds"):
                    new = decision["payload"].get(key, task["authorization"][key])
                    require(type(new) is int and task["authorization"][key] <= new <= 100000,
                            "invalid_budget", "Budget extension must explicitly preserve or increase limits")
                    task["authorization"][key] = new
            self.store.put(db, "tasks", task)
            self.store.put(db, "decisions", decision)
            self.store.event(db, task["id"], "decision.resolved", {"decision_id": decision["id"], "decision": p["decision"], "evidence": self.evidence})
            return decision

    def reasoning_reserve(self, p):
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            require(task["reasoning_calls_used"] < task["authorization"]["max_reasoning_calls"], "budget_exhausted", "Reasoning-call budget exhausted")
            task["reasoning_calls_used"] += 1
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "reasoning.reserved", {"call": task["reasoning_calls_used"]})
            return {"call": task["reasoning_calls_used"]}

    def reasoning_record(self, p):
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            observation = p.get("observation", {})
            require(isinstance(observation, dict), "invalid_observation", "Observation must be an object")
            require(len(json.dumps(observation, ensure_ascii=False)) <= 40000,
                    "invalid_observation", "Observation exceeds diagnostic record limit")
            history = task.get("recent_observations", [])
            task["recent_observations"] = (history + [observation])[-12:]
            self.store.put(db, "tasks", task)
            return {"recorded": True}

    def run_submit(self, p):
        require(isinstance(p.get("request_key"), str) and p["request_key"], "idempotency_required", "request_key is required")
        argv = p.get("argv", [])
        require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv), "invalid_command", "argv must be an array")
        executable = str(Path(shutil.which(argv[0]) or argv[0]).resolve())
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            previous = db.execute("SELECT data FROM runs WHERE task_id=? AND request_key=?", (task["id"], p["request_key"])).fetchone()
            if previous:
                run = json.loads(previous[0])
                require(run["argv"] == argv and run["cwd"] == p.get("cwd", task["authorization"]["allowed_roots"][0])
                        and run.get("requested_timeout", run["timeout_seconds"]) == p.get("timeout_seconds", task["authorization"]["max_run_seconds"])
                        and run.get("plan_id") == p.get("plan_id"),
                        "idempotency_conflict", "request_key was used with a different submission")
                return run
            if task.get("research_version") == "auto":
                history = self._research_records(task)
                plan = history[-1] if history else None
                require(plan and plan["kind"] == "plan" and plan["id"] == p.get("plan_id") and p["request_key"] in plan["run_keys"],
                        "research_plan_required", "Record hypotheses, discriminating predictions and this run key before submitting an automatic experiment")
            require(executable in task["authorization"]["allowed_programs"], "program_not_authorized", "Executable is not authorized")
            require(task["runs_used"] < task["authorization"]["max_runs"], "budget_exhausted", "Experiment-run budget exhausted")
            cwd_value = p.get("cwd", task["authorization"]["allowed_roots"][0])
            cwd = self.path(cwd_value, task["authorization"]["allowed_roots"])
            require(cwd.is_dir(), "missing_path", "Create the authorized run directory before submitting")
            timeout = p.get("timeout_seconds", task["authorization"]["max_run_seconds"])
            require(type(timeout) is int and 1 <= timeout <= task["authorization"]["max_run_seconds"], "invalid_timeout", "Run exceeds authorized timeout")
            requested_timeout = timeout
            if task.get("expires_at"):
                remaining = math.floor(task["expires_at"] - time.time())
                require(remaining > 0, "task_deadline", "No authorized execution time remains")
                timeout = min(timeout, remaining)
            run = {"id": identity("RUN"), "task_id": task["id"], "request_key": p["request_key"],
                   "argv": argv, "cwd": cwd_value, "status": "submitting", "created_at": time.time(),
                   "timeout_seconds": timeout, "requested_timeout": requested_timeout, "plan_id": p.get("plan_id"),
                   "executor": task["bindings_snapshot"]["executor"], "result": None}
            db.execute("INSERT INTO runs(id,task_id,request_key,data) VALUES(?,?,?,?)",
                       (run["id"], task["id"], p["request_key"], json.dumps(run, ensure_ascii=False)))
            task["runs_used"] += 1
            self.store.put(db, "tasks", task)
            self.store.event(db, task["id"], "run.reserved", {"run_id": run["id"]})
        try:
            result = plugin_call(run["executor"]["command"], "submit", {"project_root": str(self.root),
                "run_id": run["id"], "argv": argv, "cwd": str(cwd), "timeout_seconds": timeout})
            run.update(status=result["status"], result=result)
        except ResearchError as exc:
            run.update(status="unknown", result={"error": str(exc)})
        with self.store.transaction() as db:
            self.store.update_run(db, run)
            self.store.event(db, run["task_id"], "run.submitted", {"run_id": run["id"], "status": run["status"]})
            stopped = self.store.get(db, "tasks", run["task_id"]).get("stop_requested_at")
        if stopped:
            # Covers stop racing with the external submit acknowledgment.
            run = self._cancel_execution(run)
        return run

    def run_list(self, p):
        with self.store.transaction() as db:
            return self.store.runs(db, p["task_id"])

    def run_refresh(self, p):
        with self.store.transaction() as db:
            run = self.store.get(db, "runs", p["run_id"])
        if run.get("reconciled"):
            return run
        result = plugin_call(run["executor"]["command"], "status", {"project_root": str(self.root), "run_id": run["id"]})
        run.update(status=result["status"], result=result)
        with self.store.transaction() as db:
            # Refreshes cannot consume budget, change task ownership or relaunch runs.
            self.store.update_run(db, run)
            task = self.store.get(db, "tasks", run["task_id"])
            self._settle_stop(db, task)
            return run

    def run_cancel(self, p):
        self.human_only()
        with self.store.transaction() as db:
            run = self.store.get(db, "runs", p["run_id"])
        result = plugin_call(run["executor"]["command"], "cancel", {"project_root": str(self.root), "run_id": run["id"]})
        with self.store.transaction() as db:
            self.store.event(db, run["task_id"], "run.cancel_requested", {"run_id": run["id"], "evidence": self.evidence})
        return result

    def run_reconcile(self, p):
        self.human_only()
        require(p.get("status") in {"failed", "cancelled"}, "invalid_status", "Uncertain execution may only be closed, not invented as successful")
        with self.store.transaction() as db:
            run = self.store.get(db, "runs", p["run_id"])
            require(run["status"] in {"unknown", "submitting"}, "invalid_status", "Only uncertain execution needs manual reconciliation")
            run.update(status=p["status"], reconciled=True, reconciliation_evidence=self.evidence)
            self.store.update_run(db, run)
            self.store.event(db, run["task_id"], "run.reconciled", {"run_id": run["id"], "status": run["status"], "evidence": self.evidence})
            self._settle_stop(db, self.store.get(db, "tasks", run["task_id"]))
            return run

    def run_logs(self, p):
        with self.store.transaction() as db:
            run = self.store.get(db, "runs", p["run_id"])
        return plugin_call(run["executor"]["command"], "logs", {"project_root": str(self.root), "run_id": run["id"]})

    def file_read(self, p):
        path = self.path(p["path"])
        roots = [self.workspace]
        config = load_config(self.root)
        roots += [self.path(x) for x in config["code_roots"]]
        if p.get("task_id"):
            with self.store.transaction() as db:
                task = self.store.get(db, "tasks", p["task_id"])
                roots += [self.path(x) for x in task["authorization"]["allowed_roots"]]
        require(any(path == x or x in path.parents for x in roots), "undeclared_path", "Read path must be declared in configuration or task authorization")
        require(path.is_file() and path.stat().st_size <= 2_000_000, "invalid_file", "Expected a text file up to 2 MB")
        content = path.read_text(encoding="utf-8")
        return {"path": p["path"], "content": content, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def file_write(self, p):
        require(isinstance(p.get("content"), str) and len(p["content"].encode("utf-8")) <= 2_000_000,
                "invalid_content", "Expected UTF-8 text up to 2 MB")
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            path = self.path(p["path"], task["authorization"]["allowed_roots"])
            if path.exists():
                require(path.is_file(), "invalid_file", "Target is not a file")
                current = hashlib.sha256(path.read_bytes()).hexdigest()
                require(p.get("expected_sha256") == current, "revision_conflict", "Read the existing file and supply its expected_sha256 before updating")
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + "." + identity("tmp"))
            try:
                temp.write_text(p["content"], encoding="utf-8")
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
            self.store.event(db, task["id"], "file.written", {"path": p["path"]})
            return {"path": p["path"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def evidence_record(self, p):
        require(isinstance(p.get("text"), str) and p["text"].strip(), "invalid_evidence", "Evidence text is required")
        with self.store.transaction() as db:
            task = self.checked_owner(db, p)
            run_ids = p.get("run_ids", [])
            require(isinstance(run_ids, list), "invalid_evidence", "run_ids must be an array")
            for run_id in run_ids:
                run = self.store.get(db, "runs", run_id)
                require(run["task_id"] == task["id"], "invalid_evidence", "Run belongs to another task")
            note = self._note(task)
            note.parent.mkdir(exist_ok=True)
            prefix = "" if note.exists() else f"# {task['title']}\n\n研究目标：{task['objective']}\n\n"
            with note.open("a", encoding="utf-8") as stream:
                stream.write(prefix + "## 记录\n\n" + p["text"] + "\n\n关联运行：" + ", ".join(run_ids) + "\n\n")
            self.store.event(db, task["id"], "evidence.recorded", {"path": note.relative_to(self.root).as_posix(), "run_ids": run_ids})
            return {"path": note.relative_to(self.root).as_posix()}

    def event_list(self, p):
        with self.store.transaction() as db:
            rows = db.execute("SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT 300", (int(p.get("after", 0)),))
            return [{"seq": r["seq"], "at": r["at"], "task_id": r["task_id"], "kind": r["kind"], "data": json.loads(r["data"])} for r in rows]
