"""Install this skill's verified wheels without an application checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PACKAGES = {"ljh-research-core", "ljh-research-local", "ljh-research-controller", "ljh-research-panel"}


def binding_path():
    override = os.environ.get("LJH_RESEARCH_RUNTIME_BINDING")
    if override:
        return Path(override).expanduser().resolve()
    base = (Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "LJHResearch"
            if os.name == "nt" else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "ljh-research")
    return base / "runtime.json"


def runtime_path():
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "LJHResearch"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "ljh-research"


def verified_wheels():
    wheel_dir = Path(__file__).resolve().parents[1] / "assets/wheels"
    manifest = json.loads((wheel_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or set(manifest["packages"]) != PACKAGES:
        raise ValueError("Invalid bundled package manifest; obtain a complete setup skill")
    wheels = []
    for package, item in sorted(manifest["packages"].items()):
        filename = item["filename"]
        if Path(filename).name != filename or not filename.endswith("-py3-none-any.whl"):
            raise ValueError("Invalid bundled wheel filename")
        path = wheel_dir / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Bundled wheel hash mismatch: {filename}")
        wheels.append(path)
    return manifest, wheels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, default=runtime_path())
    parser.add_argument("--apply", action="store_true", help="Install the reviewed plan")
    parser.add_argument("--papers", action="store_true", help="Also fetch optional PDF support from the package index")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python >= 3.11 is required")
    try:
        manifest, wheels = verified_wheels()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Invalid setup bundle: {exc}\n")
    runtime = args.runtime_dir.expanduser().resolve()
    binding = binding_path()
    tool_python = runtime / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    plan = {"bundle": str(Path(__file__).resolve().parents[1]), "python": sys.executable,
            "runtime": str(runtime), "binding": str(binding), "packages": manifest["packages"],
            "offline": not args.papers, "apply": args.apply}
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if not args.apply:
        return 0
    # No source imports or pip configuration may redirect this installation.
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    if not tool_python.is_file():
        subprocess.run([sys.executable, "-I", "-m", "venv", str(runtime / "venv")], env=env, check=True)
    subprocess.run([str(tool_python), "-I", "-c",
                    "import sys; assert sys.version_info >= (3,11); assert sys.prefix != sys.base_prefix"],
                   env=env, check=True)
    subprocess.run([str(tool_python), "-I", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps",
                    "--disable-pip-version-check", "--force-reinstall", *map(str, wheels)], env=env, check=True)
    if args.papers:
        version = manifest["packages"]["ljh-research-core"]["version"]
        subprocess.run([str(tool_python), "-I", "-m", "pip", "--isolated", "install",
                        f"ljh-research-core[papers]=={version}"], env=env, check=True)
    verified = subprocess.run([str(tool_python), "-I", "-c",
        "import importlib, importlib.metadata, json; "
        "[importlib.import_module(n) for n in ('ljh_research.public','ljh_research_local','ljh_research_controller','ljh_research_panel')]; "
        "print(json.dumps({'version':importlib.metadata.version('ljh-research-core')}))"],
        env=env, capture_output=True, encoding="utf-8", check=True)
    record = {"schema_version": 1, "python": str(tool_python), **json.loads(verified.stdout)}
    binding.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=binding.parent, delete=False) as stream:
        stage = Path(stream.name)
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    try:
        os.replace(stage, binding)
    finally:
        stage.unlink(missing_ok=True)
    print(json.dumps({"installed": True, "python": str(tool_python), "binding": str(binding)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
