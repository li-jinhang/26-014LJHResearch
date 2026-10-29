"""Small transactional task ledger. Research findings remain in Markdown."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .workspace_contract import require_owned_workspace
from .errors import require


def identity(prefix):
    return prefix + "-" + uuid.uuid4().hex[:16]


class Store:
    def __init__(self, root, initialize=False):
        self.root = root
        workspace = require_owned_workspace(root)
        runtime = workspace / ".runtime"
        require(runtime.resolve().is_relative_to(workspace.resolve()), "invalid_path", "Runtime directory escapes workspace")
        self.path = runtime / "tasks.sqlite3"
        require(self.path.resolve().is_relative_to(workspace.resolve()), "invalid_path", "Task database escapes workspace")
        require(initialize or self.path.is_file(), "setup_required", "Task runtime is missing; use setup repair")
        if initialize:
            runtime.mkdir(exist_ok=True)
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT);
                INSERT OR IGNORE INTO metadata VALUES('schema_version','1');
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, task_id TEXT, request_key TEXT, data TEXT,
                    UNIQUE(task_id, request_key));
                CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    at REAL, task_id TEXT, kind TEXT, data TEXT);
            ''')
            version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
            require(version == "1", "schema_mismatch", "Unsupported runtime schema", {"version": version})

    @contextmanager
    def transaction(self):
        require(not (self.root / ".ljh-research-migration.lock").exists(), "setup_busy", "Document-directory migration is in progress")
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("BEGIN IMMEDIATE")
            require(not (self.root / ".ljh-research-migration.lock").exists(), "setup_busy", "Document-directory migration is in progress")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, db, table, key):
        require(table in {"tasks", "runs", "decisions", "settings"}, "invalid_table", "Unknown record type")
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
        require(row is not None, "not_found", f"{table} record not found", {"id": key})
        return json.loads(row[0])

    def put(self, db, table, record):
        require(table in {"tasks", "decisions", "settings"}, "invalid_table", "Unknown record type")
        db.execute(f"INSERT INTO {table}(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                   (record["id"], json.dumps(record, ensure_ascii=False)))

    def runs(self, db, task_id):
        return [json.loads(r[0]) for r in db.execute("SELECT data FROM runs WHERE task_id=? ORDER BY rowid", (task_id,))]

    def update_run(self, db, record):
        db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(record, ensure_ascii=False), record["id"]))

    def event(self, db, task_id, kind, data):
        # Leases and auth credentials are not written to the event projection.
        data = {k: v for k, v in data.items() if k not in {"lease", "human_token"}}
        db.execute("INSERT INTO events(at,task_id,kind,data) VALUES(?,?,?,?)",
                   (time.time(), task_id, kind, json.dumps(data, ensure_ascii=False)))
