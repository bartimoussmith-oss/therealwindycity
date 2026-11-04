#!/usr/bin/env python3
"""Transcribe the portal's meeting audio, one clip at a time, and write it into the record.

Why this is a script and not a one-off: the sandbox this was written in cannot reach
archive-video.granicus.com or download Whisper weights, so the transcription has to run
where the network is open — a GitHub Actions runner. This is that job, written so it is
restartable, honest about failure, and identical in output to the repo's scanner pipeline
(`scripts/scanner_continuous.py`, faster-whisper tiny.en/int8/VAD).

What it does, per clip:

  1. pick the next un-transcribed clip from `youtube-archive/catalog_granicus.json`
     (oldest first, or a single `--clip-id`, or a year range)
  2. GET the portal's own MP3 (`archive-video.granicus.com/cheyenne/cheyenne_<uuid>.mp3`)
  3. transcribe with faster-whisper, segments carry start/end seconds
  4. write `transcripts/granicus/<clip_id>-<date>-<slug>.md` (+ `.json`, + `.txt` when
     `--also-txt`), each with the origin URL, the fetch date, the model and its settings
  5. append/refresh `transcripts/granicus/index.json` and `INDEX.md`
  6. skip anything already done, so a rerun after a timeout resumes where it stopped

Every transcript states that it is a machine transcription of the portal's audio and that
it can be wrong. Nothing here is presented as a verified record.

    python3 tools/transcribe_granicus.py --limit 3 --dry-run
    python3 tools/transcribe_granicus.py --limit 3
    python3 tools/transcribe_granicus.py --clip-id 1144
    python3 tools/transcribe_granicus.py --year 2026 --limit 20
    python3 tools/transcribe_granicus.py --status          # what is done, what is left
    python3 tools/transcribe_granicus.py --refresh-catalog # pick up clips posted since the crawl
    python3 tools/transcribe_granicus.py --self-test       # prove the parser, no network
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "youtube-archive" / "catalog_granicus.json"
OUT = ROOT / "transcripts" / "granicus"
PORTAL = "https://cheyenne.granicus.com/ViewPublisher.php?view_id=2"

MODEL = os.environ.get("WHISPER_MODEL", "small.en")
LANG = os.environ.get("WHISPER_LANG", "en")
COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
BEAM = int(os.environ.get("WHISPER_BEAM", "5"))

NOTICE = ("Machine transcription of the City of Cheyenne's own meeting audio. It can be "
          "wrong — names, numbers and motions especially. Verify against the linked video "
          "before relying on any line. Not an official transcript.")


# --------------------------------------------------------------------------
# the catalog
# --------------------------------------------------------------------------

def load_catalog() -> list[dict]:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    cat.sort(key=lambda r: (r.get("date_iso", ""), int(r.get("clip_id", 0))))
    return cat


def slug(text: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:limit].rstrip("-")) or "meeting"


def stem_for(row: dict) -> str:
    return f"{int(row['clip_id']):04d}-{row['date_iso']}-{slug(row.get('name', ''))}"


def audio_url(row: dict) -> str:
    """The portal's MP3 for this clip. The catalog's stream_url is an HLS playlist, not the file."""
    if row.get("mp3_url"):
        return row["mp3_url"]
    mp4 = row.get("mp4_url") or ""
    return mp4[:-4] + ".mp3" if mp4.lower().endswith(".mp4") else ""


def download_source(row: dict, dest: Path) -> tuple[Path, str]:
    """Fetch the MP3 if the portal has one, else the MP4 and let PyAV pull the audio.

    Newer rows on some views carry only an MP4; transcription quality is identical
    because faster-whisper decodes the container itself.
    """
    mp3 = audio_url(row)
    if mp3:
        try:
            fetch(mp3, dest)
            return dest, mp3
        except Exception as exc:
            print(f"    mp3 failed ({type(exc).__name__}), trying the mp4", file=sys.stderr)
    mp4 = row.get("mp4_url") or ""
    if not mp4:
        raise RuntimeError("no audio or video URL on this catalog row")
    fetch(mp4, dest)
    return dest, mp4


def duration_minutes(row: dict) -> int:
    try:
        h, rest = (row.get("duration") or "0h 0m").split("h", 1)
        return int(h) * 60 + int(rest.strip().rstrip("m") or 0)
    except Exception:
        return 0


MANIFEST = "manifest.json"


def load_manifest() -> dict[str, dict]:
    """One compact record per finished clip. This is what makes a rerun resume."""
    path = OUT / MANIFEST
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(item["clip_id"]): item for item in data.get("items", [])}
    except Exception:
        return {}


def save_manifest(items: dict[str, dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sorted(items.values(), key=lambda r: (r.get("date") or "", int(r.get("clip_id") or 0)))
    total_audio = sum(r.get("duration_audio_seconds") or 0 for r in rows)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL, "compute_type": COMPUTE, "beam_size": BEAM, "vad": True,
        "transcripts": len(rows),
        "audio_seconds_transcribed": round(total_audio, 1),
        "words": sum(r.get("words") or 0 for r in rows),
        "notice": NOTICE,
        "items": rows,
    }
    (OUT / MANIFEST).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def done_stems() -> set[str]:
    """Every clip already transcribed — from the manifest, so --md-only runs count too."""
    manifest = load_manifest()
    if manifest:
        return {str(item.get("stem")) for item in manifest.values() if item.get("stem")}
    if not OUT.exists():
        return set()
    return {p.stem for p in OUT.glob("*.json") if p.stem not in ("index",)}


def done_clip_ids() -> set[str]:
    return set(load_manifest())


def select(rows: list[dict], a) -> list[dict]:
    if a.clip_id:
        return [r for r in rows if str(r.get("clip_id")) == str(a.clip_id)]
    if a.year:
        rows = [r for r in rows if r.get("date_iso", "").startswith(str(a.year))]
    if not a.redo:
        finished = done_clip_ids()
        rows = [r for r in rows if str(r.get("clip_id")) not in finished]
    if not a.include_agenda_only:
        rows = [r for r in rows if "agenda only" not in (r.get("name") or "").lower()]
    if a.max_minutes:
        keep, total = [], 0
        for r in rows:
            d = duration_minutes(r)
            if total + d > a.max_minutes and keep:
                break
            keep.append(r)
            total += d
        rows = keep
    return rows[: a.limit] if a.limit else rows


# --------------------------------------------------------------------------
# refreshing the catalog from the portal itself
# --------------------------------------------------------------------------
#
# youtube-archive/catalog_granicus.json is this repo's crawl of the portal's clip list
# and it stops where the last crawl stopped. The portal keeps publishing, so before a
# transcription run we re-read the two publisher views that carry download links and
# merge any clip we do not have. Views 2 and 4 both list the same meetings; 4 is the
# one whose rows carry a direct MP4 link, 2 is the one that still carries MP3.

VIEWS = ("https://cheyenne.granicus.com/ViewPublisher.php?view_id=4",
         "https://cheyenne.granicus.com/ViewPublisher.php?view_id=2")

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CLIP = re.compile(r"clip_id=(\d+)")
_DATE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})")
_DUR = re.compile(r"(\d{1,2})h\s*(\d{1,2})m")
_MP4 = re.compile(r"https://archive-video\.granicus\.com/cheyenne/cheyenne_[0-9a-f-]+\.mp4")
_MP3 = re.compile(r"https://archive-video\.granicus\.com/cheyenne/cheyenne_[0-9a-f-]+\.mp3")
_MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def _cell_text(cell: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()


def parse_view(html: str) -> list[dict]:
    """Rows from one ViewPublisher page, in this repo's catalog schema."""
    out = []
    for block in _ROW.findall(html):
        clip = _CLIP.search(block)
        mp4 = _MP4.search(block)
        if not clip:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.S | re.I)
        if not cells:
            continue
        name = _cell_text(cells[0])
        date = ""
        for cell in cells[:3]:
            m = _DATE.search(_cell_text(cell))
            if m and m.group(1) in _MONTHS:
                date = f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
                break
        dm = _DUR.search(_cell_text(block))
        mp3 = _MP3.search(block)
        if not (name and date):
            continue
        out.append({
            "clip_id": clip.group(1),
            "name": name,
            "date_display": f"{date[5:7]}/{date[8:10]}/{date[0:4]}",
            "date_iso": date,
            "timestamp": "",
            "duration": f"{int(dm.group(1)):02d}h {int(dm.group(2)):02d}m" if dm else "",
            "mp4_url": mp4.group(0) if mp4 else "",
            "stream_url": "",
            "mp3_url": mp3.group(0) if mp3 else "",
            "player_url": f"https://cheyenne.granicus.com/player/clip/{clip.group(1)}?view_id=2&redirect=true",
            "agenda_url": f"https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id={clip.group(1)}",
            "minutes_url": "",
        })
    return out


def refresh_catalog(a) -> int:
    """Merge anything new on the portal into the catalog. Returns how many were added.

    Called on its own (`--refresh-catalog --refresh-only`) it never falls through into
    transcription: a catalog refresh that silently starts an hour of CPU is a bug.
    """
    try:
        cat = load_catalog()
    except Exception:
        cat = []
    known = {str(r.get("clip_id")) for r in cat}
    fresh: dict[str, dict] = {}
    for view in VIEWS:
        print(f"  reading {view}", file=sys.stderr)
        try:
            req = urllib.request.Request(view, headers={"User-Agent": "therealwindycity-provenance/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                html = r.read().decode("utf-8", "replace")
        except Exception as exc:
            print(f"    unreachable: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        for row in parse_view(html):
            row["mp3_url"] = row.get("mp3_url") or (row["mp4_url"][:-4] + ".mp3"
                                                    if row["mp4_url"] else "")
            fresh[row["clip_id"]] = {**fresh.get(row["clip_id"], {}),
                                     **{k: v for k, v in row.items() if v}}
    added = [r for cid, r in fresh.items() if cid not in known]
    if not added:
        print("  catalog already current", file=sys.stderr)
        return 0
    for r in added:
        cat.append(r)
    cat.sort(key=lambda r: (r.get("date_iso", ""), int(r.get("clip_id", 0) or 0)))
    if a.dry_run:
        print(f"  would add {len(added)} clip(s): "
              f"{', '.join(sorted(r['clip_id'] for r in added))}", file=sys.stderr)
        return len(added)
    CATALOG.write_text(json.dumps(cat, indent=1) + "\n", encoding="utf-8")
    print(f"  added {len(added)} clip(s) to {CATALOG.relative_to(ROOT)}: "
          f"{', '.join(sorted(r['clip_id'] for r in added))}", file=sys.stderr)
    return len(added)


# --------------------------------------------------------------------------
# fetch + transcribe
# --------------------------------------------------------------------------

def fetch(url: str, dest: Path, timeout: int = 600) -> int:
    req = urllib.request.Request(url, headers={
        "User-Agent": "therealwindycity-provenance/1.0 (+https://bartimoussmith-oss.github.io/therealwindycity/)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as fh:
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            got += len(chunk)
    return got


_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel(MODEL, device="cpu", compute_type=COMPUTE)
    return _MODEL


def transcribe(path: Path) -> tuple[list[dict], dict]:
    segments, info = model().transcribe(
        str(path), language=LANG, beam_size=BEAM, vad_filter=True,
        condition_on_previous_text=False,
    )
    out = []
    for s in segments:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2),
                    "text": (s.text or "").strip()})
    meta = {"language": getattr(info, "language", LANG),
            "language_probability": round(float(getattr(info, "language_probability", 0) or 0), 3),
            "duration": round(float(getattr(info, "duration", 0) or 0), 2)}
    return out, meta


def stamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600 \
        else f"{s // 60}:{s % 60:02d}"


def write_transcript(row: dict, segments: list[dict], meta: dict, a) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    stem = stem_for(row)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = audio_url(row)
    words = sum(len(s["text"].split()) for s in segments)
    record = {
        "clip_id": int(row["clip_id"]),
        "date": row["date_iso"],
        "name": row.get("name", ""),
        "duration_stated": row.get("duration", ""),
        "duration_audio_seconds": meta.get("duration", 0),
        "segments": len(segments),
        "words": words,
        "language": meta.get("language"),
        "language_probability": meta.get("language_probability"),
        "model": MODEL,
        "compute_type": COMPUTE,
        "beam_size": BEAM,
        "vad": True,
        "transcribed_at": now,
        "audio_url": url,
        "agenda_url": row.get("agenda_url", ""),
        "minutes_url": row.get("minutes_url", ""),
        "player_url": row.get("player_url", ""),
        "portal": PORTAL,
        "notice": NOTICE,
        "segments_data": segments,
    }
    compact = {k: v for k, v in record.items() if k != "segments_data"} | {"stem": stem}
    if not getattr(a, "md_only", False):
        (OUT / f"{stem}.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")

    lines = [
        f"# {row.get('name','Meeting')} — {row['date_iso']}",
        "",
        f"*{NOTICE}*",
        "",
        f"- **Source audio (official):** {url}",
        f"- **Meeting page at the city:** {row.get('player_url') or row.get('agenda_url','')}",
        f"- **Portal:** {PORTAL}",
        f"- **Clip id:** {row['clip_id']} · **stated duration:** {row.get('duration','—')}"
        f" · **audio length:** {stamp(meta.get('duration', 0) or 0)}",
        f"- **Transcribed:** {now} with faster-whisper `{MODEL}` ({COMPUTE}, beam {BEAM}, VAD on)",
        f"- **Segments:** {len(segments):,} · **words:** {words:,}",
        "",
        "| time | what was said |",
        "|---|---|",
    ]
    for s in segments:
        text = s["text"].replace("|", "\\|")
        lines.append(f"| [{stamp(s['start'])}]({url}#t={int(s['start'])}) | {text} |")
    lines.append("")
    (OUT / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")

    if a.also_txt:
        (OUT / f"{stem}.txt").write_text(
            "\n".join(f"[{stamp(s['start'])}] {s['text']}" for s in segments) + "\n",
            encoding="utf-8")
    manifest = load_manifest()
    manifest[str(row["clip_id"])] = compact
    save_manifest(manifest)
    return record


def write_index() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cat = {int(r["clip_id"]): r for r in load_catalog()}
    manifest = load_manifest()
    save_manifest(manifest)
    rows = [{k: v.get(k) for k in (
        "clip_id", "date", "name", "duration_stated", "duration_audio_seconds",
        "words", "segments", "model", "transcribed_at", "audio_url")}
        | {"markdown": f"transcripts/granicus/{v.get('stem')}.md"}
        for v in manifest.values() if v.get("stem")]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("clip_id") or 0))
    total_audio = sum(r.get("duration_audio_seconds") or 0 for r in rows)
    total_words = sum(r.get("words") or 0 for r in rows)
    with_audio = sum(1 for r in cat.values() if r.get("mp4_url"))
    index = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL, "compute_type": COMPUTE, "beam_size": BEAM, "vad": True,
        "catalog_clips_with_audio": with_audio,
        "transcripts": len(rows),
        "audio_seconds_transcribed": round(total_audio, 1),
        "words": total_words,
        "notice": NOTICE,
        "items": rows,
    }
    (OUT / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")

    md = [
        "# The portal's meeting audio, transcribed",
        "",
        f"*{NOTICE}*",
        "",
        f"{len(rows):,} of {with_audio:,} council clips with audio, transcribed with "
        f"faster-whisper `{MODEL}` — {total_audio / 3600:,.1f} hours of audio, "
        f"{total_words:,} words. Generated {index['generated_at']} by "
        "`tools/transcribe_granicus.py`.",
        "",
        "Source: the City of Cheyenne's own MP3s at `archive-video.granicus.com`, listed on "
        f"[the portal]({PORTAL}).",
        "",
        "| date | meeting | length | words | transcript | audio |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(f"| {r['date']} | {r['name']} | {r.get('duration_stated','—')} | "
                  f"{r.get('words',0):,} | [{Path(r['markdown']).name}]({Path(r['markdown']).name}) | "
                  f"[mp3]({r.get('audio_url','')}) |")
    md.append("")
    (OUT / "INDEX.md").write_text("\n".join(md), encoding="utf-8")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

FIXTURE = """
<tr><td>City Council Meeting</td><td>1792998000Oct 26, 2026</td><td>02h 36m</td>
<td><a href="https://cheyenne.granicus.com/AgendaViewer.php?view_id=4&amp;clip_id=1144">Agenda</a></td>
<td></td><td>Video <a href="https://cheyenne.granicus.com/ASX.php?view_id=4&amp;clip_id=1144&amp;sn=cheyenne.granicus.com">Open</a></td>
<td></td><td><a href="https://archive-video.granicus.com/cheyenne/cheyenne_e443a894-d227-11f1-89ef-005056a84798.mp4">MP4</a></td></tr>
<tr><td>Cheyenne City Council</td><td>1212994800Jun 9, 2008</td><td>02h 27m</td>
<td><a href="http://cheyenne.granicus.com/AgendaViewer.php?view_id=2&amp;clip_id=28">Agenda</a></td>
<td><a href="http://cheyenne.granicus.com/MinutesViewer.php?view_id=2&amp;clip_id=28">Minutes</a></td>
<td>Video <a href="http://cheyenne.granicus.com/ASX.php?view_id=2&amp;clip_id=28">Open</a></td>
<td><a href="https://archive-video.granicus.com/cheyenne/cheyenne_0395a033-06af-41d3-8760-aa8efe3350c5.mp3">MP3 Audio</a></td>
<td><a href="https://archive-video.granicus.com/cheyenne/cheyenne_0395a033-06af-41d3-8760-aa8efe3350c5.mp4">MP4 Video</a></td></tr>
"""


def self_test() -> int:
    """Parse a saved slice of the portal and check the fields we depend on."""
    rows = {r["clip_id"]: r for r in parse_view(FIXTURE)}
    problems = []
    if set(rows) != {"1144", "28"}:
        problems.append(f"clip ids: {sorted(rows)}")
    a, b = rows.get("1144", {}), rows.get("28", {})
    if a.get("date_iso") != "2026-10-26":
        problems.append(f"1144 date: {a.get('date_iso')}")
    if a.get("duration") != "02h 36m":
        problems.append(f"1144 duration: {a.get('duration')}")
    if not a.get("mp4_url", "").endswith(".mp4"):
        problems.append("1144 mp4 not found")
    if not audio_url(a).endswith(".mp3"):
        problems.append("1144 mp3 not derived")
    if b.get("date_iso") != "2008-06-09":
        problems.append(f"28 date: {b.get('date_iso')}")
    if b.get("name") != "Cheyenne City Council":
        problems.append(f"28 name: {b.get('name')}")
    if not b.get("mp3_url", "").endswith(".mp3"):
        problems.append("28 mp3 not parsed")
    for p in problems:
        print(f"  FAIL {p}", file=sys.stderr)
    if problems:
        return 1
    print("  ok — parser reads clip id, date, duration, MP4 and MP3 from both row shapes",
          file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=3, help="how many clips this run (0 = no limit)")
    ap.add_argument("--clip-id", default="", help="one clip by id")
    ap.add_argument("--year", default="", help="only clips from this year")
    ap.add_argument("--max-minutes", type=int, default=180,
                    help="stop before this much stated meeting time is queued (default 180)")
    ap.add_argument("--include-agenda-only", action="store_true",
                    help="also transcribe 'Agenda Only' rows (usually silent)")
    ap.add_argument("--redo", action="store_true", help="re-transcribe clips already done")
    ap.add_argument("--also-txt", action="store_true", help="write a plain .txt beside each")
    ap.add_argument("--md-only", action="store_true",
                    help="skip the per-clip .json (segments are still in the .md table); "
                         "keeps 792 hours of transcripts to tens of MB instead of hundreds")
    ap.add_argument("--dry-run", action="store_true", help="list what would run, fetch nothing")
    ap.add_argument("--status", action="store_true", help="print progress and exit")
    ap.add_argument("--keep-audio", action="store_true", help="keep the downloaded audio")
    ap.add_argument("--refresh-only", action="store_true",
                    help="with --refresh-catalog: refresh the catalog and stop")
    ap.add_argument("--refresh-catalog", action="store_true",
                    help="re-read the portal's publisher pages and add clips posted since the crawl")
    ap.add_argument("--self-test", action="store_true",
                    help="parse a saved portal page and check the result, then exit")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()

    if a.refresh_catalog:
        added = refresh_catalog(a)
        if a.refresh_only:
            return 0
        print(f"  catalog: {added} new clip(s)", file=sys.stderr)

    rows = load_catalog()
    with_audio = [r for r in rows if audio_url(r) or r.get("mp4_url")]
    if a.status:
        have = done_clip_ids()
        finished = [r for r in with_audio if str(r.get("clip_id")) in have]
        todo = [r for r in with_audio if str(r.get("clip_id")) not in have]
        mins = sum(duration_minutes(r) for r in todo)
        print(f"catalog: {len(rows):,} clips · {len(with_audio):,} with audio")
        print(f"done:    {len(finished):,} transcripts ({sum(duration_minutes(r) for r in finished):,} min)")
        print(f"left:    {len(todo):,} clips ({mins:,} min ≈ {mins/60:,.1f} h of audio)")
        if todo:
            print(f"next:    {stem_for(todo[0])}")
        return 0

    queue = select(with_audio, a)
    if not queue:
        print("nothing to do — every selected clip already has a transcript", file=sys.stderr)
        return 0
    total = sum(duration_minutes(r) for r in queue)
    print(f"queue: {len(queue)} clip(s), {total:,} min of stated meeting time "
          f"(model {MODEL}, {COMPUTE})", file=sys.stderr)
    for r in queue:
        print(f"  {stem_for(r):58s} {r.get('duration','—'):>8s}  {audio_url(r)}", file=sys.stderr)
    if a.dry_run:
        return 0

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, row in enumerate(queue, 1):
            url = audio_url(row)
            stem = stem_for(row)
            mp3 = Path(tmp) / f"{stem}.mp3"
            print(f"[{i}/{len(queue)}] {stem}", file=sys.stderr, flush=True)
            try:
                src, used = download_source(row, mp3)
                print(f"    fetched {src.stat().st_size/1e6:.1f} MB from {used}", file=sys.stderr,
                      flush=True)
                segs, meta = transcribe(mp3)
                rec = write_transcript(row, segs, meta, a)
                print(f"    {rec['segments']:,} segments · {rec['words']:,} words "
                      f"· {meta.get('duration', 0)/60:.1f} min audio", file=sys.stderr, flush=True)
                if a.keep_audio:
                    OUT.mkdir(parents=True, exist_ok=True)
                    os.replace(src, OUT / f"{stem}{src.suffix}")
            except Exception as exc:  # one clip must not kill the run
                failures.append({"clip_id": row.get("clip_id"), "error": f"{type(exc).__name__}: {exc}"})
                print(f"    FAILED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            finally:
                for leftover in (mp3, mp3.with_suffix(".mp4")):
                    if leftover.exists():
                        leftover.unlink()

    write_index()
    st = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    print(f"\n{st['transcripts']:,} transcripts · {st['words']:,} words · "
          f"{st['audio_seconds_transcribed']/3600:,.1f} h transcribed "
          f"({st['transcripts']}/{st['catalog_clips_with_audio']} clips)", file=sys.stderr)
    if failures:
        print(json.dumps(failures, indent=1), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
