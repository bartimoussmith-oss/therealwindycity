#!/usr/bin/env python3
"""sync_yt_corpus.py — mirror the verbatim YouTube transcript archive.

Upstream: therealwindycity/The-Real-Windy-City- (public repo, no auth needed)
  cheyenne-2026-transcripts/meetings.json  = catalog (date, body, video id, file)
  cheyenne-2026-transcripts/<body>/*.md    = one verbatim transcript per meeting

This script downloads every cataloged transcript, converts it to the plain-text
corpus convention used under pipeline/corpus/, and writes it to
pipeline/corpus_yt/{date}-{body}.txt + a _manifest.json. Files whose content
did not change are left untouched so scheduled runs stay quiet.

Why a second corpus: pipeline/corpus/*.txt holds Granicus *minutes*
(~3k words/meeting, council only). The YouTube archive holds *verbatim*
transcripts (20k-70k words/meeting: council, committees, work sessions,
boards). engine/corpus_search.load_corpus() reads both directories and tags
each document with its source ("minutes" vs "verbatim-yt").

Stdlib only. Override the upstream base for testing:
  YT_CORPUS_BASE=https://raw.githubusercontent.com/<fork>/.../cheyenne-2026-transcripts

Exit codes: 1 when the catalog is unreachable or nothing synced (fail the
cycle loudly); 0 otherwise — individual file failures are logged as FAIL
lines but never block the rest of the civic cycle.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UPSTREAM_BASE = os.environ.get(
    "YT_CORPUS_BASE",
    "https://raw.githubusercontent.com/therealwindycity/"
    "The-Real-Windy-City-/main/cheyenne-2026-transcripts",
).rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "pipeline" / "corpus_yt"
MANIFEST = OUT_DIR / "_manifest.json"
UA = {"User-Agent": "therealwindycity-civic-cycle/1.0 (+corpus-yt-sync)"}
POLITENESS = 0.15  # seconds between file fetches
TIMEOUT = 30


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def md_to_txt(entry: dict, md: str) -> str:
    """Convert one upstream .md transcript to corpus .txt convention."""
    if "\n---\n" in md:
        md = md.split("\n---\n", 1)[1]
    body_lines = [ln for ln in md.splitlines() if ln.strip()]
    head = (f"MEETING: {entry.get('body', '')} | DATE: {entry.get('date', '')} "
            f"| YT_ID: {entry.get('youtube_id', '')}")
    src = ("SOURCE: verbatim YouTube captions via "
           "therealwindycity/The-Real-Windy-City- (cheyenne-2026-transcripts)")
    vid = f"VIDEO: https://www.youtube.com/watch?v={entry.get('youtube_id', '')}"
    extra = ""
    if entry.get("topic"):
        extra += f"\nTOPIC: {entry['topic']}"
    if entry.get("note"):
        extra += f"\nNOTE: {entry['note']}"
    return f"{head}\n{src}\n{vid}{extra}\n\n" + "\n".join(body_lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        catalog = json.loads(fetch_text(f"{UPSTREAM_BASE}/meetings.json"))
    except Exception as exc:  # noqa: BLE001 - fail the workflow step loudly
        print(f"SYNC-ERROR: cannot fetch upstream catalog: {exc}")
        return 1
    entries = [e for e in catalog if e.get("file")]
    print(f"upstream catalog: {len(entries)} transcript(s)")

    try:
        old_manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        old_files = old_manifest.get("upstream", {})
    except (OSError, ValueError):
        old_files = {}

    new_files: dict[str, str] = {}
    words = failures = wrote = 0
    for e in entries:
        name = Path(e["file"]).stem + ".txt"
        url = f"{UPSTREAM_BASE}/{e['file']}"
        try:
            txt = md_to_txt(e, fetch_text(url))
        except Exception as exc:  # noqa: BLE001 - record and continue
            print(f"  FAIL {name}: {exc}")
            failures += 1
            continue
        digest = hashlib.sha256(txt.encode("utf-8")).hexdigest()
        new_files[name] = digest
        words += len(txt.split())
        dest = OUT_DIR / name
        if old_files.get(name) == digest and dest.exists():
            pass  # unchanged
        else:
            dest.write_text(txt, encoding="utf-8")
            wrote += 1
        time.sleep(POLITENESS)

    MANIFEST.write_text(json.dumps({
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "upstream_base": UPSTREAM_BASE,
        "files": len(new_files),
        "words": words,
        "upstream": new_files,
    }, indent=1), encoding="utf-8")
    print(f"SYNC corpus_yt: {len(new_files)} file(s), {words} words, "
          f"{wrote} written, {failures} failed")
    if not new_files:
        print("SYNC-ERROR: nothing synced")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
