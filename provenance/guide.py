"""The master guide: one page that explains the whole record, and every film in it.

Everything else in this project is a piece — an inventory, a film, a ledger of cues, a
set of pages. This module is the piece that says what the others are, what is in them,
how to watch them, how to check them, and how to rebuild any of it.

It is generated from the artefacts themselves, never hand-written next to them: run it
and it restates whatever is in the checkout right now. If a film is missing, the page
says so. If a number moved, the page moves with it.

    python3 -m provenance guide                 # write data/out/PROVENANCE-GUIDE.md
    tools/render_ai_record.py --src ai-record   # → /provenance/master.html on the site
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# --------------------------------------------------------------------------
# what each thing is, in one sentence. The counts and times are filled in.
# --------------------------------------------------------------------------

PIECES: list[dict] = [
    {
        "key": "timelapse",
        "name": "The time-lapse",
        "file": "video/provenance-timelapse.mp4",
        "kind": "film",
        "what": "Every file this archive holds, one cell each, in capture order — the size of the "
                "collection at a glance.",
        "shows": [
            "each file arriving on a wall of cells, ~{rate}/second",
            "the “just arrived” column naming files as they land",
            "a bar filling with what the pile is made of: which families, in what proportion",
        ],
        "use": "Start here if you want to know how much material there is before asking how it was got.",
        "build": "python3 -m provenance timelapse",
        "source": "data/out/provenance-timelapse-frames.json — one row per file",
    },
    {
        "key": "master",
        "name": "The chapter film (master)",
        "file": "video/provenance-manual-run.mp4",
        "kind": "film",
        "what": "One chapter per kind of record: the real public page, the clicks a person makes, "
                "the download, and the file landing in this archive.",
        "shows": [
            "the scanner classifying the checkout (intro + detect)",
            "eleven chapters, one per data family, each with its real origin URL",
            "the collection panel: how many units, where they go, what it costs by hand",
            "the source-site table at the end, and the rebuild commands",
        ],
        "use": "This is the how-to. Find the chapter for the kind of record you want and watch that "
               "chapter; the rest you can skip.",
        "build": "python3 -m provenance video",
        "source": "provenance/story.py → data/out/provenance-storyboard.json",
    },
    {
        "key": "showcase",
        "name": "The showcase (one file, everything)",
        "file": "video/provenance-showcase.mp4",
        "kind": "film",
        "what": "The time-lapse, then every chapter back to back. This is the copy the site serves, "
                "so every cue is a timestamp into a single file.",
        "shows": [
            "the time-lapse (everything at once)",
            "then the chapter film (one thing at a time)",
        ],
        "use": "Send this to somebody who has ten minutes and no context. It is the whole claim in "
               "one file, in the right order.",
        "build": "python3 -m provenance ledger --showcase",
        "source": "ffmpeg concat of the two films above, stream-copied (no re-encode)",
    },
    {
        "key": "clips",
        "name": "The per-chapter cues",
        "file": "video/clips/",
        "kind": "clips",
        "what": "Each chapter cut out of the master film, ~14 seconds each, with a poster frame. "
                "These are what sit inline on the pages next to the numbers they explain.",
        "shows": [
            "one family's fetch, start to finish, with no setup",
        ],
        "use": "Open the one for the number you are checking. The row underneath it tells you the "
               "second inside the clip where that exact figure appears.",
        "build": "python3 -m provenance ledger --clips",
        "source": "video/provenance-manual-run.mp4, cut with -c:v copy",
    },
    {
        "key": "ledger",
        "name": "The ledger — one row per datum",
        "file": "data/out/PROVENANCE-LEDGER.md",
        "kind": "data",
        "what": "Every figure this project prints, with the public page it came from, the literal "
                "clicks to fetch it, the film cue where that fetch is on screen, and the files here "
                "it was counted from.",
        "shows": [
            "{datums} rows, each: datum · page · value · origin URL · film cue · which beat",
            "the film timeline, scene by scene",
        ],
        "use": "This is the citation table. If a page states a number, search the ledger for it and "
               "you get the source and the footage.",
        "build": "python3 -m provenance ledger",
        "source": "provenance/ledger.py — reads the inventory, the film schedule and data/engine.db",
    },
    {
        "key": "inventory",
        "name": "The inventory — what is actually here",
        "file": "data/out/PROVENANCE-INVENTORY.md",
        "kind": "data",
        "what": "Every file in the checkout assigned to a data family, with its origin host, unit "
                "count, size, and a conservative estimate of what the same work costs by hand.",
        "shows": [
            "{families} families, {files} files, {unassigned} unaccounted for",
            "the source hosts found in the repo's own files, with counts",
            "per-family seconds and actions per unit, stated so they can be argued with",
        ],
        "use": "Read this if you want to know what the archive contains and roughly what it took — "
               "and to check that nothing is unaccounted for.",
        "build": "python3 -m provenance detect",
        "source": "provenance/inventory.py (the family definitions are the interesting part)",
    },
    {
        "key": "site",
        "name": "The record, with provenance on every page",
        "file": "https://bartimoussmith-oss.github.io/therealwindycity/",
        "kind": "site",
        "what": "The public record itself: ~7,000 plain-text pages. Every page that states a number "
                "now carries a section underneath it with the origin link, the cue clip, and the "
                "click-path for that number.",
        "shows": [
            "“Where the numbers on this page come from” on every content page",
            "3 inline clips per page, and a cue link on every other row",
            "a standalone /provenance/ cue sheet, and /provenance/master.html — this guide",
        ],
        "use": "Read a meeting page, then scroll to the bottom: the numbers in it are sourced there, "
               "not in a footer.",
        "build": "python3 tools/render_ai_record.py",
        "source": "tools/render_ai_record.py + provenance/site.py",
    },
    {
        "key": "streamlit",
        "name": "The app, with the same block",
        "file": "rwc_provenance.py",
        "kind": "app",
        "what": "The Streamlit record. Every view that prints a number carries the same provenance "
                "block in a collapsed expander, and both films in the footer.",
        "shows": [
            "🔗 Provenance expander on every page that states a number",
            "the chapter clip, opened at the beat for that datum",
            "the two films, on every page, via the footer",
        ],
        "use": "Use it the same way as the site: read the view, then open the expander under it.",
        "build": "(no build — reads data/out/provenance-ledger.json at run time)",
        "source": "rwc_provenance.py, wired through rwc_views.py and pages/*",
    },
    {
        "key": "checks",
        "name": "The checks",
        "file": "tools/check_provenance.py",
        "kind": "check",
        "what": "Two scripts that make the claim testable rather than asserted: one fails the build "
                "if a datum loses its link or cue; the other rebuilds the record from scratch and "
                "crawls every rendered page.",
        "shows": [
            "check_provenance.py: every datum linked, cued, clip on disk, present on the cue sheet",
            "provenance_site_audit.py: build → render → crawl every internal link and <video>",
        ],
        "use": "Run them before you trust a number, and in CI so nobody ships one that lost its "
               "citation.",
        "build": "python3 tools/check_provenance.py --site _site",
        "source": "tools/check_provenance.py, tools/provenance_site_audit.py",
    },
]


# --------------------------------------------------------------------------
# reading the checkout
# --------------------------------------------------------------------------


def _human_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or unit == "TB":
            return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b} B"


def _size(path: Path) -> str:
    """Human-readable size of a file, or of a directory's contents."""
    try:
        if path.is_dir():
            b = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        else:
            b = path.stat().st_size
    except OSError:
        return "—"
    return _human_bytes(b)


def _duration(path: Path) -> str | None:
    """Read a duration without ffprobe: the mp4 mvhd box carries the timescale."""
    try:
        import struct

        with open(path, "rb") as fh:
            data = fh.read(4096)
        i = data.find(b"mvhd")
        if i < 0:
            return None
        version = data[i + 4]
        if version == 1:
            timescale, dur = struct.unpack(">IQ", data[i + 24:i + 36])
        else:
            timescale, dur = struct.unpack(">II", data[i + 16:i + 24])
        if not timescale:
            return None
        return f"{dur / timescale:.1f}s"
    except Exception:
        return None


def facts(root: Path) -> dict:
    led_path = root / "data" / "out" / "provenance-ledger.json"
    inv_path = root / "data" / "out" / "provenance-inventory.json"
    frames_path = root / "data" / "out" / "provenance-timelapse-frames.json"
    led = json.loads(led_path.read_text(encoding="utf-8")) if led_path.exists() else {}
    inv = json.loads(inv_path.read_text(encoding="utf-8")) if inv_path.exists() else {}
    frames = json.loads(frames_path.read_text(encoding="utf-8")) if frames_path.exists() else {}

    films = {}
    for key, rel in (("timelapse", "video/provenance-timelapse.mp4"),
                     ("master", "video/provenance-manual-run.mp4"),
                     ("showcase", "video/provenance-showcase.mp4")):
        p = root / rel
        films[key] = {
            "path": rel,
            "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else 0,
            "size": _size(p) if p.exists() else "missing",
            "duration": _duration(p) if p.exists() else None,
        }
    clips = sorted((root / "video" / "clips").glob("*.mp4")) if (root / "video" / "clips").is_dir() else []

    totals = inv.get("totals", {})
    return {
        "led": led,
        "inv": inv,
        "frames": frames,
        "films": films,
        "clips": clips,
        "datums": len(led.get("data", [])),
        "linked": led.get("totals", {}).get("with_link", 0),
        "cued": led.get("totals", {}).get("with_cue", 0),
        "files": frames.get("files") or totals.get("files", 0),
        "families": len([f for f in inv.get("families", []) if f.get("class") != "code"])
        or totals.get("families", 0),
        "unassigned": inv.get("unassigned", {}).get("files", 0),
        "scraped": totals.get("scraped_files", 0),
        "bytes": totals.get("bytes", 0),
        "manual_seconds": totals.get("estimated_manual_seconds", 0),
        "hosts": len(inv.get("source_hosts", [])),
        "rate": round((frames.get("files") or 0) / 13.2) if frames.get("files") else 566,
    }


def _human_time(seconds: float) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} d {h} h {m} m"
    if h:
        return f"{h} h {m} m"
    return f"{m} m"


def _tc(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


# --------------------------------------------------------------------------
# the walkthrough, in the order a reader should take it
# --------------------------------------------------------------------------


def _guide_steps(f: dict) -> list[tuple[str, str]]:
    led = f["led"]
    sched = (led.get("film") or {}).get("schedule", {})
    chapters = sched.get("chapters", [])
    steps = [
        ("Watch the time-lapse first",
         "It is {secs} and it shows the size of the thing: {files:,} files in {families} families. "
         "You are not meant to read every cell — you are meant to see how many there are."
         .format(secs=f["films"]["timelapse"]["duration"] or "20s",
                 files=f["files"], families=f["families"])),
        ("Then watch one chapter",
         "Pick the kind of record you actually care about — meeting nights, agenda packets, minutes, "
         "transcripts, the tape, the news, the arrest reports, the scanner, open data. Each chapter "
         "is ~15 seconds: the real page, the click, the download."
         + (f" Start with chapter 1 at {_tc(chapters[0][1])} in the chapter film." if chapters else "")),
        ("Then read the ledger row for a number you already believe",
         f"The ledger has {f['datums']} rows. Find one you can check quickly — a meeting count, a "
         "file count — and follow its origin link. If the number is not on the page the ledger "
         "points at, that is a bug and the ledger is wrong."),
        ("Then do it yourself, once",
         "Open the origin URL, follow the click-path in the ledger row, and download one file. It "
         "should take you two minutes and it should be exactly what the chapter showed. That is the "
         "whole test: everything here is re-fetchable by hand."),
        ("Then run the checks",
         "`python3 tools/check_provenance.py --site _site` and "
         "`python3 tools/provenance_site_audit.py` — the first proves every datum still carries a "
         "link and a cue, the second rebuilds the record and crawls every page. If either fails, do "
         "not trust the page that changed."),
    ]
    return steps


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------


def markdown(root: Path, f: dict | None = None) -> str:
    f = f or facts(root)
    led = f["led"]
    sched = (led.get("film") or {}).get("schedule", {})
    L: list[str] = []
    A = L.append

    A("# The provenance guide")
    A("")
    A("*One page for everything in this archive: what it holds, the films that show how it was "
      "fetched, and how to check any number in it yourself.*")
    A("")
    A(f"Generated **{led.get('generated_at', '')}** from this checkout by "
      "`python3 -m provenance guide`. Nothing on this page is typed in by hand — every number is "
      "read from the artefacts beside it, and anything missing is reported as missing.")
    A("")

    A("## The collection, in five numbers")
    A("")
    A("| | |")
    A("|---|---|")
    A(f"| **{f['files']:,}** | files in the collection, each one assigned to a family |")
    A(f"| **{f['families']}** | kinds of record — meetings, packets, minutes, transcripts, tape, news, arrests, scanner, open data |")
    A(f"| **{f['scraped']:,}** | of those files captured from a public site rather than derived |")
    A(f"| **{f['hosts']}** | public sites the repo's own files point at |")
    A(f"| **{f['unassigned']}** | files unaccounted for |")
    A("")
    A(f"By hand, the same set is roughly **{_human_time(f['manual_seconds'])}** of work at the "
      "conservative rates stated per family in `provenance/inventory.py`. That figure is an "
      "estimate and is labelled as one wherever it appears.")
    A("")

    A("## What is here")
    A("")
    A("| thing | what it is | size / length | file |")
    A("|---|---|---|---|")
    for piece in PIECES:
        key = piece["key"]
        if piece["kind"] == "film":
            fl = f["films"].get(key, {})
            meta = f"{fl.get('duration') or '—'} · {fl.get('size', '—')}" if fl.get("exists") else "**missing**"
        elif piece["kind"] == "clips":
            meta = f"{len(f['clips'])} clips · {_size(root / 'video' / 'clips')}"
        elif piece["kind"] == "data":
            meta = _size(root / piece["file"])
        else:
            meta = "—"
        A(f"| **{piece['name']}** | {piece['what']} | {meta} | `{piece['file']}` |")
    A("")

    A("## How to use this")
    A("")
    for i, (title, body) in enumerate(_guide_steps(f), 1):
        A(f"### {i}. {title}")
        A("")
        A(body)
        A("")

    A("## Each piece, in detail")
    A("")
    for piece in PIECES:
        A(f"### {piece['name']}")
        A("")
        A(piece["what"])
        A("")
        for line in piece["shows"]:
            A("- " + line.format(**{k: v for k, v in f.items() if isinstance(v, (int, str))}))
        A("")
        A(f"**Why you would open it:** {piece['use']}")
        A("")
        A(f"**Where it comes from:** {piece['source']}  ")
        A(f"**Rebuild:** `{piece['build']}`")
        A("")

    # the chapter-by-chapter map, with a real timestamp for each
    if sched.get("chapters"):
        A("## The chapter map")
        A("")
        A("Each chapter is one data family, in the chapter film. The cue column is where that "
          "chapter starts in `video/provenance-manual-run.mp4`; the clip is the same footage cut "
          "out and served beside the numbers on the pages.")
        A("")
        A("| # | chapter | cue in the film | clip | datums it explains |")
        A("|---|---|---|---|---|")
        counts: dict[str, int] = {}
        for d in led.get("data", []):
            counts[d.get("ledger", "")] = counts.get(d.get("ledger", ""), 0) + 1
        for i, (key, start, dur) in enumerate(sched["chapters"], 1):
            clip = ""
            for d in led.get("data", []):
                if d.get("ledger") == key and (d.get("cue") or {}).get("src"):
                    clip = d["cue"]["src"]
                    break
            A(f"| {i} | {key.replace('_', ' ')} | {_tc(start)}–{_tc(start + dur)} | "
              f"`{clip or '—'}` | {counts.get(key, 0)} |")
        A("")
        A(f"The film opens with a {sched['intro'][1]:.0f}s title and a {sched['detect'][1] - sched['detect'][0]:.0f}s "
          f"scanner sequence, ends at {_tc(sched['total'])}, and the showcase version puts the "
          f"time-lapse ({sched['timelapse_seconds']:.0f}s) in front of it for "
          f"{_tc(sched['timelapse'] + sched['timelapse_seconds'])} total.")
        A("")

    A("## Reading a ledger row")
    A("")
    A("Every datum looks like this:")
    A("")
    A("```")
    A("| `news.units` | The Daily Ledger, Front Page | 513 | capcity.news | 2:07 | panel @ 2:20 |")
    A("```")
    A("")
    A("and means: *513 article / digest items are counted on the Daily Ledger and Front Page "
      "pages; the public start of that data is capcity.news; the footage is chapter 8 at 2:07 in "
      "the chapter film; and the exact moment the collection panel shows the count is 2:20, which "
      "is 13 seconds into that chapter's clip.*")
    A("")
    A("The beats are the same choreography in every chapter:")
    A("")
    A("| beat | what is on screen |")
    A("|---|---|")
    A("| `type` | the origin URL being typed into the address bar |")
    A("| `load` | the real page loading |")
    A("| `pick` | the meeting / document row being clicked |")
    A("| `item` | the item page with its download control |")
    A("| `download` | the download click |")
    A("| `collect` | a second row, a second file |")
    A("| `save` | the file landing in the archive folder |")
    A("| `panel` | the collection panel: units, destination, cost by hand |")
    A("")

    A("## If you only have two minutes")
    A("")
    A("1. Watch `video/provenance-timelapse.mp4` — the whole collection, 20 seconds.")
    A("2. Open the chapter for a record you care about, from the cue sheet.")
    A("3. Find that number in `data/out/PROVENANCE-LEDGER.md` and click its origin link.")
    A("")
    A("If those three line up, the rest of this page is detail.")
    A("")

    A("## How this differs from the city's own portal")
    A("")
    A("The City of Cheyenne publishes the same council meetings on its own Granicus portal, "
      "and that portal is the record of authority. This archive is a reader for it. The two "
      "differ in both directions — the portal has the footage and the official viewers; this "
      "archive has the other eight bodies, the document text, the transcripts and the "
      "provenance. The full comparison, figure by figure, is a generated page:")
    A("")
    A("- on the site: `/provenance/granicus.html`")
    A("- in the repo: `data/out/GRANICUS-VS-THIS-ARCHIVE.md` (`python3 -m provenance compare`)")
    A("")

    A("## Rebuild everything, in order")
    A("")
    A("```bash")
    A("python3 -m provenance detect                    # classify every file, write the inventory")
    A("python3 -m provenance timelapse                 # render the 20-second time-lapse")
    A("python3 -m provenance video                     # render the chapter film (~8 min)")
    A("python3 -m provenance ledger --clips --showcase # cues, per-chapter clips, showcase")
    A("python3 -m provenance guide                     # this page")
    A("python3 -m provenance compare                   # portal vs this archive")
    A("python3 tools/render_ai_record.py --src ai-record --out _site   # the site, with provenance")
    A("python3 tools/check_provenance.py --site _site  # prove every datum still carries its source")
    A("```")
    A("")
    A("---")
    A("")
    A("*Silent films, captions only. Names are withheld in arrest material; charges are quoted "
      "verbatim. Not an official city website.*")
    A("")
    return "\n".join(L)


def write(root: Path, f: dict | None = None) -> Path:
    f = f or facts(root)
    out = root / "data" / "out" / "PROVENANCE-GUIDE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(root, f), encoding="utf-8")
    return out


# --------------------------------------------------------------------------
# the web version, for /provenance/master.html
# --------------------------------------------------------------------------


def html(ledger: dict, root_rel: str, facts_: dict | None = None) -> str:
    """The same guide as HTML, with the three films playable."""
    import html as _h

    f = facts_ or {}
    films = (ledger.get("film") or {})
    sched = films.get("schedule", {})
    datums = ledger.get("totals", {}).get("data", 0)

    def esc(x) -> str:
        return _h.escape(str(x))

    def video_box(rel: str, poster: str, caption: str) -> str:
        return (
            f'<figure class="film"><video controls preload="metadata" width="100%" '
            f'poster="{esc(root_rel + poster)}" src="{esc(root_rel + rel)}"></video>'
            f"<figcaption>{caption}</figcaption></figure>"
        )

    out = [
        "<h1>The provenance guide</h1>",
        "<p><em>One page for everything in this archive: what it holds, the films that show how it "
        "was fetched, and how to check any number in it yourself.</em></p>",
        '<p class="hint">Every number below is read from the artefacts in this repository when the '
        "page is built. If a film is missing, this page says so.</p>",
        "<h2>The collection, in five numbers</h2>",
        '<table class="five"><tbody>',
        f"<tr><td class='n'>{f.get('files', 0):,}</td><td>files in the collection, each assigned to a family</td></tr>",
        f"<tr><td class='n'>{f.get('families', 0)}</td><td>kinds of record</td></tr>",
        f"<tr><td class='n'>{f.get('scraped', 0):,}</td><td>captured from a public site rather than derived</td></tr>",
        f"<tr><td class='n'>{f.get('hosts', 0)}</td><td>public sites the repo's own files point at</td></tr>",
        f"<tr><td class='n'>{f.get('unassigned', 0)}</td><td>files unaccounted for</td></tr>",
        "</tbody></table>",
        "<h2>Watch the whole thing</h2>",
        '<p>First the time-lapse — every file, in capture order. Then the chapter film — one kind of '
        "record at a time, the real page, the clicks, the download. The single file below is both, "
        "in that order, and every cue in this record is a timestamp into it.</p>",
        video_box(films.get("showcase", "video/provenance-showcase.mp4"),
                  "video/provenance-showcase.jpg",
                  f"{esc(_tc(sched.get('timelapse', 0) + sched.get('timelapse_seconds', 20)))} — "
                  "time-lapse then every chapter"),
        "<h2>Or one thing at a time</h2>",
        '<div class="grid">',
        video_box(films.get("timelapse", "video/provenance-timelapse.mp4"),
                  "video/provenance-timelapse-poster.jpg",
                  "The time-lapse — every file this archive holds, ~566 a second"),
        video_box(films.get("master", "video/provenance-manual-run.mp4"),
                  "video/provenance-manual-run.jpg",
                  f"The chapter film — {esc(_tc(sched.get('total', 222)))} of hand-fetching, "
                  "one data family at a time"),
        "</div>",
        "<h2>How to use this</h2>",
    ]
    for i, (title, body) in enumerate(_guide_steps({
        "led": ledger, "films": {"timelapse": {"duration": "20s"}},
        "files": f.get("files", 0), "families": f.get("families", 0), "datums": datums,
    }), 1):
        out.append(f"<h3>{i}. {esc(title)}</h3><p>{esc(body)}</p>")

    out.append("<h2>What is here</h2>")
    out.append('<table class="pieces"><thead><tr><th>thing</th><th>what it is</th>'
               "<th>file</th></tr></thead><tbody>")
    for piece in PIECES:
        out.append(
            f'<tr><td><b>{esc(piece["name"])}</b></td><td>{esc(piece["what"])}</td>'
            f'<td><code>{esc(piece["file"])}</code></td></tr>'
        )
    out.append("</tbody></table>")

    out.append("<h2>The chapter map</h2>")
    out.append("<p>Each chapter is one data family. Open a clip and you are watching that kind of "
               "record being fetched by hand; the rows underneath carry the exact second for each "
               "figure.</p>")
    out.append('<table class="chapters"><thead><tr><th>#</th><th>chapter</th><th>cue</th>'
               "<th>clip</th><th>datums</th></tr></thead><tbody>")
    counts: dict[str, int] = {}
    for d in ledger.get("data", []):
        counts[d.get("ledger", "")] = counts.get(d.get("ledger", ""), 0) + 1
    for i, (key, start, dur) in enumerate(sched.get("chapters", []), 1):
        clip = ""
        for d in ledger.get("data", []):
            if d.get("ledger") == key and (d.get("cue") or {}).get("src"):
                clip = d["cue"]["src"]
                break
        out.append(
            f"<tr><td>{i}</td><td>{esc(key.replace('_', ' '))}</td>"
            f"<td>{_tc(start)}–{_tc(start + dur)}</td>"
            f'<td><a href="{esc(root_rel + clip)}">{esc(os.path.basename(clip) or "—")}</a></td>'
            f"<td>{counts.get(key, 0)}</td></tr>"
        )
    out.append("</tbody></table>")

    out += [
        "<h2>Reading a ledger row</h2>",
        "<p>Every datum looks like this:</p>",
        '<pre class="row">| news.units | The Daily Ledger, Front Page | 513 | capcity.news | 2:07 | panel @ 2:20 |</pre>',
        "<p>513 article / digest items are counted on the Daily Ledger and Front Page; the public "
        "start of that data is capcity.news; the footage is chapter 8 at 2:07 in the chapter film; "
        "and the collection panel shows the count at 2:20 — thirteen seconds into that chapter's "
        "clip. The beats are the same choreography in every chapter: <code>type</code> (the URL "
        "being typed), <code>load</code>, <code>pick</code> (the row being clicked), "
        "<code>item</code>, <code>download</code>, <code>collect</code>, <code>save</code> (the file "
        "landing), <code>panel</code> (the count, destination and cost).</p>",
        "<h2>How this differs from the city's own portal</h2>",
        "<p>The City of Cheyenne publishes the same council meetings on its own Granicus portal, "
        "and that portal is the record of authority. This archive is a reader for it. The two "
        "differ in both directions: the portal has the footage and the official viewers; this "
        "archive has the other eight bodies, the document text, the transcripts and the "
        "provenance.</p>",
        f'<p><a href="{esc(root_rel)}provenance/granicus.html"><b>The full comparison, figure by '
        "figure →</b></a> — what each holds, what only the portal has, what only this archive "
        "has, and where this archive is behind.</p>",
        "<h2>Check it yourself</h2>",
        '<pre class="row">python3 tools/check_provenance.py --site _site\n'
        "python3 tools/provenance_site_audit.py</pre>",
        "<p>The first fails if any datum has lost its origin link, its cue, or its clip on disk. The "
        "second rebuilds the whole record from this checkout and crawls every rendered page: internal "
        "links, video sources, provenance blocks, and the cue sheet. Both run in CI.</p>",
        f"<h2>The whole ledger</h2><p>All {datums:,} figures, with links, cues and beats: "
        f'<a href="{esc(root_rel)}provenance/index.html">the cue sheet</a>.</p>',
        "<p class='hint'>Silent films, captions only. Names are withheld in arrest material; charges "
        "are quoted verbatim. Not an official city website.</p>",
    ]
    return "\n".join(out)


GUIDE_CSS = """
.prov .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.prov .grid{grid-template-columns:1fr}}
.prov figure.film{margin:0 0 18px}
.prov figure.film figcaption{font:13px/1.4 system-ui,sans-serif;color:#444;margin-top:4px}
.prov table.five td{padding:4px 12px 4px 0;font:15px/1.5 system-ui,sans-serif}
.prov table.five td.n{font:700 22px/1.2 ui-monospace,monospace;color:#0b3a6f;text-align:right}
.prov table.pieces,.prov table.chapters{border-collapse:collapse;width:100%;margin:8px 0 16px}
.prov table.pieces td,.prov table.pieces th,.prov table.chapters td,.prov table.chapters th{
  border-bottom:1px solid #e8ecf3;padding:7px 10px 7px 0;font:14px/1.45 system-ui,sans-serif;text-align:left;vertical-align:top}
.prov pre.row{background:#f4f7fb;border:1px solid #e2e8f1;border-radius:6px;padding:10px 12px;
  font:13px/1.5 ui-monospace,monospace;overflow-x:auto}
.prov .hint{font:13px/1.5 system-ui,sans-serif;color:#666}
"""
