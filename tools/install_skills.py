"""Copy the complete setup skill to a global skills directory, preserving a backup."""
import argparse
import json
import os
from pathlib import Path
import shutil
from datetime import datetime
import zipfile

def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "ljh-research-setup"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path(os.environ.get("AGENTS_HOME", str(Path.home() / ".agents"))) / "skills/ljh-research-setup")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    target = args.destination.expanduser().resolve()
    if target == source.resolve() or target.is_relative_to(source.resolve()) or source.resolve().is_relative_to(target):
        parser.error("Choose a destination separate from the repository skill")
    if not (source / "assets/wheels/manifest.json").is_file():
        parser.error("Run tools/build_setup_skill.py first")
    print(json.dumps({"source": str(source), "destination": str(target), "apply": args.apply}, indent=2))
    if not args.apply:
        return
    if target.exists():
        backup_dir = root / ".local/setup-skill-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".zip")
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in target.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(target).as_posix())
        print(f"Previous setup preserved at {backup}")
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print("Installed the complete setup skill only; research variants remain project-local.")


if __name__ == "__main__":
    main()
