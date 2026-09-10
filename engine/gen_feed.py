"""gen_feed.py — publish public/feed.xml (RSS 2.0) from the engine ledger.

Runs at the end of every civic cycle so alerts + silent edits push outward:
RSS readers, IFTTT/Zapier relays, or anything else that polls a feed.
Feed URL once committed: the raw.githubusercontent URL of public/feed.xml.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path


def _esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def main():
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    try:
        from engine import db
    except Exception:
        print("gen_feed: engine unavailable, skipping")
        return
    if not (root / "data" / "engine.db").exists():
        print("gen_feed: no engine.db yet, skipping")
        return

    conn = db.connect()
    items = []
    for r in conn.execute(
            "SELECT a.created_at ts, a.term, a.snippet, d.url, d.title "
            "FROM alerts a JOIN documents d ON d.id=a.document_id "
            "ORDER BY a.id DESC LIMIT 40"):
        items.append((r["ts"], f"WATCHLIST: “{r['term']}” — {r['title']}",
                      r["url"], r["snippet"]))
    for r in conn.execute(
            "SELECT v.captured_at ts, v.change_summary, d.url, d.title "
            "FROM versions v JOIN documents d ON d.id=v.document_id "
            "WHERE v.seq>1 ORDER BY v.id DESC LIMIT 20"):
        items.append((r["ts"], f"SILENT EDIT: {r['title']}", r["url"],
                      r["change_summary"]))
    conn.close()
    items.sort(key=lambda x: x[0] or "", reverse=True)
    items = items[:50]

    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    body = "\n".join(
        f"""  <item><title>{_esc(t)}</title><link>{_esc(u)}</link>
    <description>{_esc(s)}</description><pubDate>{_esc(ts)}</pubDate>
    <guid isPermaLink="true">{_esc(u)}#{_esc(ts)}</guid></item>"""
        for ts, t, u, s in items)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>The Real Windy City — Civic Ledger Alerts</title>
<link>https://github.com/bartimoussmith-oss/therealwindycity</link>
<description>Verbatim-quote watchlist hits and silent-edit detections from the automated civic ledger. Public documents only.</description>
<lastBuildDate>{now}</lastBuildDate>
{body}
</channel></rss>"""
    out = root / "public" / "feed.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(xml)
    print(f"gen_feed: {len(items)} items -> {out}")


if __name__ == "__main__":
    main()
