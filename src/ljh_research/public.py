"""Versioned public contract, shared by CLI, Python clients and HTTP adapters."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys

from .errors import ResearchError, require
from .service import Service
from . import __version__


def dispatch(request, *, human=False, evidence=""):
    request_id = request.get("request_id") if isinstance(request, dict) else None
    result = {"protocol_version": 1, "request_id": request_id}
    try:
        require(isinstance(request, dict) and request.get("protocol_version") == 1,
                "protocol_version", "Expected protocol_version=1")
        method = request.get("method", "")
        require(isinstance(method, str), "invalid_request", "method must be text")
        params = request.get("params", {})
        require(isinstance(params, dict), "invalid_request", "params must be an object")
        root = Path(request.get("project_root", ".")).expanduser().resolve()
        if method == "system.capabilities":
            from .setup.doctor import inspect
            value = {"version": __version__, "protocol_version": 1, **inspect()}
        elif method == "workflow.get" and params.get("version") and not params.get("task_id"):
            # Guidance is readable before workspace creation or environment configuration.
            from .workflow import guide
            value = guide(params["version"], params.get("topic"))
        elif method == "setup.version":
            value = Service(root, human=human, evidence=evidence).setup_version(params)
        elif method.startswith("setup."):
            require(method in {"setup.plan", "setup.create", "setup.validate", "setup.repair", "setup.deploy", "setup.migrate"}, "unknown_method", "Unknown setup operation")
            if "version" in params:
                require(method in {"setup.plan", "setup.create", "setup.deploy"} and params["version"] in {"manual", "auto"},
                        "invalid_version", "Select manual or auto during create/plan/deploy; use setup.version for existing workspaces")
            if method in {"setup.create", "setup.repair", "setup.deploy", "setup.migrate"}:
                require(human and evidence.strip(), "human_required", "Explicit setup approval is required")
            from .setup import workspace, skills
            from .knowledge.layout import research_root
            from .knowledge.project_conventions import load
            from .workflow import version
            if method == "setup.plan":
                changes = workspace.plan(root)
                if not any(x.startswith("STOP") for x in changes):
                    if not (research_root(root) / ".runtime/tasks.sqlite3").is_file():
                        changes.append("CREATE ljh research docs/.runtime/tasks.sqlite3")
                    selected = params.get("version", version(load(root)) if (research_root(root) / "01约束文件.md").is_file() else "manual")
                    try:
                        deployment = skills.inspect(root, selected)
                        changes.append(("VALIDATE " if deployment["status"] == "ready" else "DEPLOY ") + deployment["path"] + " version=" + selected)
                    except ResearchError as exc:
                        changes.append("STOP " + str(exc))
                value = {"changes": changes}
            elif method == "setup.validate":
                from dataclasses import asdict
                value = asdict(workspace.validate_workspace(root))
                value["runtime_status"] = "ready" if (research_root(root) / ".runtime/tasks.sqlite3").is_file() else "needs_preparation"
                if value["status"] == "valid":
                    try:
                        value["skill_deployment"] = skills.inspect(root, version(load(root)))
                    except ResearchError as exc:
                        value["skill_deployment"] = {"status": "conflict", "message": str(exc), "details": exc.details}
            elif method == "setup.deploy":
                value = Service(root, human=human, evidence=evidence).setup_version({"version": params.get("version", version(load(root)))})
            elif method == "setup.migrate":
                from .setup.migrate import migrate
                value = migrate(root, params.get("source"))
                from .store import Store
                Store(root, initialize=True)
                value.update(Service(root, human=human, evidence=evidence).setup_version({"version": version(load(root))}))
            else:
                # Refuse conflicting local skills before any workspace writes.
                skills.inspect(root, params.get("version", "manual"))
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    operation = workspace.command_create if method == "setup.create" else workspace.command_repair
                    operation(root)
                from .store import Store
                Store(root, initialize=True)
                value = {"workspace": str(research_root(root)), "report": buffer.getvalue()}
                value.update(Service(root, human=human, evidence=evidence).setup_version({"version": params.get("version", version(load(root)))}))
        elif method == "knowledge.invoke":
            service = Service(root, human=human, evidence=evidence)
            tool = params.get("tool")
            allowed = {"research_point", "experiment_point", "reproduction", "scheduler", "import_paper",
                       "download_paper", "search_source_file", "generate_research_directions", "audit_optimization_points",
                       "append_rd_experience", "foam_bridge"}
            require(tool in allowed, "unknown_tool", "Unknown research operation")
            args = params.get("arguments", [])
            require(isinstance(args, list) and all(isinstance(x, str) for x in args), "invalid_arguments", "arguments must be an argv array")
            require(not any(x.startswith("--project-root") for x in args), "invalid_arguments", "Project binding is supplied by the public contract")
            read_only = tool in {"search_source_file", "generate_research_directions", "audit_optimization_points"} or (
                tool in {"research_point", "experiment_point", "reproduction", "scheduler"} and args and args[0] in {"list", "search", "preview", "queue", "next"})
            if not read_only:
                if human:
                    service.human_only()
                else:
                    with service.store.transaction() as db:
                        service.checked_owner(db, params)
                    require(not (tool == "research_point" and args and args[0] == "framework"),
                            "human_required", "Framework adoption requires a concrete user decision")
                    require(tool != "scheduler", "human_required", "Workspace routing repair belongs to setup")
            completed = subprocess.run([sys.executable, "-m", "ljh_research.knowledge." + tool,
                "--project-root", str(root), *args], capture_output=True, encoding="utf-8", timeout=300)
            require(completed.returncode == 0, "research_operation_failed", completed.stderr[-8000:], {"stdout": completed.stdout[-12000:]})
            value = {"output": completed.stdout, "tool": tool}
            if not read_only and tool in {"research_point", "experiment_point", "reproduction"}:
                import re
                from .memory.repository import Memory
                matches = re.findall(r"(?m)^(?:card|concluded|implemented)=(.+)$", completed.stdout)
                captures = []
                for raw_path in matches:
                    path = Path(raw_path.strip()).resolve()
                    if path.is_file() and path.is_relative_to(service.workspace):
                        from .workspace_contract import parse_frontmatter
                        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
                        identifier = meta.get("id")
                        if identifier:
                            try:
                                memory = Memory(root)
                                old = memory.get(identifier)
                            except ResearchError as exc:
                                if exc.code != "not_found":
                                    captures.append({"id": identifier, "state": "pending", "message": str(exc)})
                                    continue
                                captures.append(memory.import_object({"kind": {"research_point":"research_point", "experiment_point":"experiment", "reproduction":"reproduction"}[tool],
                                    "id": identifier, "title": meta.get("title", identifier).strip('"'), "path": path.relative_to(root).as_posix(), "reference_only": True}))
                            else:
                                try:
                                    new_path = path.relative_to(root).as_posix()
                                    if old["sources"][0]["path"] != new_path:
                                        old["sources"][0]["path"] = new_path
                                        memory.save(old)
                                    captures.append(memory.extract({"id": identifier}))
                                except ResearchError as exc:
                                    captures.append({"id": identifier, "state": "pending", "message": str(exc)})
                value["memory_updates"] = captures
        else:
            value = Service(root, human=human, evidence=evidence).dispatch(method, params)
        result.update(ok=True, result=value)
    except ResearchError as exc:
        result.update(ok=False, error={"code": exc.code, "message": str(exc), "details": exc.details})
    except (ValueError, KeyError, TypeError, OSError, SystemExit, subprocess.SubprocessError) as exc:
        result.update(ok=False, error={"code": "invalid_operation", "message": str(exc), "details": {}})
    except Exception as exc:
        result.update(ok=False, error={"code": "internal_error", "message": f"Operation failed ({type(exc).__name__})", "details": {}})
    return result


class Client:
    """In-process public client. No controller needs to import service/storage."""
    def __init__(self, project_root):
        self.project_root = str(Path(project_root).resolve())

    def call(self, method, **params):
        result = dispatch({"protocol_version": 1, "method": method, "project_root": self.project_root, "params": params})
        if not result["ok"]:
            error = result["error"]
            raise ResearchError(error["code"], error["message"], error.get("details"))
        return result["result"]
