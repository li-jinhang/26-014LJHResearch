"""Register an already verified tool environment without altering PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    args = parser.parse_args()
    executable = Path(args.python).resolve()
    result = subprocess.run([str(executable), "-c", "import ljh_research; print(ljh_research.__version__)"],
                            capture_output=True, encoding="utf-8", check=True)
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "LJHResearch" if os.name == "nt" else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "ljh-research"
    path = Path(os.environ.get("LJH_RESEARCH_RUNTIME_BINDING", str(base / "runtime.json"))).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"python": str(executable),
                               "version": result.stdout.strip()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
