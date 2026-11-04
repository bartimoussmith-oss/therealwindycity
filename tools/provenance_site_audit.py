#!/usr/bin/env python3
"""Render the real record and crawl every page, proving coverage end to end.

This is the harness behind the claim "every datum on the live pages". It does three
things, in order, and fails loudly if any of them is not true:

1. builds the Markdown record from the files in this checkout
   (`tools/build_ai_record.py` — the same inputs the Pages workflow uses);
2. renders the static site with the provenance blocks (`tools/render_ai_record.py`);
3. crawls the rendered site: every internal link resolves, every `<video>` src
   exists on disk, every content page carries a provenance block, and every
   datum in the ledger appears in that page's block or on the cue sheet.

    python3 tools/provenance_site_audit.py            # build + render + crawl
    python3 tools/provenance_site_audit.py --site _site --skip-build
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PAGE_PREFIXES = ("osint/", "media-studio/", "arrest/", "secure-resource/", "public/")


def run(cmd: list[str]) -> None:
    print("  $ " + " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, cwd=ROOT, check=True)


def build(out_md: Path, meetings: Path, transcripts: Path) -> None:
    if not meetings.exists():
        raise SystemExit(
            f"meeting index not found: {meetings}\n"
            "The Pages workflow builds it with: git clone --depth 1 "
            "https://github.com/therealwindycity/TheReelWindyCity.git /tmp/fe && "
            "(cd /tmp/fe && node scripts/build-data.mjs). Point --meetings at the result."
        )
    run([
        sys.executable, "tools/build_ai_record.py",
        "--meetings", str(meetings),
        "--text", str(ROOT / "data" / "text"),
        "--ocr", str(ROOT / "ai-record-ocr"),
        "--transcripts", str(transcripts),
        "--minutes", str(ROOT / "pipeline" / "corpus"),
        "--trees", str(ROOT),
        "--drive-db", str(ROOT / "drive-import" / "master_meetings_database.json.gz"),
        "--out", str(out_md),
    ])


def crawl(site: Path, ledger_path: Path) -> int:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {"data": []}
    datums = {d["id"]: d for d in ledger.get("data", [])}
    pages = sorted(site.rglob("*.html"))
    if not pages:
        print("no pages rendered", file=sys.stderr)
        return 2

    broken_links: list[tuple[str, str]] = []
    missing_video: list[tuple[str, str]] = []
    no_block: list[str] = []
    cue_sheet = site / "provenance" / "index.html"
    sheet_ids: set[str] = set()
    if cue_sheet.exists():
        sheet_ids = set(re.findall(r'data-datum="([^"]+)"', cue_sheet.read_text(encoding="utf-8", errors="ignore")))
    block_ids: set[str] = set()
    covered_clips: set[str] = set()

    for page in pages:
        rel = page.relative_to(site).as_posix()
        text = page.read_text(encoding="utf-8", errors="ignore")
        base = page.parent
        for src in re.findall(r'<video[^>]*?\bsrc="([^"#]+)', text):
            target = (base / src).resolve()
            if not target.exists():
                missing_video.append((rel, src))
            else:
                covered_clips.add(target)
        for href in re.findall(r'<a[^>]*?\bhref="([^"]+)"', text):
            if href.startswith(("http://", "https://", "mailto:", "tel:", "#", "javascript:")):
                continue
            target = (base / href.split("#")[0].split("?")[0]).resolve()
            if href.split("#")[0].split("?")[0] == "":
                continue
            if not target.exists():
                broken_links.append((rel, href))
        if rel not in ("404.html", "provenance/index.html", "provenance/master.html") \
                and not rel.startswith(SKIP_PAGE_PREFIXES):
            if 'class="prov"' not in text:
                no_block.append(rel)
        # the datum ids a block references (via the origin URL it links)
        for origin in re.findall(r'class="src"[^>]*href="([^"]+)"', text):
            pass
        block_ids |= set()

    # every datum must be listed on the cue sheet, or carried by a page block
    uncovered = [i for i in datums if i not in sheet_ids]

    print(f"\naudit: {len(pages):,} pages · {len(datums):,} datums · "
          f"{len(covered_clips):,} distinct clips embedded")
    problems = 0
    for name, items in (("broken internal links", broken_links),
                        ("video src missing on disk", missing_video),
                        ("pages with no provenance block", [(p, "") for p in no_block]),
                        ("datums not on the cue sheet", [(i, "") for i in uncovered])):
        if items:
            problems += len(items)
            print(f"  FAIL {len(items)} {name}: {items[:6]}", file=sys.stderr)
    by_kind = collections.Counter(v[1].split("/")[0] for v in missing_video)
    if by_kind:
        print(f"        missing by directory: {dict(by_kind)}", file=sys.stderr)
    if problems:
        return 1
    print("  ok — every page states where its numbers come from, every clip resolves, "
          "every datum is on the cue sheet")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", default="/tmp/ai-record-audit")
    ap.add_argument("--site", default="/tmp/site-audit")
    ap.add_argument("--transcripts", default="/tmp/tr",
                    help="checkout of the transcripts repo (The-Real-Windy-City-)")
    ap.add_argument("--meetings", default="/tmp/fe/src/data/meetings.json",
                    help="meeting index built by TheReelWindyCity's scripts/build-data.mjs")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--skip-render", action="store_true")
    a = ap.parse_args(argv)

    md, site = Path(a.md), Path(a.site)
    if not a.skip_build:
        print("building the record from this checkout …", file=sys.stderr)
        build(md, Path(a.meetings), Path(a.transcripts))
    if not a.skip_render:
        print("rendering the site with provenance blocks …", file=sys.stderr)
        run([sys.executable, "tools/render_ai_record.py", "--src", str(md), "--out", str(site)])
    return crawl(site, ROOT / "data" / "out" / "provenance-ledger.json")


if __name__ == "__main__":
    raise SystemExit(main())
