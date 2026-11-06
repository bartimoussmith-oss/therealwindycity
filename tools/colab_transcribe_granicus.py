#!/usr/bin/env python3
"""One file. Paste it into a Colab cell and run it.

Whisper over the City of Cheyenne's own meeting audio — the MP3s the portal serves —
written out as timestamped transcripts into your Google Drive.

No repository, no setup: it reads the portal's clip list itself. Output matches
`transcripts/granicus/` in the repo, so a session drops straight in.

  run CONFIG as-is  → transcribes the next few clips, resumably
  summary()         → what you have so far
  zip_results()     → one .zip to download out of the session

Per clip it writes `<clip_id>-<date>-<slug>.md` (a table, every time deep-linked into the
official MP3 as #t=3725), a `.txt`, `manifest.json` (the resume state) and `INDEX.md`.
Every transcript says it is machine transcription that can be wrong and is not official.

Rough speed on a free Colab T4, for the 792 hours on the portal:

  tiny.en   ~60x realtime  → ~13 h compute   small.en  ~30x  → ~26 h
  large-v3  ~10x realtime  → ~80 h compute, best on names

Set CONFIG, run, repeat. That is the workflow.
"""

from __future__ import annotations

import datetime as dt
import html as _html
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------
# EDIT THIS
# --------------------------------------------------------------------------

CONFIG = {
    # ---- what -------------------------------------------------------------
    # None = every clip on the portal (478 of them, 792 hours). Narrow it with:
    #   years=(2026,)            only 2026
    #   clip_ids=("1144",)       one meeting
    "years": None,
    "clip_ids": None,
    # Meeting names containing "Agenda Only" are almost always silent; skip them.
    "skip_agenda_only": True,

    # ---- how many per session ---------------------------------------------
    # These two are the session stop conditions: whichever comes first. A free
    # Colab dies around 12 h but throttles much earlier, so keep it modest.
    "max_clips": 6,
    "max_minutes": 300,        # stated meeting length, not wall clock
    "max_hours": 3.0,          # wall clock, hard stop

    # ---- whisper ----------------------------------------------------------
    "model": "small.en",       # tiny.en / base.en / small.en / medium.en / large-v3
    "compute": "auto",         # auto → float16 on GPU, int8 on CPU
    "language": "en",
    "beam_size": 5,
    "vad": True,

    # ---- where ------------------------------------------------------------
    "use_drive": True,         # mount Drive and write there; else ./granicus
    "drive_subdir": "granicus-transcripts",
    "write_json": False,       # per-clip segment JSON as well as the markdown
    "also_txt": True,
    "redo": False,             # re-transcribe clips already in the manifest
}

PORTAL = "https://cheyenne.granicus.com/ViewPublisher.php?view_id=2"
VIEWS = (4, 2)                 # both carry the same meetings; 4 has MP4s, 2 has MP3s
SCHEMA = ("clip_id", "name", "date_display", "date_iso", "timestamp", "duration",
          "mp4_url", "stream_url", "mp3_url", "player_url", "agenda_url", "minutes_url")
NOTICE = ("Machine transcription of the City of Cheyenne's own meeting audio. It can be "
          "wrong — names, numbers and motions especially. Verify against the linked video "
          "before relying on any line. Not an official transcript.")
UA = {"User-Agent": "therealwindycity/1.0 (+https://bartimoussmith-oss.github.io/therealwindycity/)"}


# --------------------------------------------------------------------------
# setup: packages, drive, output folder
# --------------------------------------------------------------------------

def install():
    """faster-whisper on a Colab image. Idempotent and quiet."""
    try:
        import faster_whisper  # noqa: F401
        return
    except ImportError:
        pass
    print("installing faster-whisper …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "faster-whisper==1.2.1", "av==18.1.0"], check=True)


def out_dir(cfg=CONFIG) -> Path:
    """Drive if we can mount it, so a dead session does not lose the work."""
    if cfg.get("use_drive"):
        try:
            from google.colab import drive  # type: ignore

            if not Path("/content/drive/MyDrive").exists():
                drive.mount("/content/drive")
            d = Path("/content/drive/MyDrive") / cfg.get("drive_subdir", "granicus-transcripts")
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception as exc:
            print(f"  Drive not mounted ({type(exc).__name__}); writing locally instead")
    d = Path.cwd() / "granicus"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# the portal: read the clip list ourselves
# --------------------------------------------------------------------------

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CLIP = re.compile(r"clip_id=(\d+)")
_DATE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})")
_DUR = re.compile(r"(\d{1,2})h\s*(\d{1,2})m")
_MP4 = re.compile(r"https://archive-video\.granicus\.com/cheyenne/cheyenne_[0-9a-f-]+\.mp4")
_MP3 = re.compile(r"https://archive-video\.granicus\.com/cheyenne/cheyenne_[0-9a-f-]+\.mp3")
_MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def _text(fragment: str) -> str:
    raw = _html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", raw.replace("\xa0", " ")).strip()


def parse_view(page: str) -> list[dict]:
    """Rows from one ViewPublisher page, in the repo catalog's schema."""
    rows = []
    for block in _ROW.findall(page):
        clip, mp4 = _CLIP.search(block), _MP4.search(block)
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.S | re.I)
        if not clip or not cells:
            continue
        name = _text(cells[0])
        date = ""
        for cell in cells[:3]:
            m = _DATE.search(_text(cell))
            if m and m.group(1) in _MONTHS:
                date = f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
                break
        if not (name and date):
            continue
        dur = _DUR.search(_text(block))
        mp3 = _MP3.search(block)
        row = {
            "clip_id": clip.group(1),
            "name": name,
            "date_display": f"{date[5:7]}/{date[8:10]}/{date[0:4]}",
            "date_iso": date,
            "timestamp": "",
            "duration": f"{int(dur.group(1)):02d}h {int(dur.group(2)):02d}m" if dur else "",
            "mp4_url": mp4.group(0) if mp4 else "",
            "stream_url": "",
            "mp3_url": mp3.group(0) if mp3 else "",
            "player_url": f"https://cheyenne.granicus.com/player/clip/{clip.group(1)}?view_id=2&redirect=true",
            "agenda_url": f"https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id={clip.group(1)}",
            "minutes_url": "",
        }
        row["mp3_url"] = row["mp3_url"] or audio_url(row)
        rows.append({k: row.get(k, "") for k in SCHEMA})
    return rows


def audio_url(row: dict) -> str:
    """The portal's MP3. Its HLS stream is a playlist, not a file, so derive from the MP4."""
    if row.get("mp3_url"):
        return row["mp3_url"]
    for key in ("mp4_url", "stream_url"):
        url = row.get(key) or ""
        if url.lower().endswith(".mp4"):
            return url[:-4] + ".mp3"
    return ""


def scrape(views=VIEWS) -> list[dict]:
    """Every clip the portal lists, merged across views and de-duplicated."""
    merged: dict[str, dict] = {}
    for view in views:
        url = f"https://cheyenne.granicus.com/ViewPublisher.php?view_id={view}"
        print(f"  reading {url}")
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                page = r.read().decode("utf-8", "replace")
        except Exception as exc:
            print(f"    unreachable: {type(exc).__name__}: {exc}")
            continue
        for row in parse_view(page):
            merged[row["clip_id"]] = {**merged.get(row["clip_id"], {}),
                                      **{k: v for k, v in row.items() if v}}
    rows = sorted(merged.values(), key=lambda r: (r["date_iso"], int(r["clip_id"])))
    print(f"  {len(rows)} clips on the portal")
    return rows


def minutes(row: dict) -> int:
    try:
        h, rest = (row.get("duration") or "0h 0m").split("h", 1)
        return int(h) * 60 + int(rest.strip().rstrip("m") or 0)
    except Exception:
        return 0


def slug(text: str, limit: int = 48) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:limit].rstrip("-")
            or "meeting")


def stem_for(row: dict) -> str:
    return f"{int(row['clip_id']):04d}-{row['date_iso']}-{slug(row.get('name', ''))}"


# --------------------------------------------------------------------------
# resume state
# --------------------------------------------------------------------------

def load_manifest(d: Path) -> dict[str, dict]:
    p = d / "manifest.json"
    if not p.exists():
        return {}
    try:
        return {str(i["clip_id"]): i for i in json.loads(p.read_text()).get("items", [])}
    except Exception:
        return {}


def save_manifest(d: Path, items: dict[str, dict], cfg=CONFIG) -> None:
    rows = sorted(items.values(), key=lambda r: (r.get("date") or "", int(r.get("clip_id") or 0)))
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": cfg["model"], "compute_type": cfg["compute"], "beam_size": cfg["beam_size"],
        "vad": cfg["vad"], "transcripts": len(rows),
        "audio_seconds_transcribed": round(sum(r.get("duration_audio_seconds") or 0 for r in rows), 1),
        "words": sum(r.get("words") or 0 for r in rows),
        "notice": NOTICE, "items": rows,
    }
    (d / "manifest.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def write_index(d: Path, items: dict[str, dict]) -> None:
    rows = sorted((r for r in items.values() if r.get("stem")),
                  key=lambda r: (r.get("date") or "", int(r.get("clip_id") or 0)))
    hours = sum(r.get("duration_audio_seconds") or 0 for r in rows) / 3600
    md = ["# The portal's meeting audio, transcribed", "", f"*{NOTICE}*", "",
          f"{len(rows):,} clips · {hours:,.1f} hours · "
          f"{sum(r.get('words') or 0 for r in rows):,} words · model `{CONFIG['model']}`", "",
          f"Source: the City of Cheyenne's own MP3s, listed on [the portal]({PORTAL}).", "",
          "| date | meeting | stated | words | transcript | audio |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r.get('date','')} | {r.get('name','')} | {r.get('duration_stated','—')} | "
                  f"{r.get('words',0):,} | [{r['stem']}.md]({r['stem']}.md) | "
                  f"[mp3]({r.get('audio_url','')}) |")
    md.append("")
    (d / "INDEX.md").write_text("\n".join(md), encoding="utf-8")


# --------------------------------------------------------------------------
# whisper
# --------------------------------------------------------------------------

_MODEL = None


def load_model(cfg=CONFIG):
    """Load once. Try the GPU, fall back to CPU rather than dying on a cuDNN mismatch."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    from faster_whisper import WhisperModel

    want = cfg.get("compute", "auto")
    if want == "auto":
        gpu = False
        try:
            import torch  # noqa: F401

            gpu = torch.cuda.is_available()
        except Exception:
            gpu = False
        want = "float16" if gpu else "int8"
    try:
        print(f"  loading {cfg['model']} ({want}) …")
        _MODEL = WhisperModel(cfg["model"], device="cuda" if want == "float16" else "cpu",
                              compute_type=want)
        print("  model ready")
        return _MODEL
    except Exception as exc:
        if want != "int8":
            print(f"  GPU load failed ({type(exc).__name__}: {exc}); falling back to CPU int8")
            _MODEL = WhisperModel(cfg["model"], device="cpu", compute_type="int8")
            return _MODEL
        raise


def transcribe(path: Path, cfg=CONFIG) -> tuple[list[dict], dict]:
    segments, info = load_model(cfg).transcribe(
        str(path), language=cfg.get("language", "en"), beam_size=cfg.get("beam_size", 5),
        vad_filter=cfg.get("vad", True), condition_on_previous_text=False,
    )
    out = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": (s.text or "").strip()}
           for s in segments]
    return out, {"duration": round(float(getattr(info, "duration", 0) or 0), 2),
                 "language": getattr(info, "language", cfg.get("language")),
                 "language_probability": round(float(
                     getattr(info, "language_probability", 0) or 0), 3)}


def stamp(seconds: float) -> str:
    s = int(seconds)
    return (f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600
            else f"{s // 60}:{s % 60:02d}")


# --------------------------------------------------------------------------
# write one transcript
# --------------------------------------------------------------------------

def write_transcript(d: Path, row: dict, segments: list[dict], meta: dict,
                     items: dict[str, dict], cfg=CONFIG) -> dict:
    stem = stem_for(row)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = audio_url(row)
    words = sum(len(s["text"].split()) for s in segments)
    rec = {
        "clip_id": row["clip_id"], "date": row["date_iso"], "name": row.get("name", ""),
        "duration_stated": row.get("duration", ""),
        "duration_audio_seconds": meta.get("duration", 0),
        "segments": len(segments), "words": words, "stem": stem,
        "language": meta.get("language"), "language_probability": meta.get("language_probability"),
        "model": cfg["model"], "compute_type": cfg["compute"], "beam_size": cfg["beam_size"],
        "vad": cfg["vad"], "transcribed_at": now, "audio_url": url,
        "player_url": row.get("player_url", ""), "agenda_url": row.get("agenda_url", ""),
        "portal": PORTAL, "notice": NOTICE,
    }

    lines = [
        f"# {row.get('name', 'Meeting')} — {row['date_iso']}",
        "",
        f"*{NOTICE}*",
        "",
        f"- **Source audio (official):** {url}",
        f"- **Meeting page at the city:** {row.get('player_url') or row.get('agenda_url', '')}",
        f"- **Portal:** {PORTAL}",
        f"- **Clip id:** {row['clip_id']} · **stated duration:** {row.get('duration', '—')}"
        f" · **audio length:** {stamp(meta.get('duration', 0) or 0)}",
        f"- **Transcribed:** {now} with faster-whisper `{cfg['model']}` "
        f"({rec['compute_type']}, beam {cfg['beam_size']}, VAD "
        f"{'on' if cfg['vad'] else 'off'})",
        f"- **Segments:** {len(segments):,} · **words:** {words:,}",
        "",
        "| time | what was said |",
        "|---|---|",
    ]
    for s in segments:
        lines.append(f"| [{stamp(s['start'])}]({url}#t={int(s['start'])}) "
                     f"| {s['text'].replace('|', chr(92) + '|')} |")
    lines.append("")
    (d / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")

    if cfg.get("also_txt", True):
        (d / f"{stem}.txt").write_text(
            "\n".join(f"[{stamp(s['start'])}] {s['text']}" for s in segments) + "\n",
            encoding="utf-8")
    if cfg.get("write_json"):
        (d / f"{stem}.json").write_text(
            json.dumps({**rec, "segments_data": segments}, indent=1) + "\n", encoding="utf-8")

    items[str(row["clip_id"])] = rec
    save_manifest(d, items, cfg)
    return rec


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------

def download(row: dict, dest: Path) -> tuple[Path, str]:
    """Prefer the portal's MP3; fall back to its MP4 and let Whisper decode the audio."""
    for url, suffix in ((audio_url(row), ".mp3"), (row.get("mp4_url") or "", ".mp4")):
        if not url:
            continue
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as fh:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
            return dest, url
        except Exception as exc:
            print(f"    {suffix[1:]} failed ({type(exc).__name__}); trying the other")
    raise RuntimeError("could not download this clip's audio or video")


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def plan(clips: list[dict], items: dict[str, dict], cfg=CONFIG) -> list[dict]:
    if cfg.get("clip_ids"):
        wanted = {str(c) for c in cfg["clip_ids"]}
        rows = [r for r in clips if r["clip_id"] in wanted]
    else:
        rows = [r for r in clips if audio_url(r) or r.get("mp4_url")]
        if cfg.get("years"):
            years = tuple(str(y) for y in cfg["years"])
            rows = [r for r in rows if r["date_iso"][:4] in years]
        if cfg.get("skip_agenda_only", True):
            rows = [r for r in rows if "agenda only" not in (r.get("name") or "").lower()]
    if not cfg.get("redo"):
        rows = [r for r in rows if r["clip_id"] not in items]

    keep, total = [], 0
    for r in rows:
        if cfg.get("max_clips") and len(keep) >= int(cfg["max_clips"]):
            break
        d = minutes(r)
        if cfg.get("max_minutes") and total + d > int(cfg["max_minutes"]) and keep:
            break
        keep.append(r)
        total += d
    return keep


def run(cfg: dict | None = None) -> None:
    cfg = {**CONFIG, **(cfg or {})}
    install()
    d = out_dir(cfg)
    print(f"output: {d}\n")

    items = load_manifest(d)
    print(f"already done: {len(items)} clips")
    clips = scrape()
    queue = plan(clips, items, cfg)
    todo = sum(minutes(r) for r in queue)
    left = [r for r in clips if r["clip_id"] not in items and (audio_url(r) or r.get("mp4_url"))]
    print(f"this session: {len(queue)} clips ({todo:,} min) · "
          f"still to go overall: {len(left):,} clips "
          f"({sum(minutes(r) for r in left):,} min ≈ {sum(minutes(r) for r in left)/60:,.1f} h)")
    if not queue:
        print("\nnothing left to do for this selection.")
        return
    for r in queue:
        print(f"  {stem_for(r):58s} {r.get('duration', '—'):>8s}")
    print()

    deadline = time.time() + float(cfg.get("max_hours", 3.0)) * 3600
    load_model(cfg)
    tmp = d / "_audio"
    tmp.mkdir(exist_ok=True)
    failures: list[dict] = []

    for i, row in enumerate(queue, 1):
        if time.time() > deadline:
            print(f"\nwall-clock budget reached after {i - 1} clip(s); stopping cleanly.")
            break
        stem = stem_for(row)
        print(f"[{i}/{len(queue)}] {stem}", flush=True)
        src = tmp / (stem + ".part")
        try:
            t0 = time.time()
            audio, used = download(row, src)
            print(f"    {audio.stat().st_size / 1e6:.1f} MB from {used.rsplit('/', 1)[-1]}")
            segs, meta = transcribe(audio, cfg)
            rec = write_transcript(d, row, segs, meta, items, cfg)
            took = time.time() - t0
            audio_min = (rec["duration_audio_seconds"] or 0) / 60
            speed = (audio_min * 60 / took) if took else 0
            print(f"    {rec['segments']:,} segments · {rec['words']:,} words · "
                  f"{audio_min:.0f} min audio in {took/60:.1f} min ({speed:.0f}x realtime)")
        except Exception as exc:
            failures.append({"clip_id": row.get("clip_id"), "error": f"{type(exc).__name__}: {exc}"})
            print(f"    FAILED: {type(exc).__name__}: {exc}")
        finally:
            for p in tmp.glob(stem + ".*"):
                p.unlink(missing_ok=True)

    write_index(d, items)
    summary(cfg=cfg)
    if failures:
        print(f"\n{len(failures)} clip(s) failed this session — rerun to retry them:")
        for f in failures:
            print(f"  {f['clip_id']}: {f['error']}")


def summary(cfg: dict | None = None) -> None:
    """What is done so far, and how much is left."""
    cfg = {**CONFIG, **(cfg or {})}
    d = out_dir(cfg)
    items = load_manifest(d)
    done_audio = sum(i.get("duration_audio_seconds") or 0 for i in items.values())
    print(f"\n{d}")
    print(f"  {len(items):,} transcripts · {done_audio/3600:,.1f} h of audio · "
          f"{sum(i.get('words') or 0 for i in items.values()):,} words")
    if items:
        recent = sorted(items.values(), key=lambda r: r.get("transcribed_at") or "")[-5:]
        print("  newest:")
        for r in recent:
            print(f"    {r.get('date','')}  {r.get('name','')[:44]:44s} {r.get('words',0):>8,} words")
    print("  the whole portal, at capture: 478 clips · 792.5 h")
    print(f"  left: ~{max(0, 792.5 - done_audio/3600):,.1f} h of audio")
    try:
        size = sum(p.stat().st_size for p in d.glob("*.*")) / 1e6
        print(f"  on disk: {size:,.1f} MB")
    except Exception:
        pass


def zip_results(cfg: dict | None = None) -> Path:
    """Bundle everything into one .zip so a Colab session can download it."""
    import zipfile

    cfg = {**CONFIG, **(cfg or {})}
    d = out_dir(cfg)
    out = Path("/content") / f"granicus-transcripts-{dt.date.today():%Y%m%d}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(d.glob("*")):
            if p.is_file() and p.suffix in (".md", ".txt", ".json"):
                z.write(p, p.name)
    print(f"{out}  ({out.stat().st_size/1e6:,.1f} MB)")
    try:
        from google.colab import files  # type: ignore

        files.download(str(out))
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# offline check — no network, no model
# --------------------------------------------------------------------------

FIXTURE = """<table>
<tr><td>City Council Meeting</td><td>1792998000Oct&nbsp;26,&nbsp;2026</td><td>02h&nbsp;36m</td>
<td><a href="https://cheyenne.granicus.com/AgendaViewer.php?view_id=4&amp;clip_id=1144">Agenda</a></td>
<td></td><td>Video</td><td></td>
<td><a href="https://archive-video.granicus.com/cheyenne/cheyenne_e443a894-d227-11f1-89ef-005056a84798.mp4">MP4</a></td></tr>
<tr><td>Cheyenne City Council</td><td>1212994800Jun 9, 2008</td><td>02h 27m</td>
<td><a href="http://cheyenne.granicus.com/AgendaViewer.php?view_id=2&amp;clip_id=28">Agenda</a></td>
<td><a href="http://cheyenne.granicus.com/MinutesViewer.php?view_id=2&amp;clip_id=28">Minutes</a></td>
<td>Video</td>
<td><a href="https://archive-video.granicus.com/cheyenne/cheyenne_0395a033-06af-41d3-8760-aa8efe3350c5.mp3">MP3</a></td>
<td><a href="https://archive-video.granicus.com/cheyenne/cheyenne_0395a033-06af-41d3-8760-aa8efe3350c5.mp4">MP4</a></td></tr>
</table>"""


def self_test() -> int:
    """Parse, write, resume — with no network and no model. Run this first in Colab."""
    import tempfile

    bad = []
    rows = {r["clip_id"]: r for r in parse_view(FIXTURE)}
    if set(rows) != {"1144", "28"}:
        bad.append(f"clip ids {sorted(rows)}")
    if rows.get("1144", {}).get("date_iso") != "2026-10-26":
        bad.append("1144 date")
    if rows.get("1144", {}).get("duration") != "02h 36m":
        bad.append(f"1144 duration {rows.get('1144', {}).get('duration')!r}")
    if not audio_url(rows.get("1144", {})).endswith(".mp3"):
        bad.append("1144 mp3 not derived from mp4")
    if not rows.get("28", {}).get("mp3_url", "").endswith(".mp3"):
        bad.append("28 mp3 not parsed")
    if rows.get("28", {}).get("duration") != "02h 27m":
        bad.append("28 duration")

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        cfg = {**CONFIG, "use_drive": False, "also_txt": True, "write_json": True,
               "model": "self-test", "compute": "int8"}
        segs = [{"start": 0.0, "end": 4.2, "text": "The meeting is called to order."},
                {"start": 3725.5, "end": 3729.0, "text": "Roll call: all members present."}]
        items: dict[str, dict] = {}
        rec = write_transcript(d, rows["1144"], segs, {"duration": 9362.0, "language": "en",
                                                      "language_probability": 0.99}, items, cfg)
        if rec["words"] != 11:
            bad.append(f"word count {rec['words']}")
        md = (d / f"{rec['stem']}.md").read_text()
        if "#t=3725" not in md:
            bad.append("timestamp not deep-linked into the mp3")
        if "1:02:05" not in md:
            bad.append("hour timestamp not formatted")
        if not (d / f"{rec['stem']}.txt").exists() or not (d / f"{rec['stem']}.json").exists():
            bad.append("txt/json not written")
        write_index(d, items)
        if not (d / "INDEX.md").exists():
            bad.append("INDEX.md not written")
        again = load_manifest(d)
        if set(again) != {"1144"}:
            bad.append(f"manifest round-trip {sorted(again)}")
        queue = plan([rows["1144"], rows["28"]], again, {**cfg, "max_clips": 10})
        if [r["clip_id"] for r in queue] != ["28"]:
            bad.append(f"resume did not skip the finished clip: {[r['clip_id'] for r in queue]}")

    for b in bad:
        print(f"  FAIL {b}")
    print("  ok — parser, deep links, manifest and resume all work" if not bad else "")
    return 1 if bad else 0


# In Colab, paste the whole file into a cell and run it: __name__ is "__main__" there
# too, so this fires. From a shell it is `python3 tools/colab_transcribe_granicus.py`.
# The self-test is instant and tells you straight away if the portal markup has moved.
if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    self_test()
    run()
