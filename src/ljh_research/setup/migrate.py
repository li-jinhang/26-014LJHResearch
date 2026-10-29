"""Explicit, idle-only rename of an owned legacy document workspace."""
import json
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import uuid
import zipfile

from ..errors import require
from ..knowledge.layout import RESEARCH_DIR, LEGACY_RESEARCH_DIRS, legacy_roots, WORKSPACE_SCHEMA_VERSION
from .skills import inspect


LOCK = ".ljh-research-migration.lock"


def _map_paths(value, old, new):
    if isinstance(value, list):
        return [_map_paths(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: _map_paths(v, old, new) for k, v in value.items()}
    if isinstance(value, str):
        for left, right in ((str(old), str(new)), (old.as_posix(), new.as_posix()), (old.name, new.name)):
            for sep in ("/", "\\"):
                prefix = left + sep
                if value.startswith(prefix):
                    return right + value[len(left):]
    return value


def _idle(database):
    if not database.is_file():
        return
    with closing(sqlite3.connect(database, timeout=15)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        tasks = [json.loads(r[0]) for r in db.execute("SELECT data FROM tasks")]
        runs = [json.loads(r[0]) for r in db.execute("SELECT data FROM runs")]
        require(not any(t["status"] in {"running", "awaiting_decision", "stopping"} for t in tasks)
                and all(r["status"] in {"succeeded", "failed", "cancelled"} for r in runs),
                "workspace_busy", "Pause/finish tasks and reconcile every run before migrating document paths")


def _rewrite_database(database, old, new):
    if not database.is_file():
        return
    with closing(sqlite3.connect(database)) as db, db:
        for table in ("tasks", "runs", "decisions", "settings"):
            for key, data in db.execute(f"SELECT id,data FROM {table}").fetchall():
                mapped = _map_paths(json.loads(data), old, new)
                db.execute(f"UPDATE {table} SET data=? WHERE id=?", (json.dumps(mapped, ensure_ascii=False), key))
        # Events are history: preserve original paths instead of rewriting past actions.


def migrate(root, source=None):
    root = Path(root).resolve()
    new = root / RESEARCH_DIR
    require(not new.exists(), "migration_conflict", "Destination already exists; never merge document trees automatically")
    require(source is None or source in LEGACY_RESEARCH_DIRS, "invalid_path", "Migration source must be an explicit recognized legacy directory name")
    candidates = legacy_roots(root)
    require(len(candidates) == 1, "migration_conflict", "Exactly one legacy document tree is required; inspect conflicting/missing directories first")
    old = root / source if source else candidates[0]
    require(old == candidates[0] and old.is_dir() and not old.is_symlink() and not getattr(old, "is_junction", lambda: False)()
            and old.resolve().parent == root and new.resolve().parent == root, "invalid_path", "Migration paths must remain directly inside the selected project")
    marker = old / ".workspace.json"
    try:
        owned = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        owned = None
    require(isinstance(owned, dict) and owned == {"kind": "ljh-research-workspace", "schema_version": WORKSPACE_SCHEMA_VERSION}
            and type(owned.get("schema_version")) is int, "unowned_workspace",
            "Legacy directory has no supported ownership marker; preserve it and review its format before migration")
    inspect(root, "manual")  # Refuse a conflicting project skill before moving any records.
    lock = root / LOCK
    try:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "source": old.name, "destination": new.name}))
    except FileExistsError:
        require(False, "setup_busy", "Another migration or an interrupted migration lock needs inspection")
    original = {}
    moved = False
    try:
        database = old / ".runtime/tasks.sqlite3"
        _idle(database)
        replacements = {}
        for path in old.rglob("*"):
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(old) or path.suffix not in {".md", ".json"} or path.stat().st_size > 2_000_000:
                continue
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
                if path.suffix == ".json":
                    data = json.loads(text)
                    mapped = _map_paths(data, old, new)
                    changed = (json.dumps(mapped, ensure_ascii=False, indent=2) + "\n") if mapped != data else text
                else:
                    changed = text.replace(old.name + "/", new.name + "/").replace(old.name + "\\", new.name + "\\")
                    if changed != text:
                        changed = re.sub(r"\]\(([^<>\n)]*ljh research docs[^<>\n)]*)\)", lambda m: "](<" + m[1] + ">)", changed)
            except (ValueError, UnicodeError):
                continue
            if changed != text:
                relative = path.relative_to(old).as_posix()
                original[relative] = raw
                replacements[relative] = changed.encode("utf-8")
        if database.is_file():
            original[".runtime/tasks.sqlite3"] = database.read_bytes()
        backup_relative = ".runtime/setup/migrations/" + uuid.uuid4().hex + ".zip"
        backup = old / backup_relative
        require(backup.resolve().is_relative_to(old), "invalid_path", "Migration backup escapes workspace")
        backup.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(backup, "x", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("migration.json", json.dumps({"from": old.name, "to": new.name, "changed_files": list(original)}, ensure_ascii=False))
            for name, content in original.items():
                bundle.writestr("original/" + name, content)
        old.rename(new)
        moved = True
        for relative, content in replacements.items():
            (new / relative).write_bytes(content)
        _rewrite_database(new / ".runtime/tasks.sqlite3", old, new)
        return {"workspace": str(new), "migrated_from": old.name, "backup": RESEARCH_DIR + "/" + backup_relative,
                "changed_reference_files": len(replacements), "budgets_preserved": True}
    except BaseException:
        if moved:
            for relative, content in original.items():
                (new / relative).write_bytes(content)
            new.rename(old)
        raise
    finally:
        lock.unlink(missing_ok=True)
