"""Module 4 (storage) + Module 2 (routing).

One SQLite file serves three jobs:
  1. Relational ledger: sources, documents, versions, alerts, drafted requests.
  2. Full-text search: FTS5 virtual table (auto-falls back to LIKE if the build
     lacks FTS5).
  3. Job queue (Module 2 semantics): ingest enqueues lightweight messages like
     ("extract", document_id); heavy workers dequeue and process at their own
     pace. To swap in RabbitMQ/Kafka later, reimplement enqueue_job/dequeue_job.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAP_DIR = DATA / "snapshots"
TEXT_DIR = DATA / "text"
OUT_DIR = DATA / "out"
DB_PATH = DATA / "engine.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'html',
    enabled INTEGER NOT NULL DEFAULT 1,
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    title TEXT DEFAULT '',
    first_seen TEXT NOT NULL,
    last_checked TEXT NOT NULL,
    published_at TEXT DEFAULT '',
    local_path TEXT DEFAULT '',
    sha256 TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    status TEXT DEFAULT 'downloaded'
);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    change_summary TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    snippet TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, term, snippet)
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    processed_at TEXT DEFAULT ''
);
"""


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> dict:
    for d in (DATA, SNAP_DIR, TEXT_DIR, OUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
        fts_enabled = True
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS text_index USING "
                "fts5(title, content, doc_id UNINDEXED, source UNINDEXED)"
            )
        except sqlite3.OperationalError:
            fts_enabled = False
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('fts_enabled', ?)",
            ("1" if fts_enabled else "0",),
        )
    conn.close()
    return {"db": str(DB_PATH), "fts_enabled": fts_enabled}


def load_config() -> dict:
    cfg_path = ROOT / "config" / "sources.json"
    return json.loads(cfg_path.read_text())


def load_watchlist() -> list[tuple[str, str]]:
    wl_path = ROOT / "config" / "watchlist.json"
    raw = json.loads(wl_path.read_text())
    pairs = []
    for topic, terms in raw.get("topics", {}).items():
        for term in terms:
            pairs.append((topic, term))
    return pairs


def sync_sources(conn: sqlite3.Connection) -> int:
    cfg = load_config()
    n = 0
    with conn:  # type: ignore[attr-defined]
        for s in cfg.get("sources", []):
            conn.execute(
                "INSERT OR REPLACE INTO sources (name, url, type, enabled, notes)"
                " VALUES (?, ?, ?, ?, ?)",
                (s["name"], s["url"], s.get("type", "html"),
                 1 if s.get("enabled", False) else 0, s.get("notes", "")),
            )
            n += 1
    return n


def get_document_by_url(conn: sqlite3.Connection, url: str):
    return conn.execute("SELECT * FROM documents WHERE url = ?", (url,)).fetchone()


def insert_document(conn, source, url, title, local_path, sha256, size, published_at=""):
    now = utcnow()
    with conn:
        cur = conn.execute(
            "INSERT INTO documents (source, url, title, first_seen, last_checked,"
            " published_at, local_path, sha256, size_bytes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (source, url, title, now, now, published_at, local_path, sha256, size),
        )
        doc_id = cur.lastrowid
        conn.execute(
            "INSERT INTO versions (document_id, seq, sha256, captured_at, change_summary)"
            " VALUES (?, 1, ?, ?, 'initial capture')",
            (doc_id, sha256, now),
        )
    return doc_id


def bump_hash(conn, doc_id: int, sha256: str, local_path: str, size: int) -> int:
    """Existing URL, new hash -> new version row. Returns new seq number."""
    now = utcnow()
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS m FROM versions WHERE document_id = ?",
        (doc_id,),
    ).fetchone()
    seq = row["m"] + 1
    with conn:
        conn.execute(
            "INSERT INTO versions (document_id, seq, sha256, captured_at, change_summary)"
            " VALUES (?, ?, ?, ?, ?)",
            (doc_id, seq, sha256, now, f"hash changed (seq {seq}); diff pending"),
        )
        conn.execute(
            "UPDATE documents SET sha256 = ?, local_path = ?, size_bytes = ?,"
            " last_checked = ? WHERE id = ?",
            (sha256, local_path, size, now, doc_id),
        )
    return seq


def touch_checked(conn, doc_id: int):
    with conn:
        conn.execute("UPDATE documents SET last_checked = ? WHERE id = ?",
                     (utcnow(), doc_id))


def index_text(conn, doc_id: int, source: str, title: str, content: str):
    text_path = TEXT_DIR / f"{doc_id}.txt"
    text_path.write_text(content, errors="replace")
    fts = conn.execute("SELECT value FROM meta WHERE key='fts_enabled'").fetchone()
    with conn:
        if fts and fts["value"] == "1":
            conn.execute("DELETE FROM text_index WHERE doc_id = ?", (doc_id,))
            conn.execute(
                "INSERT INTO text_index (title, content, doc_id, source)"
                " VALUES (?, ?, ?, ?)",
                (title, content, str(doc_id), source),
            )
        conn.execute(
            "UPDATE documents SET status = 'indexed' WHERE id = ?", (doc_id,)
        )
    return str(text_path)


def search(conn, query: str) -> list[dict]:
    fts = conn.execute("SELECT value FROM meta WHERE key='fts_enabled'").fetchone()
    if fts and fts["value"] == "1":
        rows = conn.execute(
            "SELECT doc_id, title, source, snippet(text_index, 1, '[', ']', '…', 12) AS snip"
            " FROM text_index WHERE text_index MATCH ? ORDER BY rank LIMIT 50",
            (query,),
        ).fetchall()
    else:
        rows = []
        for r in conn.execute("SELECT id, title, source FROM documents").fetchall():
            p = TEXT_DIR / f"{r['id']}.txt"
            if p.exists() and query.lower() in p.read_text(errors="replace").lower():
                rows.append({"doc_id": r["id"], "title": r["title"],
                             "source": r["source"], "snip": "(LIKE fallback match)"})
    return [dict(r) for r in rows]


def record_alert(conn, doc_id: int, term: str, snippet: str):
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO alerts (document_id, term, snippet, created_at)"
            " VALUES (?, ?, ?, ?)",
            (doc_id, term, snippet, utcnow()),
        )


def enqueue_job(conn, kind: str, payload: dict):
    with conn:
        conn.execute(
            "INSERT INTO jobs (kind, payload, created_at) VALUES (?, ?, ?)",
            (kind, json.dumps(payload), utcnow()),
        )


def dequeue_job(conn) -> dict | None:
    row = conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        return None
    with conn:
        conn.execute(
            "UPDATE jobs SET status = 'done', processed_at = ? WHERE id = ?",
            (utcnow(), row["id"]),
        )
    return {"id": row["id"], "kind": row["kind"], "payload": json.loads(row["payload"])}


def save_request(conn, kind: str, subject: str, body: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO requests (kind, subject, body, created_at) VALUES (?, ?, ?, ?)",
            (kind, subject, body, utcnow()),
        )
        rid = cur.lastrowid
    out = OUT_DIR / f"request-{rid:04d}-{kind}.md"
    out.write_text(body)
    return rid
