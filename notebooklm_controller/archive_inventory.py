#!/usr/bin/env python3
"""
archive_inventory.py — Unified inventory of the FULL Cheyenne meeting archive.

Builds one queue entry per meeting, oldest -> newest, from three sources:

  1. pipeline/meetings.json          — 479 meetings, 2008-05-27 -> 2026-08-24,
     with clip_id, date, name, agenda_url, minutes_url, mp4_url, player_url.
  2. pipeline/corpus_yt/*.txt        — 85 verbatim YouTube transcripts (2026 ONLY),
     matched to meetings by date + body to attach YouTube video IDs.
  3. pipeline/notebooklm/cheyenne_minutes_YYYY.md
     — yearly minutes aggregates; split per-meeting on the
     ``MEETING: ... | DATE: ... | CLIP_ID:`` header to attach minutes text.

IMPORTANT DESIGN RULE — minutes and verbatim transcripts are NEVER substituted
for one another:

  * ``transcript_text`` / ``transcript_path`` = ONLY verbatim YouTube captions
    (available for 2026 meetings only via corpus_yt). Null for 2008-2025.
  * ``minutes_text`` / ``minutes_path`` = Granicus minutes text (2008-2026),
    always kept separate from transcript text.
  * ``has_verbatim_transcript`` = boolean flag so downstream code never
    pretends minutes are verbatim.
  * ``source_availability`` = list like ["minutes"] or ["verbatim_transcript"]
    or ["verbatim_transcript", "minutes"] so the notebook spec and artifacts
    can label each source honestly.

Queue entry example (2026 meeting with both sources):
  {
    "clip_id": "1126",
    "date": "2026-08-24",
    "body": "city-council",
    "title": "City Council Meeting — 2026-08-24",
    "youtube_id": "HX3_qn0rw_Q",
    "youtube_url": "https://www.youtube.com/watch?v=HX3_qn0rw_Q",
    "transcript_text": "...verbatim captions...",
    "transcript_path": "pipeline/corpus_yt/2026-08-24-city-council.txt",
    "transcript_source": "corpus_yt",
    "has_verbatim_transcript": true,
    "minutes_text": "...summarized minutes...",
    "minutes_path": "pipeline/notebooklm/cheyenne_minutes_2026.md",
    "minutes_source": "granicus_minutes",
    "source_availability": ["verbatim_transcript", "minutes"],
    "agenda_url": "...",
    "minutes_url": "...",
    "mp4_url": "...",
    "player_url": "...",
    "supporting_docs": [...],
  }

Queue entry example (2008 meeting, minutes only — NO verbatim transcript):
  {
    "clip_id": "24",
    "date": "2008-05-27",
    "body": "city-council",
    "title": "Cheyenne City Council — 2008-05-27",
    "youtube_id": null,
    "youtube_url": null,
    "transcript_text": null,
    "transcript_path": null,
    "transcript_source": null,
    "has_verbatim_transcript": false,
    "minutes_text": "...summarized minutes...",
    "minutes_path": "pipeline/notebooklm/cheyenne_minutes_2008.md",
    "minutes_source": "granicus_minutes",
    "source_availability": ["minutes"],
    "agenda_url": "...",
    ...
  }

Sorted strictly oldest -> newest by date. Same-day committees kept as separate
entries (keyed by date|body).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
MEETINGS_JSON = ROOT / "pipeline" / "meetings.json"
CORPUS_YT = ROOT / "pipeline" / "corpus_yt"
MINUTES_DIR = ROOT / "pipeline" / "notebooklm"
GRANICUS_CATALOG = ROOT / "youtube-archive" / "catalog_granicus.json"

MEETING_HEADER_RE = re.compile(
    r"^MEETING:\s*(?P<body>.+?)\s*\|\s*DATE:\s*(?P<date>\d{4}-\d{2}-\d{2})\s*"
    r"\|\s*CLIP_ID:\s*(?P<clip_id>\S+)",
)


def _log(msg: str) -> None:
    print(f"[inventory] {msg}")


def _body_slug(name: str) -> str:
    n = name.lower().strip()
    n = n.replace("city council meeting", "city-council")
    n = n.replace("committee of the whole", "committee-of-the-whole")
    n = n.replace("public services", "public-services")
    n = n.replace("finance committee", "finance-committee")
    n = n.replace("planning commission", "planning-commission")
    n = n.replace("board of adjustment", "board-of-adjustment")
    n = n.replace("historic preservation", "historic-preservation")
    n = n.replace("urban renewal", "urban-renewal")
    n = n.replace("goal setting", "goal-setting")
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    return n or "meeting"


def _load_granicus_by_date() -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = {}
    if not GRANICUS_CATALOG.exists():
        return by_date
    try:
        catalog = json.loads(GRANICUS_CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log(f"could not read granicus catalog: {exc}")
        return by_date
    for entry in catalog:
        by_date.setdefault(entry.get("date_iso", ""), []).append(entry)
    return by_date


def _build_corpus_index() -> dict[str, dict]:
    """Index corpus_yt files by 'date-body' for matching.

    These are VERBATIM YouTube transcripts only (2026). Never minutes.
    """
    index: dict[str, dict] = {}
    if not CORPUS_YT.exists():
        return index
    for path in CORPUS_YT.glob("*.txt"):
        if path.name == "_manifest.json":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        mdate = mbody = yt_id = video = None
        for line in text.splitlines()[:14]:
            if line.startswith("VIDEO:"):
                video = line.split(":", 1)[1].strip()
            for part in line.split("|"):
                part = part.strip()
                if part.startswith("MEETING:"):
                    mbody = part.split(":", 1)[1].strip()
                elif part.startswith("DATE:"):
                    mdate = part.split(":", 1)[1].strip()
                elif part.startswith("YT_ID:"):
                    yt_id = part.split(":", 1)[1].strip()
        if mdate and mbody and yt_id:
            slug = _body_slug(mbody)
            index[f"{mdate}-{slug}"] = {
                "transcript_path": str(path),
                "youtube_id": yt_id,
                "youtube_url": video,
                "transcript_source": "corpus_yt",
                "raw_meeting": mbody,
            }
    return index


def _split_minutes_by_meeting(minutes_dir: Path) -> dict[str, dict]:
    """Split yearly minutes .md files into {clip_id: minutes_chunk}.

    Returns SUMMARIZED minutes text only — NEVER verbatim transcripts.
    Each chunk includes the MEETING header so provenance is preserved.
    """
    out: dict[str, dict] = {}
    if not minutes_dir.exists():
        return out
    for path in sorted(minutes_dir.glob("cheyenne_minutes_*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts = re.split(r"(?=^MEETING:)", text, flags=re.MULTILINE)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            first_line = part.splitlines()[0] if part.splitlines() else ""
            m = MEETING_HEADER_RE.match(first_line)
            if not m:
                continue
            clip_id = m.group("clip_id")
            date = m.group("date")
            body = m.group("body")
            out[clip_id] = {
                "minutes_text": part,
                "minutes_path": str(path),
                "date": date,
                "body": body.strip(),
                "minutes_source": "granicus_minutes",
            }
    return out


def build_queue(live: bool = False) -> list[dict]:
    """Unified queue, oldest -> newest. `live` reserved for YouTube-live mode.

    Minutes and verbatim transcripts are kept in SEPARATE fields. Neither is
    ever substituted for the other.
    """
    corpus_index = _build_corpus_index()
    minutes_index = _split_minutes_by_meeting(MINUTES_DIR)
    granicus_by_date = _load_granicus_by_date()

    try:
        meetings = json.loads(MEETINGS_JSON.read_text(encoding="utf-8"))["meetings"]
    except (OSError, ValueError, KeyError) as exc:
        _log(f"could not read meetings.json: {exc}")
        return []

    _log(f"meetings.json entries: {len(meetings)}")

    entries: dict[str, dict] = {}
    for clip_id, m in meetings.items():
        date = m.get("date", "")
        name = m.get("name", "Cheyenne City Council")
        body = _body_slug(name)
        key = f"{date}|{body}"

        yt_match = corpus_index.get(f"{date}-{body}")
        minutes_chunk = minutes_index.get(clip_id)

        # --- VERBATIM TRANSCRIPT (2026 only, from corpus_yt) ---
        transcript_text = None
        transcript_path = None
        transcript_source = None
        youtube_id = None
        youtube_url = None
        has_verbatim_transcript = False
        if yt_match:
            has_verbatim_transcript = True
            transcript_path = yt_match["transcript_path"]
            try:
                transcript_text = Path(transcript_path).read_text(
                    encoding="utf-8", errors="replace")
            except OSError:
                transcript_text = None
            transcript_source = yt_match["transcript_source"]
            youtube_id = yt_match["youtube_id"]
            youtube_url = yt_match["youtube_url"]

        # --- MINUTES (2008-2026, from yearly files) — SEPARATE FROM TRANSCRIPT ---
        minutes_text = None
        minutes_path = None
        minutes_source = None
        if minutes_chunk:
            minutes_text = minutes_chunk["minutes_text"]
            minutes_path = minutes_chunk.get("minutes_path")
            minutes_source = minutes_chunk.get("minutes_source")

        source_availability: list[str] = []
        if has_verbatim_transcript:
            source_availability.append("verbatim_transcript")
        if minutes_text:
            source_availability.append("minutes")
        if not source_availability:
            source_availability.append("none")

        supporting = []
        for g in granicus_by_date.get(date, []):
            gname = (g.get("name") or "").lower()
            if body.replace("-", " ") in gname or gname in name.lower() or not name:
                supporting.append({
                    "type": "granicus_catalog",
                    "clip_id": g.get("clip_id"),
                    "name": g.get("name"),
                    "date_display": g.get("date_display"),
                    "duration": g.get("duration"),
                    "agenda_url": g.get("agenda_url"),
                    "minutes_url": g.get("minutes_url"),
                    "mp4_url": g.get("mp4_url"),
                    "player_url": g.get("player_url"),
                    "note": "Local mirror of cheyenne.granicus.com catalog; live "
                            "fetch attempted by the controller when network allows.",
                })
        # dedupe
        seen, uniq = set(), []
        for d in supporting:
            k = (d["agenda_url"], d["minutes_url"])
            if k in seen:
                continue
            seen.add(k)
            uniq.append(d)

        entries[key] = {
            "clip_id": clip_id,
            "date": date,
            "body": body,
            "title": f"{name} — {date}",
            "youtube_id": youtube_id,
            "youtube_url": youtube_url,
            "transcript_text": transcript_text,
            "transcript_path": transcript_path,
            "transcript_source": transcript_source,
            "has_verbatim_transcript": has_verbatim_transcript,
            "minutes_text": minutes_text,
            "minutes_path": minutes_path,
            "minutes_source": minutes_source,
            "source_availability": source_availability,
            "agenda_url": m.get("agenda_url"),
            "minutes_url": m.get("minutes_url"),
            "mp4_url": m.get("mp4_url"),
            "player_url": m.get("player_url"),
            "supporting_docs": uniq,
        }

    # Backfill: corpus_yt meetings not in meetings.json (shouldn't happen, but safe)
    for key, yt in corpus_index.items():
        date = key.split("-", 1)[0]
        body = key.split("-", 1)[1]
        k = f"{date}|{body}"
        if k not in entries:
            try:
                yt_text = Path(yt["transcript_path"]).read_text(
                    encoding="utf-8", errors="replace")
            except OSError:
                yt_text = None
            entries[k] = {
                "clip_id": f"yt-{key}",
                "date": date,
                "body": body,
                "title": f"YouTube transcript — {date}",
                "youtube_id": yt["youtube_id"],
                "youtube_url": yt["youtube_url"],
                "transcript_text": yt_text,
                "transcript_path": yt["transcript_path"],
                "transcript_source": "corpus_yt",
                "has_verbatim_transcript": True,
                "minutes_text": None,
                "minutes_path": None,
                "minutes_source": None,
                "source_availability": ["verbatim_transcript"],
                "agenda_url": None,
                "minutes_url": None,
                "mp4_url": None,
                "player_url": None,
                "supporting_docs": [],
            }

    queue = sorted(entries.values(), key=lambda e: (e["date"], e["body"], e["clip_id"]))
    n_verbatim = sum(1 for e in queue if e["has_verbatim_transcript"])
    n_minutes_only = sum(1 for e in queue if not e["has_verbatim_transcript"] and e["minutes_text"])
    _log(f"unified queue entries: {len(queue)}  {queue[0]['date']} -> {queue[-1]['date']}" if queue else "queue empty")
    _log(f"with verbatim transcript: {n_verbatim}  minutes-only: {n_minutes_only}")
    return queue
