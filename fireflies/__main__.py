"""CLI for the Fireflies-style meeting intelligence ledger.

  python3 -m fireflies build [--limit N] [--out DIR] [--repo DIR]
  python3 -m fireflies brief <date|meeting_id> [--body SLUG] [--repo DIR]
  python3 -m fireflies search "query" [--body SLUG] [--year YYYY] [--max N] [--json]
  python3 -m fireflies topics [term] [--year YYYY] [--repo DIR]
  python3 -m fireflies tracker [--body SLUG] [--year YYYY] [--repo DIR]
  python3 -m fireflies verify [--repo DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .build import build_ledger, verify_ledger
from .search import search as run_search
from .sources import load_meetings
from .topics import term_timeline

DEFAULT_REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path(__file__).resolve().parent


def _out_dir(repo: Path) -> Path:
    """Ledger lives in <repo>/fireflies by default; --out layouts write
    <out>/ledger directly. Resolve whichever exists."""
    repo = Path(repo)
    if (repo / "fireflies" / "ledger" / "meetings.jsonl").exists():
        return repo / "fireflies"
    return repo


def _load_ledger(repo: Path) -> list:
    p = _out_dir(repo) / "ledger" / "meetings.jsonl"
    if not p.exists():
        sys.exit("No ledger found — run `python3 -m fireflies build` first.")
    return [json.loads(line) for line in p.open(encoding="utf-8") if line.strip()]


def cmd_build(a):
    stats = build_ledger(Path(a.repo), Path(a.out), limit=a.limit)
    print(json.dumps(stats, indent=1))
    print(f"\nBriefs: {a.out}/briefs/  Ledger: {a.out}/ledger/")
    return 0


def cmd_brief(a):
    for rec in _load_ledger(Path(a.repo)):
        if (a.query in rec["meeting_id"] or a.query in rec["date"]
                or a.query in rec["title"]):
            if a.body and rec["body"] != a.body:
                continue
            print((_out_dir(Path(a.repo)) / "briefs" /
                   f"{rec['meeting_id']}.md").read_text(encoding="utf-8"))
            return 0
    sys.exit(f"No meeting matching {a.query!r} (tip: pass a date like 2026-08-24)")
    return 1


def cmd_search(a):
    meetings = load_meetings(Path(a.repo))
    hits = run_search(a.query, meetings, body=a.body, year=a.year, max_hits=a.max)
    if a.json:
        print(json.dumps(hits, ensure_ascii=False, indent=1))
        return 0
    if not hits:
        print("No hits.")
        return 0
    for h in hits:
        loc = h["locator"]
        tag = loc.get("ts") or (f"¶{loc['para']}" if loc.get("para") else loc["ref"])
        print(f"[{h['date'] or 'undated'}] {h['body']} ({h['meeting_id']}) — {tag}")
        s, e = h["match_start"], h["match_end"]
        print(f"   …{h['snippet'][:s]}[[{h['snippet'][s:e]}]]{h['snippet'][e:]}…")
    return 0


def cmd_topics(a):
    ledger = _load_ledger(Path(a.repo))
    if not a.term:
        topics = json.loads((_out_dir(Path(a.repo)) / "ledger" / "topics.json")
                            .read_text(encoding="utf-8"))
        ents = topics["entities"]
        if a.year:
            ents = [e for e in ents if any(m["date"].startswith(a.year)
                                           for m in e["meetings"])]
        for e in ents[:40]:
            print(f"{e['type']:11s} {e['value']:12s} ×{e['mentions']:<4d} "
                  f"meetings:{len(e['meetings']):<3d} {e['first_seen']} → {e['last_seen']}")
        return 0
    meetings = load_meetings(Path(a.repo))
    rows = term_timeline(a.term, meetings,
                         corpus_texts=lambda mt: mt.texts, )
    if a.year:
        rows = [r for r in rows if (r["date"] or "").startswith(a.year)]
    for r in rows:
        ex = (r["example"] or {}).get("quote", "")
        ts = ((r["example"] or {}).get("locator") or {}).get("ts", "")
        print(f"[{r['date'] or 'undated'}] {r['body']} ×{r['count']} {ts}")
        if ex:
            print(f"   “{ex[:160]}”")
    if not rows:
        print("No mentions.")
    return 0


def cmd_tracker(a):
    ledger = _load_ledger(Path(a.repo))
    n = 0
    for rec in ledger:
        if a.body and rec["body"] != a.body:
            continue
        if a.year and not (rec["date"] or "").startswith(a.year):
            continue
        for it in rec["items"]:
            o = next((o for o in rec["outline"] if o["item_id"] == it["item_id"]), {})
            acts = [act for act in rec["actions"] if act["item_id"] == it["item_id"]]
            n += 1
            print(f"{rec['date'] or 'undated':10s} {rec['body']:26s} {it['item_id']} "
                  f"{it['title'][:90]}")
            if o.get("start"):
                print(f"    chapter {o['start']}–{o.get('end', '')} ({o['method']})")
            for d in it["docs"][:3]:
                print(f"    doc: {d.get('title', '')[:70]} — {d.get('url') or d.get('ref', '')}")
            for act in acts[:4]:
                print(f"    {act['type']}: “{act['quote'][:120]}”")
    print(f"\n{n} agenda items.")
    return 0


def cmd_verify(a):
    report = verify_ledger(Path(a.repo),
                           _out_dir(Path(a.repo)) / "ledger" / "meetings.jsonl")
    print(f"quotes checked: {report['checked']}  failures: {len(report['bad'])}")
    for b in report["bad"][:20]:
        print(f"  BAD [{b['meeting_id']}] {b['where']}: {b['quote']!r}")
    return 0 if report["ok"] else 2


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fireflies", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=str(DEFAULT_REPO))
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build briefs + ledger over the corpus",
                       parents=[common])
    b.add_argument("--out", default=str(DEFAULT_OUT))
    b.add_argument("--limit", type=int, default=None)
    b.set_defaults(fn=cmd_build)

    p = sub.add_parser("brief", help="print one meeting brief", parents=[common])
    p.add_argument("query")
    p.add_argument("--body", default=None)
    p.set_defaults(fn=cmd_brief)

    s = sub.add_parser("search", help="search every source text", parents=[common])
    s.add_argument("query")
    s.add_argument("--body", default=None)
    s.add_argument("--year", default=None)
    s.add_argument("--max", type=int, default=25)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_search)

    t = sub.add_parser("topics", help="entity timelines / term timeline",
                       parents=[common])
    t.add_argument("term", nargs="?", default=None)
    t.add_argument("--year", default=None)
    t.set_defaults(fn=cmd_topics)

    k = sub.add_parser("tracker", help="agenda item tracker (flat view)",
                       parents=[common])
    k.add_argument("--body", default=None)
    k.add_argument("--year", default=None)
    k.set_defaults(fn=cmd_tracker)

    v = sub.add_parser("verify", help="re-check every stored quote against sources",
                       parents=[common])
    v.set_defaults(fn=cmd_verify)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
