"""Build the self-contained setup skill and its downloadable ZIP from this checkout."""
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "ljh-research-setup"


def main():
    wheel_dir = SKILL / "assets/wheels"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ljh-build-wheels-") as folder:
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
                        "--disable-pip-version-check", "--wheel-dir", folder, str(ROOT),
                        *[str(ROOT / "packages" / name) for name in ("local-executor", "controller", "panel")]], check=True)
        wheels = sorted(Path(folder).glob("*.whl"))
        if len(wheels) != 4:
            raise RuntimeError("Expected exactly four distribution wheels")
        packages = {}
        for path in wheels:
            with zipfile.ZipFile(path) as archive:
                metadata_path = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
                metadata = BytesParser().parsebytes(archive.read(metadata_path))
                packages[metadata["Name"]] = {"filename": path.name, "version": metadata["Version"],
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            shutil.copy2(path, wheel_dir / path.name)
        keep = {item["filename"] for item in packages.values()}
        for old in wheel_dir.glob("*.whl"):
            if old.name not in keep:
                old.unlink()
        (wheel_dir / "manifest.json").write_text(json.dumps({"schema_version": 1, "packages": packages},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "src/ljh_research/resources/skill_variants/entry.py", SKILL / "scripts/_entry.py")
    output = ROOT / "dist/ljh-research-setup.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SKILL.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, "ljh-research-setup/" + path.relative_to(SKILL).as_posix())
    print(json.dumps({"skill": str(SKILL), "zip": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
