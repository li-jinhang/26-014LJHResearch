"""Install one selected research variant into one project, never globally."""
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import uuid
import zipfile

from ..errors import require
from ..knowledge.layout import research_root


SLOT = Path(".agents/skills/ljh-research")
MARKER = ".deployment.json"
MANAGED = ("SKILL.md", "agents/openai.yaml", "scripts/research.py", "scripts/_entry.py")


def payload(version):
    require(version in {"manual", "auto"}, "invalid_version", "Choose manual or auto")
    resource = files("ljh_research").joinpath("resources", "skill_variants")
    return {"SKILL.md": resource.joinpath(version, "SKILL.md").read_bytes(),
            "agents/openai.yaml": resource.joinpath(version, "agents", "openai.yaml").read_bytes(),
            "scripts/research.py": resource.joinpath("research.py").read_bytes(),
            "scripts/_entry.py": resource.joinpath("entry.py").read_bytes()}


def destination(root):
    root = Path(root).resolve()
    target = root / SLOT
    global_roots = [Path(os.environ.get("AGENTS_HOME", str(Path.home() / ".agents"))) / "skills",
                    Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills"]
    require(not any(target.resolve().is_relative_to(p.resolve()) for p in global_roots),
            "global_deployment_forbidden", "Research variants may only be deployed to a project, not a global skill directory")
    for part in (root / ".agents", root / ".agents/skills", target):
        require(part.resolve().is_relative_to(root) and not part.is_symlink() and not getattr(part, "is_junction", lambda: False)(),
                "invalid_path", "Project skill destination must be a real directory inside the selected project")
        require(not part.exists() or part.is_dir(), "deployment_conflict", "Project skill path is not a directory")
    return target


def inspect(root, version):
    target = destination(root)
    expected = payload(version)
    marker = target / MARKER
    result = {"path": SLOT.as_posix(), "skill_name": "ljh-research", "research_version": version, "status": "missing"}
    if not target.exists() or not any(target.iterdir()):
        return result
    require(marker.is_file() and not marker.is_symlink(), "deployment_conflict", "Existing project skill is not setup-managed; preserve it and resolve this concrete conflict before deployment", {"path": str(target)})
    try:
        saved = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        require(False, "deployment_conflict", "Invalid project skill deployment marker", {"reason": str(exc)})
    require(isinstance(saved, dict) and saved.get("kind") == "ljh-research-project-skill" and saved.get("schema_version") == 1
            and type(saved.get("schema_version")) is int
            and saved.get("research_version") in {"manual", "auto"} and isinstance(saved.get("files"), dict)
            and set(saved["files"]) == set(MANAGED), "deployment_conflict", "Unrecognized project skill deployment marker")
    modified = []
    missing = []
    for name in MANAGED:
        path = target / name
        require(path.resolve().is_relative_to(target) and all(not q.is_symlink() and not getattr(q, "is_junction", lambda: False)() for q in (path, path.parent)),
                "invalid_path", "Managed skill file must be real and stay inside its deployment directory")
        if not path.exists():
            missing.append(name)
        elif not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != saved["files"][name]:
            modified.append(name)
    require(not modified, "deployment_conflict", "Setup-managed files were edited; preserve/review those edits before switching or updating", {"modified_files": modified})
    result["status"] = "ready" if not missing and saved["research_version"] == version and all((target / k).read_bytes() == v for k, v in expected.items()) else "outdated"
    result["deployed_version"] = saved["research_version"]
    result["missing_files"] = missing
    return result


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def restore(root, snapshot):
    target = destination(root)
    for name, original in snapshot.items():
        path = target / name
        if original is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, original)


def deploy(root, version):
    status = inspect(root, version)
    if status["status"] == "ready":
        return status, None
    target = destination(root)
    snapshot = {name: (target / name).read_bytes() if (target / name).is_file() else None for name in (*MANAGED, MARKER)}
    data = payload(version)
    manifest = {"kind": "ljh-research-project-skill", "schema_version": 1, "research_version": version,
                "files": {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}}
    data[MARKER] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if any(v is not None for v in snapshot.values()):
        backup = research_root(Path(root)) / ".runtime/setup/skill-backups" / (uuid.uuid4().hex + ".zip")
        require(backup.resolve().is_relative_to(research_root(Path(root)).resolve()), "invalid_path", "Skill backup escapes workspace")
        backup.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(backup, "x", zipfile.ZIP_DEFLATED) as bundle:
            for name, original in snapshot.items():
                if original is not None:
                    bundle.writestr(name, original)
    try:
        for name, content in data.items():
            atomic_write(target / name, content)
    except BaseException:
        restore(root, snapshot)
        raise
    return {**inspect(root, version), "changed": True}, snapshot
