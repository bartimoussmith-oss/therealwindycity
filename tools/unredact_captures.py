#!/usr/bin/env python3
"""Put the names back into arrest-report captures that ingest redacted (owner decision 2026-11-27).

engine/redact.py used to replace every person name in a weekly arrest report with
"[WITHHELD]" before the capture was committed. The owner has since asked for the arrest
records to be published unredacted. This tool restores the names in:

  * data/snapshots/*arrest-report*   (raw captures)
  * data/text/*.txt                  (extracted text)
  * data/engine.db                   (documents / search index text)

For every "[WITHHELD] - <charges>" line it takes the name from an UNREDACTED copy of the same
report -- another capture in data/snapshots/ that has no placeholder, or the article itself
(fetched from its source URL) -- matching on the charge text, in order. A line with no
matching entry stops the run; nothing is guessed.

    python3 tools/unredact_captures.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from publish_arrest_names import norm, parse_capture  # noqa: E402

PH = "[WITHHELD]"
LINE = re.compile(r"\[WITHHELD\](\s*[\u2013\u2014-]\s*)([^<\n\r]+)")
SLUG = re.compile(r"arrest-report-(\d{1,2}-\d{1,2}-\d{2})-(\d{1,2}-\d{1,2}-\d{2})")
TITLE = re.compile(r"arrest report \((\d{1,2})/(\d{1,2})/(\d{2})\s*[\u2013\u2014-]\s*(\d{1,2})/(\d{1,2})/(\d{2})\)")


def slug_of(text: str, name: str = "") -> str | None:
    m = SLUG.search(name) or SLUG.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = TITLE.search(text)
    return "-".join(m.groups()[:3]) + "-" + "-".join(m.groups()[3:]) if m else None


def source_entries(slug: str, text: str, cache: dict) -> list[dict]:
    if slug in cache:
        return cache[slug]
    ents: list[dict] = []
    for snap in sorted((ROOT / "data" / "snapshots").glob(f"*arrest-report-{slug}*")):
        raw = snap.read_text(errors="ignore")
        if PH not in raw:
            ents = parse_capture(raw)
            if ents:
                break
    if not ents:
        m = re.search(r"https://capcity\.news/crime/[^\s\"'<>]*" + re.escape(slug) + r"/?", text)
        url = m.group(0) if m else None
        if url:
            raw = subprocess.run(["curl", "-sL", "-A", "Mozilla/5.0", "-m", "60", url],
                                 capture_output=True, text=True).stdout
            ents = parse_capture(raw)
    cache[slug] = ents
    return ents


def fill(text: str, ents: list[dict]) -> tuple[str, int, list[str]]:
    pool: dict[str, list[str]] = {}
    for e in ents:
        pool.setdefault(norm(e["ch"]), []).append(e["name"])
    used: dict[str, int] = {}
    missing: list[str] = []

    def sub(m):
        k = norm(m.group(2))
        i = used.get(k, 0)
        names = pool.get(k) or []
        if i >= len(names):
            missing.append(m.group(2)[:60])
            return m.group(0)
        used[k] = i + 1
        return names[i] + m.group(1) + m.group(2)

    out, n = LINE.subn(sub, text)
    return out, n - len(missing), missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cache: dict = {}
    problems: list[str] = []
    changed = 0
    files = [p for d in ("data/snapshots", "data/text") for p in sorted((ROOT / d).glob("*")) if p.is_file()]
    for p in files:
        t = p.read_text(errors="ignore")
        if PH not in t:
            continue
        slug = slug_of(t, p.name)
        ents = source_entries(slug, t, cache) if slug else []
        new, n, miss = fill(t, ents)
        if miss or PH in new:
            problems.append(f"{p.relative_to(ROOT)}: {len(miss)} unmatched ({miss[:2]})")
            continue
        changed += 1
        print(f"{p.relative_to(ROOT)}: {n} names restored (report {slug})")
        if not a.dry_run:
            p.write_text(new, encoding="utf-8")
    db = ROOT / "data" / "engine.db"
    if db.exists():
        con = sqlite3.connect(db)
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        # FTS5 shadow tables (<fts>_data/_idx/_content/_docsize/_config) are maintained by SQLite;
        # writing them directly would desync the index. Update through the virtual table only.
        virt = [r[0] for r in con.execute("select name from sqlite_master where sql like 'CREATE VIRTUAL TABLE%'")]
        tables = [t for t in tables if not any(t.startswith(v + "_") for v in virt)]
        for tb in tables:
            try:
                cols = [r[1] for r in con.execute(f'pragma table_info("{tb}")') if r[2].upper() in ("TEXT", "")]
                rowid = "rowid"
                for c in cols:
                    rows = con.execute(f'select {rowid}, "{c}" from "{tb}" where "{c}" like ?',
                                       (f"%{PH}%",)).fetchall()
                    for rid, val in rows:
                        slug = slug_of(val)
                        ents = source_entries(slug, val, cache) if slug else []
                        new, n, miss = fill(val, ents)
                        if miss or PH in new:
                            problems.append(f"engine.db {tb}.{c} row {rid}: {len(miss)} unmatched")
                            continue
                        print(f"engine.db {tb}.{c} row {rid}: {n} names restored (report {slug})")
                        changed += 1
                        if not a.dry_run:
                            con.execute(f'update "{tb}" set "{c}"=? where {rowid}=?', (new, rid))
            except sqlite3.DatabaseError as e:     # virtual FTS shadow tables etc.
                if PH in str(e):
                    problems.append(f"engine.db {tb}: {e}")
        if not a.dry_run:
            con.commit()
        con.close()
    if problems:
        print("NOT restored:", *problems, sep="\n  ")
        return 3
    print(f"done: {changed} captures/rows restored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
