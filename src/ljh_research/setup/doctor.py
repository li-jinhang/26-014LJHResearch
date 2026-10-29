"""Read-only capability discovery; distinguish shims from working commands."""
import importlib.util
import platform
import shutil
import subprocess
import sys


def probe(command, markers=()):
    try:
        result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=10)
        output = result.stdout + result.stderr
        valid = result.returncode == 0 and (not markers or any(marker in output.lower() for marker in markers))
        return {"command": command, "available": valid, "version": output.strip()[:400]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"command": command, "available": False, "reason": str(exc)}


def inspect():
    commands = {}
    for name in ("codex", "claude"):
        path = shutil.which(name)
        commands[name] = probe([path, "--version"], (name,)) if path else {"available": False, "reason": "not on PATH"}
    return {"platform": platform.system(), "python": {"executable": sys.executable,
        "version": platform.python_version(), "supported": sys.version_info >= (3, 11)},
        "commands": commands, "optional": {name: importlib.util.find_spec(name) is not None
            for name in ("pypdf", "ljh_research_local", "ljh_research_controller", "ljh_research_panel")}}
