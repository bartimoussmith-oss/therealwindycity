#!/usr/bin/env python3
"""Check the provenance ledger is complete, and that a rendered site carries it.

Run after `python3 -m provenance ledger` and `tools/render_ai_record.py`:

    python3 tools/check_provenance.py --ledger data/out/provenance-ledger.json
    python3 tools/check_provenance.py --ledger data/out/provenance-ledger.json --site _site

It exits non-zero when a datum has no origin link, no film cue, a cue pointing at a
clip that does not exist, or when a site page has no provenance section. The point is
to make "every datum is linked or filmed" a build-time fact rather than a claim.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default="data/out/provenance-ledger.json")
    ap.add_argument("--site", default="", help="a rendered _site directory to inspect")
    ap.add_argument("--min-datums", type=int, default=100)
    ap.add_argument("--allow-external-origin", action="store_true", default=True,
                    help="origins may be any http(s) URL (this is the normal case)")
    a = ap.parse_args(argv)

    problems: list[str] = []
    led_path = Path(a.ledger)
    if not led_path.exists():
        print(f"MISSING ledger: {led_path}", file=sys.stderr)
        return 2
    ledger = json.loads(led_path.read_text(encoding="utf-8"))
    data = ledger.get("data", [])
    totals = ledger.get("totals", {})

    if len(data) < a.min_datums:
        problems.append(f"only {len(data)} datums (expected at least {a.min_datums})")

    no_link, no_cue, bad_cue, bad_origin = [], [], [], []
    for d in data:
        origin = (d.get("origin") or {}).get("url", "")
        if not origin.startswith(("http://", "https://")):
            bad_origin.append(d["id"])
        cue = d.get("cue") or {}
        if not cue.get("src"):
            no_cue.append(d["id"])
        elif not Path(cue["src"]).exists():
            bad_cue.append(f"{d['id']} → {cue['src']}")
        if not (d.get("how") or "").strip():
            no_link.append(f"{d['id']} (no click-path)")

    for label, items in (("no click-path", no_link), ("no film cue", no_cue),
                         ("cue clip missing", bad_cue),
                         ("origin is not a public URL", bad_origin)):
        if items:
            problems.append(f"{len(items)} datums with {label}: {items[:4]}")

    # every datum must be reachable from a page: a site block, or the cue sheet
    if a.site:
        site = Path(a.site)
        pages = [p for p in site.rglob("*.html")]
        if not pages:
            problems.append(f"no HTML pages under {site}")
        skip = {"404.html", "provenance/index.html", "provenance/master.html"}
        no_prov = [p.relative_to(site).as_posix() for p in pages
                   if p.relative_to(site).as_posix() not in skip
                   and 'class="prov"' not in p.read_text(encoding="utf-8", errors="ignore")]
        guide = site / "provenance" / "master.html"
        if not guide.exists():
            problems.append("no /provenance/master.html guide in the rendered site")
        else:
            home = site / "index.html"
            index = home.read_text(encoding="utf-8", errors="ignore") if home.exists() else ""
            if "provenance/master.html" not in index:
                problems.append("the guide is not linked from the site header")
            gtext = guide.read_text(encoding="utf-8", errors="ignore")
            for must in ("provenance-showcase.mp4", "provenance-timelapse.mp4",
                         "provenance-manual-run.mp4"):
                if must not in gtext:
                    problems.append(f"the guide does not mention {must}")
        cue_sheet = site / "provenance" / "index.html"
        if not cue_sheet.exists():
            problems.append("no /provenance/ cue sheet in the rendered site")
        else:
            sheet = cue_sheet.read_text(encoding="utf-8", errors="ignore")
            missing = [d["id"] for d in data if f'data-datum="{d["id"]}"' not in sheet]
            if missing:
                problems.append(f"{len(missing)} datums not in the cue sheet: {missing[:4]}")
            vids = re.findall(r"<video[^>]+src=\"([^\"#]+)", sheet)
            broken = [v for v in vids if not (cue_sheet.parent / v).resolve().exists()]
            if broken:
                problems.append(f"{len(broken)} cue videos missing on disk: {broken[:3]}")
        if no_prov:
            problems.append(f"{len(no_prov)} pages without a provenance block: {no_prov[:4]}")

    print(f"ledger: {len(data):,} datums · {totals.get('with_link', 0):,} linked · "
          f"{totals.get('with_cue', 0):,} cued")
    if a.site:
        print(f"site:   {a.site} · {len(list(Path(a.site).rglob('*.html')))} pages checked")
    if problems:
        for p in problems:
            print(f"  FAIL {p}", file=sys.stderr)
        return 1
    print("  ok — every datum carries an origin link, a click-path and a film cue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
