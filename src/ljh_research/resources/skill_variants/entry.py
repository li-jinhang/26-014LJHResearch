"""Select an installed core, optionally using the user runtime binding."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

def run(module):
    if importlib.util.find_spec("ljh_research") is not None:
        runpy.run_module(module, run_name="__main__")
        return
    base = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()/"AppData/Local")))/"LJHResearch"
            if os.name == "nt" else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")))/"ljh-research")
    binding = Path(os.environ.get("LJH_RESEARCH_RUNTIME_BINDING", str(base/"runtime.json"))).expanduser()
    if not binding.is_file():
        raise SystemExit("LJH Research runtime is not configured. Use ljh-research-setup bootstrap first.")
    python = Path(json.loads(binding.read_text(encoding="utf-8"))["python"])
    if not python.is_file() or python.resolve() == Path(sys.executable).resolve():
        raise SystemExit("Configured tool environment is unavailable. Run ljh-research-setup again.")
    raise SystemExit(subprocess.call([str(python), "-m", module, *sys.argv[1:]]))
