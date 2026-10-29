"""One JSON request per invocation; detached workers survive driver exit."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def write_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def process_identity(pid):
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            code = wintypes.DWORD()
            kernel.GetExitCodeProcess(handle, ctypes.byref(code))
            return f"{created.dwHighDateTime}:{created.dwLowDateTime}" if code.value == 259 else None
        finally:
            kernel.CloseHandle(handle)
    try:
        # Linux process birth time also protects against PID reuse.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def status(folder):
    result = folder / "result.json"
    if result.is_file():
        return json.loads(result.read_text(encoding="utf-8"))
    worker = folder / "worker.json"
    if not worker.is_file():
        return {"status": "unknown", "reason": "Submission not acknowledged; do not resubmit automatically"}
    data = json.loads(worker.read_text(encoding="utf-8"))
    alive = data.get("identity") and process_identity(data["pid"]) == data["identity"]
    return {"status": "running" if alive else "unknown", "worker_pid": data["pid"],
            "reason": "worker verified" if alive else "worker identity unavailable; reconcile before retry"}


def job_folder(p):
    if not re.fullmatch(r"RUN-[a-zA-Z0-9_-]+", p["run_id"]):
        raise ValueError("Invalid run identity")
    root = Path(p["project_root"]).resolve()
    workspace = root / "ljh research docs"
    if not (workspace / ".workspace.json").is_file():
        raise ValueError("No research workspace")
    folder = workspace / ".runtime" / "executions" / p["run_id"]
    if workspace.resolve() not in folder.resolve().parents:
        raise ValueError("Execution path escapes workspace")
    return folder


def handle(method, p):
    if method == "capabilities":
        return {"protocol_version": 1, "executor": "local", "platform": sys.platform,
                "operations": ["submit", "status", "logs", "cancel"], "detached": True,
                "scope_enforcement": "trusted host process; not an OS sandbox"}
    folder = job_folder(p)
    if method == "submit":
        spec = {k: p[k] for k in ("run_id", "argv", "cwd", "timeout_seconds")}
        encoded = json.dumps(spec, sort_keys=True)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            existing = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
            if existing["fingerprint"] != fingerprint:
                raise ValueError("Run ID already has a different submission")
            return status(folder)
        write_json(folder / "spec.json", {**spec, "fingerprint": fingerprint})
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen([sys.executable, "-m", "ljh_research_local", "--worker", str(folder)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **options)
        birth = process_identity(process.pid)
        write_json(folder / "worker.json", {"pid": process.pid, "identity": birth})
        return {"status": "running", "worker_pid": process.pid, "identity": birth}
    if method == "status":
        return status(folder)
    if method == "cancel":
        if status(folder)["status"] not in {"succeeded", "failed", "cancelled"}:
            (folder / "cancel.request").write_text("cancel", encoding="utf-8")
        return {"cancel_requested": True, **status(folder)}
    if method == "logs":
        result = {}
        for name in ("stdout", "stderr"):
            path = folder / (name + ".log")
            if path.exists():
                with path.open("rb") as stream:
                    stream.seek(max(0, path.stat().st_size - 32000))
                    result[name] = stream.read().decode("utf-8", errors="replace")
            else:
                result[name] = ""
        return result
    raise ValueError("Unknown execution operation")


def terminate_tree(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def worker(folder):
    started = time.time()
    result = {"status": "failed", "started_at": started}
    try:
        spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        with (folder / "stdout.log").open("wb") as out, (folder / "stderr.log").open("wb") as err:
            process = subprocess.Popen(spec["argv"], cwd=spec["cwd"], stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, env={**os.environ, "PYTHONUTF8": "1"}, **options)
            write_json(folder / "process.json", {"pid": process.pid, "identity": process_identity(process.pid)})
            deadline = time.monotonic() + spec["timeout_seconds"]
            reason = "exited"
            while process.poll() is None:
                if (folder / "cancel.request").exists() or time.monotonic() > deadline:
                    reason = "cancelled" if (folder / "cancel.request").exists() else "timeout"
                    terminate_tree(process)
                    break
                time.sleep(0.15)
            result.update(status="cancelled" if reason == "cancelled" else "succeeded" if process.returncode == 0 and reason == "exited" else "failed",
                          exit_code=process.returncode, reason=reason)
    except Exception as exc:
        result["error"] = str(exc)
    result.update(finished_at=time.time(), elapsed_seconds=time.time() - started)
    write_json(folder / "result.json", result)


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]))
        return 0
    request = {}
    try:
        request = json.load(sys.stdin)
        if request.get("protocol_version") != 1:
            raise ValueError("Unsupported protocol version")
        result = {"ok": True, "result": handle(request["method"], request.get("params", {}))}
    except Exception as exc:
        result = {"ok": False, "error": {"message": str(exc)}}
    result.update(protocol_version=1, request_id=request.get("request_id"))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
