"""Module 5 (reporting): the daily evidence digest.

Everything printed here carries its source URL and fetch timestamp. Sections
with zero items are omitted — a quiet day is a true report too.
"""
from __future__ import annotations

from . import db


def build_digest(conn, days: int = 7) -> str:
    lines: list[str] = []
    today = db.utcnow()[:10]
    lines.append(f"# Civic Transparency Digest — {today}")
    lines.append(f"_Window: trailing {days} days · All items link to source "
                 f"captures in data/snapshots/_\n")

    new_docs = conn.execute(
        "SELECT d.id, d.title, d.url, d.source, d.first_seen FROM documents d"
        " WHERE d.first_seen >= datetime('now', ?) ORDER BY d.first_seen DESC",
        (f"-{days} days",),
    ).fetchall()
    if new_docs:
        lines.append(f"\n## New documents ({len(new_docs)})")
        for r in new_docs:
            lines.append(f"- [{r['title'] or r['url']}]({r['url']}) "
                         f"· `{r['source']}` · first seen {r['first_seen']}")

    edits = conn.execute(
        "SELECT v.document_id, v.seq, v.captured_at, v.change_summary, d.url, d.title"
        " FROM versions v JOIN documents d ON d.id = v.document_id"
        " WHERE v.seq > 1 AND v.captured_at >= datetime('now', ?)"
        " ORDER BY v.captured_at DESC",
        (f"-{days} days",),
    ).fetchall()
    if edits:
        lines.append(f"\n## SILENT EDITS DETECTED ({len(edits)})")
        lines.append("_A hash change on an already-published document._")
        for r in edits:
            lines.append(f"- **doc #{r['document_id']}** [{r['title']}]({r['url']}) "
                         f"— seq {r['seq']} at {r['captured_at']}: "
                         f"{r['change_summary']}")

    alerts = conn.execute(
        "SELECT a.term, a.snippet, a.created_at, d.url, d.title"
        " FROM alerts a JOIN documents d ON d.id = a.document_id"
        " WHERE a.created_at >= datetime('now', ?)"
        " ORDER BY a.term, a.created_at DESC",
        (f"-{days} days",),
    ).fetchall()
    if alerts:
        lines.append(f"\n## Watchlist hits ({len(alerts)})")
        current = None
        for r in alerts:
            if r["term"] != current:
                current = r["term"]
                lines.append(f"\n### `{current}`")
            lines.append(f"- {r['created_at']} — [{r['title']}]({r['url']})")
            lines.append(f"  > {r['snippet']}")

    drafts = conn.execute(
        "SELECT id, kind, subject, created_at FROM requests"
        " WHERE created_at >= datetime('now', ?) ORDER BY id DESC",
        (f"-{days} days",),
    ).fetchall()
    if drafts:
        lines.append(f"\n## Drafted requests awaiting a human ({len(drafts)})")
        for r in drafts:
            lines.append(f"- #{r['id']} [{r['kind']}] {r['subject']} "
                         f"(filed {r['created_at']}) — send manually")

    body = "\n".join(lines) + "\n"
    out = db.OUT_DIR / f"digest-{today}.md"
    out.write_text(body)
    return body


def stats(conn) -> dict:
    def one(q):
        return conn.execute(q).fetchone()[0]
    return {
        "sources_enabled": one("SELECT COUNT(*) FROM sources WHERE enabled=1"),
        "documents": one("SELECT COUNT(*) FROM documents"),
        "versions": one("SELECT COUNT(*) FROM versions"),
        "silent_edits": one("SELECT COUNT(*) FROM versions WHERE seq > 1"),
        "alerts": one("SELECT COUNT(*) FROM alerts"),
        "draft_requests": one("SELECT COUNT(*) FROM requests WHERE status='draft'"),
        "jobs_queued": one("SELECT COUNT(*) FROM jobs WHERE status='queued'"),
    }
