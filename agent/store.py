"""SQLite persistence — sessions, messages, runs, swarm tasks, memory, audit.

One file (`~/.windycity-agent/agent.db`), WAL mode, thread-safe via a
connection-per-thread factory. No ORM, no services: the same design rule the
civic engine uses (SQLite instead of a broker/vector DB) applied to agent state.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    created REAL,
    updated REAL,
    mode TEXT,
    provider TEXT,
    model TEXT,
    workspace TEXT,
    meta TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    task TEXT,
    mode TEXT,
    status TEXT,          -- running | done | error | stopped
    provider TEXT,
    model TEXT,
    started REAL,
    finished REAL,
    error TEXT,
    summary TEXT,
    steps INTEGER DEFAULT 0,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    run_id TEXT,
    seq INTEGER,
    role TEXT,            -- system | user | assistant | tool | note
    content TEXT,
    tool_name TEXT,
    tool_args TEXT,
    tool_result TEXT,
    ok INTEGER,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created REAL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    worker TEXT,
    role TEXT,
    prompt TEXT,
    status TEXT,
    result TEXT,
    worktree TEXT,
    created REAL,
    finished REAL
);
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT,           -- global | project | session
    key TEXT,
    value TEXT,
    tags TEXT,
    created REAL,
    updated REAL,
    UNIQUE(scope, key)
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    ts REAL,
    tool TEXT,
    args TEXT,
    decision TEXT,        -- allow | deny | dry_run | confirm
    ok INTEGER,
    duration_ms INTEGER,
    result_hash TEXT,
    agent TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT,
    platform TEXT,
    token_hash TEXT,
    created REAL,
    last_seen REAL,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, started);
CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit(run_id, ts);
"""


def _now() -> float:
    return time.time()


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class Store:
    """Thread-safe SQLite store. Every worker thread gets its own connection."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._fts = False
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            self._fts = self._try_fts(conn)
            conn.commit()

    # -- plumbing -----------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Autocommit mode (isolation_level=None): each statement stands alone, so a
            # failed statement can never leave an implicit write transaction open and
            # deadlock every other connection. Explicit commits below stay harmless.
            conn.isolation_level = None
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.DatabaseError:
                pass
            self._local.conn = conn
        return conn

    def _try_fts(self, conn) -> bool:
        try:
            existing = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='memory_fts'").fetchone()
            if existing and "content=" in (existing[0] or ""):
                conn.execute("DROP TABLE memory_fts")  # old external-content form: unsafe
            conn.executescript(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(key, value, tags);")
            # keep a fresh index in sync with rows written by an older build
            count = conn.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0]
            rows = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
            if count == 0 and rows:
                conn.execute("INSERT INTO memory_fts (rowid,key,value,tags) "
                             "SELECT id,key,value,tags FROM memory")
            return True
        except sqlite3.DatabaseError:
            return False  # FTS5 not compiled in -> LIKE fallback

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def execute(self, sql, params=()):
        with self._lock:
            conn = self._conn()
            try:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur
            except sqlite3.Error:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise

    def query(self, sql, params=()) -> list[sqlite3.Row]:
        cur = self._conn().execute(sql, params)
        return cur.fetchall()

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # -- sessions -----------------------------------------------------------
    def create_session(self, title: str = "New session", mode: str = "single",
                       provider: str = "", model: str = "", workspace: str = "",
                       meta: dict | None = None) -> str:
        sid = new_id("s_")
        self.execute(
            "INSERT INTO sessions (id,title,created,updated,mode,provider,model,workspace,meta)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, title[:200], _now(), _now(), mode, provider, model, workspace,
             json.dumps(meta or {})),
        )
        return sid

    def touch_session(self, sid: str, title: str | None = None):
        if title:
            self.execute("UPDATE sessions SET updated=?, title=? WHERE id=?", (_now(), title[:200], sid))
        else:
            self.execute("UPDATE sessions SET updated=? WHERE id=?", (_now(), sid))

    def list_sessions(self, limit: int = 50) -> list[dict]:
        rows = self.query(
            "SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS n"
            " FROM sessions s ORDER BY updated DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def get_session(self, sid: str) -> dict | None:
        row = self.one("SELECT * FROM sessions WHERE id=?", (sid,))
        return dict(row) if row else None

    def rename_session(self, sid: str, title: str):
        self.execute("UPDATE sessions SET title=? WHERE id=?", (title[:200], sid))

    def delete_session(self, sid: str):
        self.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        self.execute("DELETE FROM runs WHERE session_id=?", (sid,))
        self.execute("DELETE FROM sessions WHERE id=?", (sid,))

    # -- runs ---------------------------------------------------------------
    def start_run(self, session_id: str, task: str, mode: str, provider: str, model: str) -> str:
        rid = new_id("r_")
        self.execute(
            "INSERT INTO runs (id,session_id,task,mode,status,provider,model,started)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (rid, session_id, task, mode, "running", provider, model, _now()),
        )
        return rid

    def finish_run(self, rid: str, status: str, summary: str = "", error: str = "",
                   steps: int = 0, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0):
        self.execute(
            "UPDATE runs SET status=?, finished=?, summary=?, error=?, steps=?,"
            " tokens_in=?, tokens_out=?, cost_usd=? WHERE id=?",
            (status, _now(), summary, error, steps, tokens_in, tokens_out, cost_usd, rid),
        )

    def get_run(self, rid: str) -> dict | None:
        row = self.one("SELECT * FROM runs WHERE id=?", (rid,))
        return dict(row) if row else None

    def list_runs(self, session_id: str | None = None, limit: int = 50) -> list[dict]:
        if session_id:
            rows = self.query("SELECT * FROM runs WHERE session_id=? ORDER BY started DESC LIMIT ?",
                              (session_id, limit))
        else:
            rows = self.query("SELECT * FROM runs ORDER BY started DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # -- messages -----------------------------------------------------------
    def add_message(self, session_id: str, run_id: str | None, role: str, content: str,
                    tool_name: str | None = None, tool_args=None, tool_result=None,
                    ok: int | None = None, tokens_in: int = 0, tokens_out: int = 0) -> int:
        seq_row = self.one(
            "SELECT COALESCE(MAX(seq),0)+1 AS s FROM messages WHERE session_id=?", (session_id,))
        seq = int(seq_row["s"]) if seq_row else 1
        cur = self.execute(
            "INSERT INTO messages (session_id,run_id,seq,role,content,tool_name,tool_args,"
            "tool_result,ok,tokens_in,tokens_out,created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, run_id, seq, role, content,
             tool_name,
             json.dumps(tool_args) if tool_args is not None else None,
             json.dumps(tool_result) if not isinstance(tool_result, (str, type(None))) else tool_result,
             ok, tokens_in, tokens_out, _now()),
        )
        self.touch_session(session_id)
        return int(cur.lastrowid)

    def get_messages(self, session_id: str, limit: int = 500) -> list[dict]:
        rows = self.query(
            "SELECT * FROM messages WHERE session_id=? ORDER BY seq ASC LIMIT ?", (session_id, limit))
        return [dict(r) for r in rows]

    # -- swarm tasks --------------------------------------------------------
    def add_task(self, run_id: str, worker: str, role: str, prompt: str, worktree: str = "") -> str:
        tid = new_id("t_")
        self.execute(
            "INSERT INTO tasks (id,run_id,worker,role,prompt,status,worktree,created)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (tid, run_id, worker, role, prompt, "queued", worktree, _now()),
        )
        return tid

    def update_task(self, tid: str, status: str, result: str = ""):
        self.execute("UPDATE tasks SET status=?, result=?, finished=? WHERE id=?",
                     (status, result, _now(), tid))

    def list_tasks(self, run_id: str) -> list[dict]:
        rows = self.query("SELECT * FROM tasks WHERE run_id=? ORDER BY created ASC", (run_id,))
        return [dict(r) for r in rows]

    # -- memory -------------------------------------------------------------
    def memo_set(self, key: str, value: str, scope: str = "global", tags: str = "") -> int:
        existing = self.one("SELECT id FROM memory WHERE scope=? AND key=?", (scope, key))
        if existing:
            self.execute("UPDATE memory SET value=?, tags=?, updated=? WHERE id=?",
                         (value, tags, _now(), existing["id"]))
            mid = int(existing["id"])
        else:
            cur = self.execute(
                "INSERT INTO memory (scope,key,value,tags,created,updated) VALUES (?,?,?,?,?,?)",
                (scope, key, value, tags, _now(), _now()))
            mid = int(cur.lastrowid)
        if self._fts:
            try:
                self.execute("DELETE FROM memory_fts WHERE rowid=?", (mid,))
                self.execute("INSERT INTO memory_fts (rowid,key,value,tags) VALUES (?,?,?,?)",
                             (mid, key, value, tags))
            except sqlite3.DatabaseError:
                self._fts = False  # fall back to LIKE rather than risk a stuck index
        return mid

    def memo_get(self, key: str, scope: str = "global") -> str | None:
        row = self.one("SELECT value FROM memory WHERE scope=? AND key=?", (scope, key))
        return row["value"] if row else None

    def memo_search(self, term: str, limit: int = 20) -> list[dict]:
        if self._fts:
            try:
                rows = self.query(
                    "SELECT m.* FROM memory_fts f JOIN memory m ON m.id=f.rowid"
                    " WHERE memory_fts MATCH ? LIMIT ?", (term, limit))
                if rows:
                    return [dict(r) for r in rows]
            except sqlite3.DatabaseError:
                pass
        like = f"%{term}%"
        rows = self.query(
            "SELECT * FROM memory WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? LIMIT ?",
            (like, like, like, limit))
        return [dict(r) for r in rows]

    def memo_all(self, limit: int = 200) -> list[dict]:
        return [dict(r) for r in self.query("SELECT * FROM memory ORDER BY updated DESC LIMIT ?", (limit,))]

    # -- audit --------------------------------------------------------------
    def audit(self, run_id: str | None, tool: str, args, decision: str, ok: bool,
              duration_ms: int = 0, result_hash: str = "", agent: str = ""):
        self.execute(
            "INSERT INTO audit (run_id,ts,tool,args,decision,ok,duration_ms,result_hash,agent)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, _now(), tool, json.dumps(args, default=str)[:4000], decision,
             1 if ok else 0, duration_ms, result_hash, agent))

    def list_audit(self, run_id: str | None = None, limit: int = 200) -> list[dict]:
        if run_id:
            rows = self.query("SELECT * FROM audit WHERE run_id=? ORDER BY ts ASC LIMIT ?",
                              (run_id, limit))
        else:
            rows = self.query("SELECT * FROM audit ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # -- devices ------------------------------------------------------------
    def add_device(self, name: str, platform: str, token_hash: str, user_agent: str = "") -> str:
        did = new_id("d_")
        self.execute(
            "INSERT INTO devices (id,name,platform,token_hash,created,last_seen,user_agent)"
            " VALUES (?,?,?,?,?,?,?)",
            (did, name[:80], platform[:40], token_hash, _now(), _now(), user_agent[:300]))
        return did

    def list_devices(self) -> list[dict]:
        return [dict(r) for r in self.query("SELECT * FROM devices ORDER BY last_seen DESC")]

    def find_device_by_token(self, token_hash: str) -> dict | None:
        row = self.one("SELECT * FROM devices WHERE token_hash=?", (token_hash,))
        return dict(row) if row else None

    def seed_device(self, token_hash: str, name: str = "primary"):
        if not self.one("SELECT id FROM devices WHERE token_hash=?", (token_hash,)):
            self.add_device(name, "unknown", token_hash)
