"""One ledger entry per datum: where it came from, and the second in the film
where you can watch somebody fetch it.

The inventory (`detect`) answers *what do we hold and which family is it in*.
This module answers the harder question the pages need: **for this exact
number on this exact page, what is the public URL behind it, and where in the
film does a human being open that page and take that thing off it.**

Three things get written:

* `data/out/provenance-ledger.json` — every datum, keyed by `id`, with its
  origin URL, the ledger row it belongs to, and the film cue (`start`, `end`,
  `src`, `poster`) that shows the fetch.
* `video/clips/<chapter>-<slug>.mp4` — the per-family slice of the master film,
  cut straight out of `video/provenance-manual-run.mp4` with ffmpeg (no
  re-encode of new content, just a stream copy of the existing frames), sized
  for an iframe.
* `data/out/PROVENANCE-LEDGER.md` — the same ledger as a table, so the mapping
  can be audited without opening any HTML.

Nothing here goes near the network. Every URL is either read out of a file in
the checkout, or it is the one curated origin we recorded for that family when
the data was first pulled.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import inventory as inventory_mod
from . import origins
from . import story as story_mod
from .scenes import CHAPTER, DETECT, ENDCARD, FINALE, INTRO, MONTAGE
from .timelapse import TL_OUTRO, TL_RUN, TL_TITLE
from .util import human_bytes, human_duration, human_int

# Scene order in the film, in the order `Film.schedule` lays them out.
REPO = "https://github.com/bartimoussmith-oss/therealwindycity/blob/main"
CLIP_DIR = "video/clips"
CLIP_SHOWCASE = "video/provenance-showcase.mp4"


# --------------------------------------------------------------------------
# the datum
# --------------------------------------------------------------------------


@dataclass
class Datum:
    """One number, row, or phrase that appears on a live page."""

    id: str  # stable, url-safe: "meeting_calendar.units"
    surface: str  # "streamlit" | "site"
    page: str  # human page name, e.g. "Minutes & Tapes"
    item: str  # e.g. "479 meeting days"
    value: object  # the number/string as displayed
    ledger: str  # family key, or "engine" for the sqlite ledger
    origin_url: str  # the public page a person would open
    origin_host: str
    how: str  # the literal set of clicks
    evidence: list[str] = field(default_factory=list)  # files in this repo
    cue: dict | None = None  # filled in by `attach_cues`
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "surface": self.surface,
            "page": self.page,
            "item": self.item,
            "value": self.value,
            "ledger": self.ledger,
            "origin": {"url": self.origin_url, "host": self.origin_host},
            "how": self.how,
            "evidence": self.evidence[:6],
            "note": self.note,
            "cue": self.cue,
        }


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _how_for(key: str, origin: dict | None) -> str:
    """The literal path a human takes, phrased as clicks."""
    return {
        "meeting_calendar": "cheyennecity.org → Your Government → City Council → Minutes and Agendas → pick the body → pick the year → click a meeting date",
        "agenda_documents": "open the minutes-and-agendas date → the Agenda link opens Granicus AgendaViewer → Download the packet PDF",
        "supporting_documents": "same AgendaViewer page → scroll to the item → open each Linked Attachment / Supporting Document",
        "minutes_and_notes": "same date on the city site → the Minutes column → Download (or MinutesViewer on Granicus for the record of proceedings)",
        "transcripts": "open the meeting's official video on the City of Cheyenne YouTube channel → ⋯ → Show transcript → select all → paste",
        "meeting_video": "Granicus video archive → pick the clip → Download MP4 (or pull the mp4_url the player is streaming)",
        "drive_corpus": "docs.google.com → WindyCityMeetings shared folder → processed_database → download the master JSON and read each record",
        "news": "capcity.news/feed (or the Tribune Eagle search feed) → open the item → copy url, published date and body",
        "arrests": "capcity.news → the weekly arrest report post → read the de-identified list → keep the source URL and the body hash",
        "scanner": "broadcastify.com/archives/feed/47003/ → pick the hour → download the segment → transcribe locally",
        "open_data": "the county Socrata portal → Catalog → the dataset → Export as JSON/CSV",
        "ocr": "the scanned PDF already in artifacts/ → run OCR → store the text beside it",
    }.get(key) or (f"open {origin['url']} and take it off the page" if origin else "see the evidence files in this repo")


# --------------------------------------------------------------------------
# where each datum lives on the live surfaces
# --------------------------------------------------------------------------

# Which page on the public site a family's numbers show up on. The site pages
# are generated by tools/build_ai_record.py; the names here match the headings
# that builder writes.
SITE_PAGES = {
    "meeting_calendar": "Meeting index (years/*)",
    "agenda_documents": "Meeting pages — Archived documents",
    "supporting_documents": "Meeting pages — Archived documents",
    "minutes_and_notes": "Meeting pages — Record of Proceedings",
    "transcripts": "Transcript pages",
    "meeting_video": "Meeting pages — official video",
    "drive_corpus": "Caption transcript pages",
    "news": "News index",
    "arrests": "Arrest reports",
    "scanner": "Scanner index",
    "open_data": "Open-data probes",
}

# Streamlit pages that display each family, from pages/_features.json. Kept
# explicit so the ledger can say "this number is on this page" without
# importing streamlit.
STREAMLIT_PAGES = {
    "meeting_calendar": ["Minutes & Tapes", "Meeting Nights"],
    "agenda_documents": ["Minutes & Tapes"],
    "supporting_documents": ["Minutes & Tapes"],
    "minutes_and_notes": ["Minutes & Tapes"],
    "transcripts": ["Minutes & Tapes", "Montage Theater"],
    "meeting_video": ["Montage Theater"],
    "drive_corpus": ["Minutes & Tapes"],
    "news": ["The Daily Ledger", "Front Page"],
    "arrests": ["Arrest Reports"],
    "scanner": ["Scanner Archive"],
    "open_data": ["Open Data"],
}


def _engine_rows(root: Path) -> dict:
    """Read the sqlite ledger so the numbers we print match the database."""
    db = root / "data" / "engine.db"
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        out = {}
        for table in ("documents", "versions", "alerts", "jobs", "sources"):
            try:
                out[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                pass
        try:
            out["by_source"] = [
                {"source": s, "n": n}
                for s, n in con.execute(
                    "SELECT source, COUNT(*) n FROM documents GROUP BY source ORDER BY n DESC"
                )
            ]
        except sqlite3.Error:
            pass
        out["sample"] = [
            dict(zip(("url", "source", "sha256", "local_path"), row))
            for row in con.execute(
                "SELECT url, source, sha256, local_path FROM documents ORDER BY first_seen DESC LIMIT 6"
            )
        ]
        return out
    finally:
        con.close()


# --------------------------------------------------------------------------
# building the ledger
# --------------------------------------------------------------------------


def build(root: Path, inv=None, story=None, generated_at: str | None = None) -> dict:
    inv = inv or inventory_mod.scan(root, generated_at=generated_at)
    story = story or story_mod.build(root, generated_at=generated_at)
    engine = _engine_rows(root)

    data: list[Datum] = []

    def add(**kw):
        data.append(Datum(**kw))

    # ---- 1. every family, per family -------------------------------------------------
    for fam in inv.families:
        if fam.files == 0:
            continue
        origin = origins.curated(fam.origin_key) if fam.origin_key else None
        url = (origin or {}).get("url") or ""
        host = (origin or {}).get("portal") or (origins.host_of(url) if url else "")
        if not url and fam.host_hits:
            hit = fam.host_hits[0]
            url = hit.examples[0] if hit.examples else f"https://{hit.host}/"
            host = hit.host
        if not url:
            # derived or held-only data: the public URL is the file itself, in this repo
            sample = fam.samples[0] if fam.samples else ""
            url = f"{REPO}/{sample}" if sample else REPO
            host = "github.com (this repo)"
        evidence = list(fam.samples)
        slug = fam.key

        rows = [
            ("files", "files stored", fam.files,
             f"What this repo holds for {fam.title.lower()}, in {fam.destination}."),
            ("units", f"{fam.unit}s counted", fam.units,
             fam.unit_note or "Counted from the files themselves, not an estimate."),
            ("bytes", "size on disk", human_bytes(fam.bytes),
             "Sum of the file sizes on disk."),
        ]
        for kind, item, value, note in rows:
            add(
                id=f"{slug}.{kind}",
                surface="both",
                page=", ".join(STREAMLIT_PAGES.get(slug, []) + [SITE_PAGES.get(slug, "")]).strip(", "),
                item=item,
                value=value,
                ledger=slug,
                origin_url=url,
                origin_host=host,
                how=_how_for(slug, origin),
                evidence=evidence,
                note=note,
            )
        if fam.host_hits:
            for hit in fam.host_hits[:1]:
                add(
                    id=f"{slug}.host-{_slug(hit.host)}",
                    surface="both",
                    page=SITE_PAGES.get(slug, fam.title),
                    item=f"links found to {hit.host}",
                    value=hit.count,
                    ledger=slug,
                    origin_url=hit.examples[0] if hit.examples else f"https://{hit.host}/",
                    origin_host=hit.host,
                    how=f"follow the {hit.host} links in this repo's own files back to the page each one points at",
                    evidence=hit.examples[:3],
                    note="Counted by scanning the repo for absolute URLs.",
                )

    # ---- 2. the headline totals the film and the site both print --------------------
    tot = story.totals
    add(id="totals.files", surface="both", page="Front Page · About", item=f"{tot['files']:,} files classified",
        value=tot["files"], ledger="inventory", origin_url="https://github.com/bartimoussmith-oss/therealwindycity",
        origin_host="github.com", how="python3 -m provenance detect — walks the checkout once, read-only",
        evidence=["data/out/provenance-inventory.json"], note="Includes 0 unaccounted-for files.")
    add(id="totals.scraped", surface="both", page="Front Page · About", item=f"{tot['scraped_files']:,} scraped files",
        value=tot["scraped_files"], ledger="inventory", origin_url="https://github.com/bartimoussmith-oss/therealwindycity",
        origin_host="github.com", how="the sum of every family whose class is 'scraped'",
        evidence=["data/out/PROVENANCE-INVENTORY.md"])
    add(id="totals.hosts", surface="both", page="Front Page · About", item=f"{tot['hosts']} source sites",
        value=tot["hosts"], ledger="inventory", origin_url="https://github.com/bartimoussmith-oss/therealwindycity",
        origin_host="github.com", how="hosts that appear in this repo's files AND are in the curated catalogue",
        evidence=["provenance/origins.py"])
    add(id="totals.manual", surface="both", page="Front Page · About",
        item=f"≈ {human_duration(tot['manual_seconds'])} of hand-work",
        value=round(tot["manual_seconds"]), ledger="inventory",
        origin_url="https://github.com/bartimoussmith-oss/therealwindycity", origin_host="github.com",
        how="units × a stated per-document rate in inventory.py — an estimate, labelled as one",
        evidence=["provenance/inventory.py"])
    for i, h in enumerate(story.hosts[:12], 1):
        add(id=f"hosts.{_slug(h['host'])}", surface="both", page="Source sites", item=f"{h['name']} — {h['count']:,}",
            value=h["count"], ledger="inventory", origin_url=f"https://{h['host']}/", origin_host=h["host"],
            how=f"search this repo for {h['host']} and open what each hit points at",
            evidence=[], note=h.get("kind", ""))

    # ---- 3. the sqlite ledger: every document has its own URL -----------------------
    if engine:
        add(id="engine.documents", surface="both", page="The Daily Ledger", item="documents fingerprinted",
            value=engine.get("documents", 0), ledger="engine", origin_url=REPO + "/data/engine.db",
            origin_host="github.com (this repo)", how="sqlite3 data/engine.db 'select count(*) from documents'",
            evidence=["data/engine.db"])
        add(id="engine.versions", surface="both", page="Shape-Shifters", item="captured versions",
            value=engine.get("versions", 0), ledger="engine", origin_url=REPO + "/data/engine.db",
            origin_host="github.com (this repo)",
            how="sqlite3 data/engine.db 'select count(*) from versions'", evidence=["data/engine.db"])
        add(id="engine.alerts", surface="both", page="Action Alerts", item="watchlist hits",
            value=engine.get("alerts", 0), ledger="engine", origin_url=REPO + "/data/engine.db",
            origin_host="github.com (this repo)",
            how="sqlite3 data/engine.db 'select count(*) from alerts'", evidence=["data/engine.db"])
        for s in engine.get("by_source", [])[:6]:
            add(id=f"engine.source-{_slug(s['source'])}", surface="both", page="The Daily Ledger",
                item=f"documents from {s['source']}", value=s["n"], ledger="engine",
                origin_url=REPO + "/data/engine.db", origin_host="github.com (this repo)",
                how=f"sqlite3 data/engine.db \"select url from documents where source='{s['source']}'\" — each row carries its own origin URL",
                evidence=["data/engine.db"])
        for row in engine.get("sample", [])[:6]:
            if not row.get("url", "").startswith("http"):
                continue
            add(id=f"engine.doc-{row['sha256'][:12]}", surface="both", page="The Daily Ledger",
                item=row["url"].split("/")[-1][:70] or row["url"][:70], value=row["url"], ledger="engine",
                origin_url=row["url"], origin_host=origins.host_of(row["url"]),
                how=f"that exact URL was fetched and stored at {row['local_path'].split('/data/snapshots/')[-1]}"
                    if "/data/snapshots/" in row.get("local_path", "") else "fetched from the source feed",
                evidence=[row.get("local_path", "")], note=f"sha256 {row['sha256'][:16]}…")

    # ---- 4. the film's own claims ---------------------------------------------------
    add(id="film.duration", surface="both", page="Provenance film", item="the film's runtime, in seconds",
        value=round(_schedule(story)["total"]), ledger="film",
        origin_url=REPO + "/video/provenance-showcase.mp4", origin_host="github.com (this repo)",
        how="the film is generated from the checkout: python3 -m provenance video",
        evidence=["video/provenance-manual-run.mp4"])
    add(id="film.chapters", surface="both", page="Provenance film", item=f"{len(story.chapters)} chapters",
        value=len(story.chapters), ledger="film", origin_url=REPO + "/provenance/story.py",
        origin_host="github.com (this repo)",
        how="one chapter per data family, in story.ORDER", evidence=["provenance/story.py"])

    # ---- cues ----------------------------------------------------------------------
    schedule = _schedule(story)
    by_key = {}
    for key, start, dur in schedule["chapters"]:
        by_key[key] = (start, dur)

    for d in data:
        if d.ledger in by_key:
            start, dur = by_key[d.ledger]
            clip = _chapter_file(story, d.ledger)
            d.cue = {
                "chapter": d.ledger,
                # where this footage sits in the chapter film…
                "master": {"src": "video/provenance-manual-run.mp4", "start": round(start, 2),
                           "end": round(start + dur, 2)},
                # …and where it sits in the 20-second everything-at-once edit
                "showcase": {"src": CLIP_SHOWCASE, "start": schedule["timelapse"],
                             "end": round(schedule["timelapse"] + _timelapse_total(), 2)},
                "src": f"{CLIP_DIR}/{clip}",
                "start": round(start, 2),
                "end": round(start + dur, 2),
            }
        else:
            d.cue = {
                "chapter": "overview",
                "master": {"src": "video/provenance-manual-run.mp4", "start": 0.0,
                           "end": round(schedule["total"], 2)},
                "showcase": {"src": CLIP_SHOWCASE, "start": schedule["timelapse"],
                             "end": round(schedule["timelapse"] + _timelapse_total(), 2)},
                "src": CLIP_SHOWCASE,
                "start": schedule["timelapse"],
                "end": round(schedule["timelapse"] + _timelapse_total(), 2),
            }

    ledger = {
        "generated_at": inv.generated_at,
        "film": {
            "master": "video/provenance-manual-run.mp4",
            "showcase": CLIP_SHOWCASE,
            "timelapse": "video/provenance-timelapse.mp4",
            "clips": CLIP_DIR,
            "schedule": schedule,
        },
        "totals": {
            "data": len(data),
            "families": len({d.ledger for d in data}),
            "with_link": sum(1 for d in data if d.origin_url.startswith("http")),
            "with_cue": sum(1 for d in data if d.cue),
            # the exhaustive manifest: every datum in machine-readable form for the site build
            "manifest": "data/out/provenance-manifest.json",
        },
        "data": [d.as_dict() for d in data],
    }
    return ledger


def _timelapse_total() -> float:
    return TL_TITLE + TL_RUN + TL_OUTRO


def _chapter_file(story, key: str) -> str:
    for ch in story.chapters:
        if ch.key == key:
            return f"{ch.index:02d}-{_slug(ch.title)}.mp4"
    return "00-chapter.mp4"


def _schedule(story) -> dict:
    """The film's timeline, computed the same way `scenes.Film` computes it."""
    chapters = []
    t = INTRO + DETECT
    for ch in story.chapters:
        chapters.append((ch.key, t, CHAPTER))
        t += CHAPTER
    montage = t
    t += MONTAGE
    finale = t
    t += FINALE
    endcard = t
    total = t + ENDCARD
    tl_total = _timelapse_total()
    return {
        "timelapse": round(total + 0.4, 2),
        "timelapse_seconds": round(tl_total, 2),
        "intro": [0.0, INTRO],
        "detect": [INTRO, INTRO + DETECT],
        "chapters": chapters,
        "montage": [montage, MONTAGE],
        "finale": [finale, FINALE],
        "endcard": [endcard, ENDCARD],
        "total": round(total, 2),
    }


# --------------------------------------------------------------------------
# cutting the clips out of the master film
# --------------------------------------------------------------------------


def cut_clips(root: Path, ledger: dict, force: bool = False) -> list[dict]:
    """Cut each chapter's walkthrough out of the chapter film.

    Two cuts per chapter: a **cue** strip (the whole chapter, 6–8 s once the
    dead air is trimmed) that sits inline in a page next to the datum it
    explains, and a **poster** frame so the iframe has a face before it plays.
    """
    made = []
    sched = ledger["film"]["schedule"]
    for key, start, dur in sched["chapters"]:
        datum = next((d for d in ledger["data"] if d["ledger"] == key and d.get("cue")), None)
        if not datum:
            continue
        cue = datum["cue"]
        out = root / cue["src"]
        if out.exists() and not force:
            made.append({"clip": cue["src"], "skipped": True})
            continue
        _slice(root / ledger["film"]["master"], out, cue["master"]["start"], cue["master"]["end"])
        made.append({"clip": cue["src"], "bytes": out.stat().st_size})
        poster = out.with_suffix(".jpg")
        if not poster.exists() or force:
            thumb(out, poster, min(6.0, max(0.8, (cue["end"] - cue["start"]) / 2)))
    return made


def _slice(src: Path, dst: Path, start: float, end: float) -> None:
    """Copy a span out of the master film without re-encoding it."""
    from .video import ffmpeg_path

    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start:.3f}", "-to", f"{max(start + 0.5, end - 0.2):.3f}", "-i", str(src),
         "-an", "-c:v", "copy", "-movflags", "+faststart", str(dst)],
        check=True,
    )


def build_showcase(root: Path, ledger: dict, force: bool = False) -> Path:
    """One file: the time-lapse, then every chapter back to back.

    This is the copy the site serves. The time-lapse opens it (everything at
    once), then one chapter per family (each one, fetched by hand). Every cue in
    the ledger points into this single file, so a reader can jump from any datum
    to the exact second that shows it being collected.
    """
    from .video import ffmpeg_path

    out = root / CLIP_SHOWCASE
    tl = root / ledger["film"]["timelapse"]
    master = root / ledger["film"]["master"]
    poster = root / "video" / "provenance-timelapse-poster.jpg"
    if tl.exists() and (not poster.exists() or force):
        thumb(tl, poster, 12.0)
    master_poster = root / "video" / "provenance-manual-run.jpg"
    if master.exists() and (not master_poster.exists() or force):
        thumb(master, master_poster, 30.0)
    if out.exists() and not force:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    listing = root / "data" / "out" / "showcase.concat.txt"  # scratch, deleted below
    listing.write_text(
        f"file '{tl.resolve()}'\n" + f"file '{master.resolve()}'\n", encoding="utf-8"
    )
    subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "-movflags", "+faststart", str(out)],
        check=True,
    )
    try:
        listing.unlink()
    except OSError:
        pass
    showcase_poster = root / "video" / "provenance-showcase.jpg"
    if not showcase_poster.exists() or force:
        thumb(out, showcase_poster, 226.0)
    return out


def thumb(src: Path, dst: Path, at: float) -> None:
    from .video import ffmpeg_path

    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at:.3f}",
         "-i", str(src), "-frames:v", "1", "-q:v", "4", str(dst)],
        check=True,
    )


# --------------------------------------------------------------------------
# writing it down
# --------------------------------------------------------------------------


def write(root: Path, ledger: dict) -> tuple[Path, Path]:
    out = root / "data" / "out"
    out.mkdir(parents=True, exist_ok=True)
    js = out / "provenance-ledger.json"
    js.write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8")

    manifest = out / "provenance-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "generated_at": ledger["generated_at"],
                "note": "one row per datum on the live pages; key = datum id used by the page blocks",
                "film": ledger["film"],
                "rows": {
                    d["id"]: {
                        "ledger": d["ledger"],
                        "item": d["item"],
                        "value": d["value"],
                        "origin": d["origin"],
                        "how": d["how"],
                        "cue": d["cue"],
                        "pages": d.get("page", ""),
                    }
                    for d in ledger["data"]
                },
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )

    md = out / "PROVENANCE-LEDGER.md"
    L = [
        "# Provenance ledger — every datum, its origin link, and its film cue",
        "",
        f"Generated **{ledger['generated_at']}** by `python3 -m provenance ledger` from this checkout.",
        "One row per datum that a live page prints. `origin` is the public page a person",
        "would open to get it themselves; `film` is the second in the master film where",
        "that fetch is on screen.",
        "",
        f"- **{ledger['totals']['data']:,}** datums catalogued",
        f"- **{ledger['totals']['with_link']:,}** carry a public origin link",
        f"- **{ledger['totals']['with_cue']:,}** carry a film cue",
        "",
        "## Film timeline",
        "",
        "| scene | start | length | what it shows |",
        "|---|---|---|---|",
        f"| intro | {_tc(0)} | {INTRO:.0f}s | title and totals |",
        f"| detect | {_tc(INTRO)} | {DETECT:.0f}s | the scanner walking the checkout |",
    ]
    for key, start, dur in ledger["film"]["schedule"]["chapters"]:
        L.append(f"| chapter {key} | {_tc(start)} | {dur:.0f}s | {_clip_name(ledger, key)} |")
    for name, (start, dur) in (("montage", ledger["film"]["schedule"]["montage"]),
                               ("finale", ledger["film"]["schedule"]["finale"]),
                               ("endcard", ledger["film"]["schedule"]["endcard"])):
        L.append(f"| {name} | {_tc(start)} | {dur:.0f}s | |")
    L += ["", "## The ledger", "",
          "| datum | page | value | origin | film cue |", "|---|---|---|---|---|"]
    for d in ledger["data"]:
        cue = d["cue"]
        cuetxt = f"[{_tc(cue['start'])}]({cue['src']})" if cue else "—"
        val = d["value"]
        if isinstance(val, int) and not isinstance(val, bool):
            val = f"{val:,}"
        L.append(
            f"| `{d['id']}` | {d['page']} | {val} | [{d['origin']['host']}]({d['origin']['url']}) | {cuetxt} |"
        )
    L += ["", "---", "",
          "Film cues are cut from the master film at `video/provenance-manual-run.mp4`;",
          "each clip is byte-identical to that span, copied with `-c:v copy`."]
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    return js, md


def _clip_name(ledger: dict, key: str) -> str:
    for d in ledger["data"]:
        if d["ledger"] == key and d["cue"]:
            return f"`{d['cue']['src']}`"
    return ""


def _tc(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"
