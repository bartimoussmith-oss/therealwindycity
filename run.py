#!/usr/bin/env python3
"""Civic Transparency Engine — CLI entry point.

Commands:
  selftest   Prove Modules 1-5 offline using synthetic fixtures (no network).
  init       Create the database and sync config.
  crawl      Politely pull all enabled sources (Module 1), queue jobs (Module 2).
  work       Process queued jobs: extract, index, scan, diff (Modules 3).
  search Q   Plain-English full-text search across every captured document.
  digest     Write data/out/digest-<today>.md (Module 5).
  request    Draft a Wyoming PRA request or public comment (saved as DRAFT).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from engine import analyze, db, digest, ingest, records
from engine.extract import process_jobs


def _fail(msg: str):
    print(f"SELFTEST FAIL: {msg}")
    sys.exit(1)


def cmd_selftest(_args):
    print("== Civic Transparency Engine selftest (offline, zero deps) ==\n")
    report = db.init_db()
    print(f"[1] storage initialized -> {report['db']} (FTS5: {report['fts_enabled']})")

    fix = db.DATA / "selftest"
    if fix.exists():
        shutil.rmtree(fix)
    fix.mkdir(parents=True)
    (fix / "minutes-2026-08-18.txt").write_text(
        "Finance Committee minutes. The committee considered a $186,500 contract "
        "with a consultant to study the roundabout at Pershing and Converse. "
        "Discussion also touched on the administrative warrant ordinance in "
        "Chapter 1.28 of the municipal code.")
    page = ('<html><body><h1>Agenda preview</h1>'
            '<p>The council will consider the proposed data center annexation '
            'and a resolution on reclaimed water fill-and-flush discharges.</p>'
            '</body></html>')
    (fix / "agenda-preview.html").write_text(page)

    conn = db.connect()
    ingest.crawl_fixture(conn, "fixture_city_hall", str(fix))
    process_jobs(conn, kinds=("extract", "diff"))

    assert digest.stats(conn)["documents"] >= 2, _fail("documents not tracked")
    hits = db.search(conn, '"data center"') or db.search(conn, "data")
    assert hits, _fail("full-text search returned nothing")
    alerts = digest.stats(conn)["alerts"]
    assert alerts > 0, _fail("watchlist produced no alerts")
    print(f"[2] ingestion + extraction OK: 2 docs indexed, search hits "
          f"{len(hits)}, watchlist alerts {alerts}")

    (fix / "minutes-2026-08-18.txt").write_text(
        "Finance Committee minutes. The committee considered a $286,500 contract "
        "with a consultant to study the roundabout at Pershing and Converse. "
        "The vote was taken after an executive session not listed on the agenda.")
    ingest.crawl_fixture(conn, "fixture_city_hall", str(fix))
    process_jobs(conn, kinds=("extract", "diff"))

    st = digest.stats(conn)
    assert st["silent_edits"] >= 1, _fail("silent edit not detected")
    v = conn.execute(
        "SELECT change_summary FROM versions WHERE seq = 2").fetchone()
    print(f"[3] silent-edit detector OK: version 2 -> '{v['change_summary']}'")

    result = analyze.Summarizer().summarize(
        "The council approved the annexation. The vote was six to three. "
        "Residents filed a referendum petition the following week. The clerk "
        "began verifying signatures. The mayor asked the city attorney to seek "
        "a court ruling. The ordinance remains suspended during verification.")
    assert result["method"] == "extractive-offline"
    print(f"[4] analysis OK (method={result['method']}): "
          + result["summary"].splitlines()[0][:78] + "…")

    body = records.generate_pra(
        conn,
        records_description=("All engineering studies, draft scopes of work, and "
                             "correspondence regarding the Pershing/Converse/19th "
                             "roundabout operational analysis"),
        date_range="2026-01-01 to present")
    assert "16-4-201" in body
    print("[5] Wyoming PRA draft generated and stored as DRAFT (human sends it)")

    body = digest.build_digest(conn, days=2)
    assert "SILENT EDIT" in body or "SILENT-EDIT" in body
    print(f"[6] digest written -> {db.OUT_DIR}")
    print("\nSELFTEST PASS — all modules operational. Remove data/selftest* and run"
          " `python3 run.py init && python3 run.py crawl` to go live.")


def cmd_init(_args):
    report = db.init_db()
    conn = db.connect()
    n = db.sync_sources(conn)
    print(f"Initialized {report['db']} (FTS5: {report['fts_enabled']}) "
          f"with {n} configured sources.")
    for row in conn.execute("SELECT name, enabled, notes FROM sources"):
        flag = "ON " if row["enabled"] else "OFF"
        print(f"  [{flag}] {row['name']:<28} {row['notes'][:70]}")


def cmd_crawl(_args):
    conn = db.connect()
    total = ingest.crawl_all(conn)
    print(f"\nCrawl complete: {total} link(s) processed. Run `python3 run.py work`.")


def cmd_work(_args):
    conn = db.connect()
    done = process_jobs(conn, kinds=("extract", "diff"))
    print(f"Queue drained: {done} job(s).")


def cmd_search(args):
    conn = db.connect()
    rows = db.search(conn, args.query)
    if not rows:
        print("No matches.")
        return
    for r in rows:
        print(f"doc #{r['doc_id']} [{r['source']}] {r['title']}")
        print(f"   {r.get('snip', '')}\n")


def cmd_digest(args):
    conn = db.connect()
    body = digest.build_digest(conn, days=args.days)
    print(body)
    print(digest.stats(conn))


def cmd_request(args):
    conn = db.connect()
    if args.kind == "pra":
        print(records.generate_pra(conn, records_description=args.description,
                                   date_range=args.date_range))
    else:
        print(records.generate_public_comment(
            conn, body_name=args.body_name, agenda_item=args.description,
            meeting_date=args.date_range, position=args.position or "[POSITION]",
            ask=args.ask or "[SPECIFIC ASK]",
            fact_bullets=args.facts or "  - [fact + citation]"))
    print("\n(Stored in DB as a DRAFT; also written to data/out/. You send it.)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    sub.add_parser("init")
    sub.add_parser("crawl")
    sub.add_parser("work")
    p = sub.add_parser("search"); p.add_argument("query")
    p = sub.add_parser("digest"); p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("request")
    p.add_argument("kind", choices=["pra", "comment"])
    p.add_argument("description", help="records sought (pra) or agenda item (comment)")
    p.add_argument("date_range", help="e.g. '2026-01-01 to present' or meeting date")
    p.add_argument("--position"); p.add_argument("--ask"); p.add_argument("--facts")
    args = ap.parse_args()
    {"selftest": cmd_selftest, "init": cmd_init, "crawl": cmd_crawl,
     "work": cmd_work, "search": cmd_search, "digest": cmd_digest,
     "request": cmd_request}[args.cmd](args)


if __name__ == "__main__":
    main()
