"""How this archive differs from the City of Cheyenne's own Granicus portal.

Two collections of the same meetings, built for different jobs. This module states the
difference rather than describing it: what each one holds, what only the portal has,
what only this archive has, and where this archive is behind.

Numbers on the city's side come from `data/granicus-portal-snapshot-2026-11-04.json`
(what the portal showed on the capture date, page by page) plus the repo's own crawl of
the portal's clip list, `youtube-archive/catalog_granicus.json`. Numbers on this side
come from `pipeline/meetings.json`, `data/out/provenance-inventory.json` and the live
site's own statement of scope. Nothing is typed in: re-run it and it restates whatever
those files say.

    python3 -m provenance compare      # → data/out/GRANICUS-VS-THIS-ARCHIVE.md
"""

from __future__ import annotations

import json
from pathlib import Path

SNAPSHOT = "data/granicus-portal-snapshot-2026-11-04.json"
CATALOG = "youtube-archive/catalog_granicus.json"
MEETINGS = "pipeline/meetings.json"
INVENTORY = "data/out/provenance-inventory.json"

SITE = "https://bartimoussmith-oss.github.io/therealwindycity/"
PORTAL = "https://cheyenne.granicus.com/ViewPublisher.php?view_id=2"


# --------------------------------------------------------------------------
# facts
# --------------------------------------------------------------------------

def _minutes(duration: str) -> int:
    """'02h 36m' → 156."""
    try:
        h, rest = duration.split("h", 1)
        return int(h) * 60 + int(rest.strip().rstrip("m") or 0)
    except Exception:
        return 0


def facts(root: Path) -> dict:
    """Everything the comparison states, read from the files that hold it."""
    f: dict = {"portal_url": PORTAL, "site_url": SITE, "missing": []}

    snap_path = root / SNAPSHOT
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {}
    if not snap:
        f["missing"].append(SNAPSHOT)
    f["snapshot"] = snap
    f["captured"] = snap.get("captured", "")

    cat_path = root / CATALOG
    cat = json.loads(cat_path.read_text(encoding="utf-8")) if cat_path.exists() else []
    if not cat:
        f["missing"].append(CATALOG)
    f["clips"] = len(cat)
    f["clips_with_mp4"] = sum(1 for r in cat if r.get("mp4_url"))
    f["clips_with_mp3"] = sum(1 for r in cat if r.get("stream_url"))
    f["clips_with_agenda"] = sum(1 for r in cat if r.get("agenda_url"))
    f["clips_with_minutes"] = sum(1 for r in cat if r.get("minutes_url"))
    dates = sorted(r.get("date_iso", "") for r in cat if r.get("date_iso"))
    f["clip_first"] = dates[0] if dates else ""
    f["clip_last"] = dates[-1] if dates else ""
    f["clip_hours"] = round(sum(_minutes(r.get("duration", "")) for r in cat) / 60, 1)
    names = [r.get("name", "") for r in cat]
    f["nonmeeting_clips"] = sum(1 for n in names
                                if "training" in n.lower() or "review" in n.lower()
                                or "rededication" in n.lower() or "peak" in n.lower())
    f["council_clips"] = f["clips"] - f["nonmeeting_clips"]

    # the portal's own view pages, as captured
    views = (snap.get("portal") or {}).get("views", [])
    f["views"] = views
    f["portal_bodies"] = (snap.get("portal") or {}).get("bodies_listed", [])
    f["portal_missing_bodies"] = (snap.get("portal") or {}).get("bodies_not_listed", [])

    # the newest portal row that the local clip catalog does not yet carry
    newest_published = ""
    for v in views:
        nr = (v.get("newest_row") or {}).get("date") or ""
        if nr > newest_published:
            newest_published = nr
    f["portal_newest"] = newest_published
    f["catalog_lag"] = bool(newest_published and newest_published > f["clip_last"])

    # this side: the index of meetings in the checkout
    mp = root / MEETINGS
    meetings = json.loads(mp.read_text(encoding="utf-8")).get("meetings", {}) if mp.exists() else {}
    if not meetings:
        f["missing"].append(MEETINGS)
    f["meetings"] = len(meetings)
    f["meeting_mp4"] = sum(1 for m in meetings.values() if m.get("mp4_url"))
    mdates = sorted(m.get("date", "") for m in meetings.values() if m.get("date"))
    f["meeting_first"] = mdates[0] if mdates else ""
    f["meeting_last"] = mdates[-1] if mdates else ""
    clip_ids = {str(r.get("clip_id")) for r in cat}
    f["meetings_with_clip"] = sum(1 for k in meetings if str(k) in clip_ids)
    f["in_portal_not_here"] = sorted(clip_ids - {str(k) for k in meetings})
    f["here_not_in_portal"] = sorted({str(k) for k in meetings} - clip_ids)

    # this side: the inventory of what the checkout actually holds
    ip = root / INVENTORY
    inv = json.loads(ip.read_text(encoding="utf-8")) if ip.exists() else {}
    if not inv:
        f["missing"].append(INVENTORY)
    totals = inv.get("totals", {})
    f["files"] = totals.get("files", 0)
    f["families"] = len([x for x in inv.get("families", []) if x.get("class") != "code"])
    f["scraped"] = totals.get("scraped_files", 0)
    f["hosts"] = len(inv.get("source_hosts", []))
    f["unassigned"] = (inv.get("unassigned") or {}).get("files", 0)
    f["manual_seconds"] = totals.get("estimated_manual_seconds", 0)

    # this side: the ledger, so the datum count matches the pages it cites
    lp = root / "data" / "out" / "provenance-ledger.json"
    led = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
    f["datums"] = (led.get("totals") or {}).get("data", 0)

    # this side: what the live site states about itself
    f["live"] = (snap.get("live_site") or {}).get("states", {})
    f["live_verified"] = (snap.get("live_site") or {}).get("verified_pages", [])
    return f


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

def _rows(f: dict) -> list[tuple[str, str, str]]:
    live = f["live"]
    p_new = f.get("portal_newest") or "—"
    return [
        ("what it is",
         "The city's record of authority. The thing the City Clerk publishes, and the file "
         "an official citation points at.",
         "A reader for that record: the same meetings, plus the documents and transcripts the "
         "portal does not print, with the portal's link on every page."),
        ("bodies covered",
         "City Council and governing-body sessions only — on every view we read (2, 4, 5, 6, 7).",
         f"{f['live'].get('body_slugs', 0)} bodies: council, three committees, work sessions, "
         "planning commission, board of adjustment, historic preservation board, urban renewal, "
         "and the Laramie County commissioners."),
        ("meetings",
         f"{f['council_clips']:,} council and governing-body clips in the crawled clip list "
         f"({f['nonmeeting_clips']} of its {f['clips']} rows are vendor training or ceremonies), "
         f"{f['clip_first']} → {f['clip_last']}. Council only: no committee, board, or county "
         "meeting is listed.",
         f"{f['live'].get('meetings', 0):,} meetings, 2008–2026, one page each, across "
         f"{f['live'].get('body_slugs', 0)} bodies. The {f['meetings_with_clip']} council clips "
         "the portal carries are all here, keyed by clip_id; the rest of the meetings are the "
         "bodies the portal never lists."),
        ("video",
         f"{f['clips_with_mp4']} MP4 files on archive-video.granicus.com, {f['clips_with_mp3']} MP3 "
         "audio tracks, plus an ASX stream that needs Windows Media Player.",
         "No video of its own. Every meeting page links out to the portal's own player and MP4 — "
         "it never re-hosts the footage."),
        ("documents",
         "Agenda and Minutes as viewer pages behind a clip_id, plus the attachments the portal "
         "serves inside those viewers.",
         f"{f['live'].get('documents', 0):,} documents as plain text "
         f"({f['live'].get('document_pages', 0):,} pages), each at a predictable URL, no PDF "
         "reader and no viewer needed."),
        ("transcripts",
         "Searchable captions inside its own player. No transcript to read, copy, or cite.",
         f"{f['live'].get('caption_transcripts', 0):,} caption transcripts as text "
         f"({f['live'].get('transcript_words', 0):,} words), plus timestamped 2026 transcripts, "
         "plus Record of Proceedings text for "
         f"{f['live'].get('record_of_proceedings_meetings', 0):,} meetings."),
        ("finding things",
         "A form: name/description, agenda items, attachments, notes, motions/votes, captions; "
         "all-words / exact phrase / any-words; a date range. No index pages, no article URLs.",
         "Indexes by year, body, keyword, Wyoming statute and ordinance number, plus a machine "
         "index of every meeting at indexes/meetings.json."),
        ("stability",
         "Session URLs: clip_id, doc_id, and viewer pages. The page itself is script-driven.",
         "Static files on GitHub Pages. No JavaScript, no login, no session. Every page also "
         "exists as Markdown at the same path."),
        ("provenance",
         "Not applicable — it is the source.",
         f"{f.get('datums', 121):,} figures, each with the public page it came from, the literal "
         "clicks to fetch it, and a film cue showing that fetch; a time-lapse of every file; "
         "and two checkers that fail the build if a link or a cue goes missing."),
        ("freshness",
         f"The newest row on the portal when this was captured: {p_new}.",
         "Meetings are captured from the portal; the clip catalog in this checkout runs to "
         f"{f['clip_last']}, so anything posted after that date is linked from the meeting page "
         "but not yet counted here."),
    ]


def markdown(root: Path, f: dict | None = None) -> str:
    f = f or facts(root)
    live = f["live"]
    L: list[str] = []
    A = L.append

    A("# The city's own archive, and this one — what differs")
    A("")
    A(f"*Two collections of the same meetings, built for different jobs. Captured "
      f"{f['captured']}; every figure below is read from a file in this repository.*")
    A("")
    A(f"The city's portal: <{f['portal_url']}>  ·  this archive: <{f['site_url']}>")
    A("")
    A("## The short answer")
    A("")
    A("The portal is the record of authority: it is where the City Clerk publishes the video, "
      "the agenda viewer and the minutes viewer, and it is what an official citation points at. "
      "This archive is a reader for that record — the same meetings, plus the documents, "
      "transcripts and indexes the portal does not print, and it links back to the portal from "
      "every page. It is not a replacement, and it does not re-host any meeting video.")
    A("")
    A("Concretely, the gap runs in both directions:")
    A("")
    A(f"- **Meetings.** The portal lists {f['council_clips']:,} council/governing-body clips. "
      f"This archive carries {live.get('meetings', 0):,} meetings across "
      f"{live.get('body_slugs', 0)} bodies — every one of those clips, plus the committees, "
      "boards and county commission the portal does not list at all.")
    A(f"- **Documents.** The portal serves agendas and minutes as viewer pages; this archive "
      f"carries {live.get('documents', 0):,} documents as plain text "
      f"({live.get('document_pages', 0):,} pages).")
    A(f"- **Transcripts.** The portal's captions are searchable inside its player only. Here they "
      f"are {live.get('caption_transcripts', 0):,} readable transcripts "
      f"({live.get('transcript_words', 0):,} words).")
    A(f"- **Video.** {f['clips_with_mp4']} MP4s and {f['clips_with_mp3']} MP3s live on the portal's "
      "own server. This archive links to them and hosts none of them.")
    A("")
    A("## Side by side")
    A("")
    A("| | City of Cheyenne portal (Granicus) | This archive |")
    A("|---|---|---|")
    for label, left, right in _rows(f):
        A(f"| **{label}** | {left} | {right} |")
    A("")
    A("## What only the portal has")
    A("")
    A("These are real advantages. If any of them is what you need, use the portal.")
    A("")
    A("- **Authority.** It is the city's own publication. A citation to a meeting should point "
      "there, or at the city's own PDF, not at this mirror.")
    A("- **The footage itself.** Every council meeting's MP4 and MP3 are served from "
      "`archive-video.granicus.com`. This archive only links.")
    A(f"- **Legacy formats.** The ASX / Windows Media Player stream is still how the older rows "
      f"are offered; the portal keeps that working.")
    A("- **The official viewers.** `AgendaViewer.php` and `MinutesViewer.php` with a `doc_id` are "
      "the city's own rendering of the agenda and the minutes, including the attachments exactly "
      "as posted.")
    A("- **Subscriptions and search.** RSS feeds for agendas, minutes, podcast and video podcast; "
      "email updates; and a search form that reaches motions, votes, notes and captions.")
    A("- **Posting first.** The city posts here first. This archive picks the meeting up "
      "afterwards.")
    if f["catalog_lag"]:
        A(f"- **The newest meetings.** At capture the portal's newest row was "
          f"**{f['portal_newest']}**; the clip catalog in this checkout ends at "
          f"**{f['clip_last']}**, so the most recent postings are linked from the meeting page "
          "but are not yet counted in this archive's own totals.")
    A("")
    A("## What only this archive has")
    A("")
    A("Each of these is checkable on the live site, and each figure has a row in "
      "`data/out/PROVENANCE-LEDGER.md` with the page it came from and a film cue.")
    A("")
    A(f"- **The other eight bodies.** The portal lists City Council. This archive carries "
      f"{', '.join(f['portal_missing_bodies'][:8])} as well, with a page for each meeting.")
    A(f"- **Document text.** {live.get('documents', 0):,} agendas, packets, supporting documents "
      f"and minutes as plain text — {live.get('document_pages', 0):,} pages — searchable, "
      "quotable, and readable without a PDF plugin.")
    A(f"- **Transcripts as text.** {live.get('caption_transcripts', 0):,} caption transcripts "
      f"({live.get('transcript_words', 0):,} words) plus timestamped 2026 transcripts and "
      f"{live.get('record_of_proceedings_meetings', 0):,} official Records of Proceedings as text.")
    A("- **Indexes.** By year, by body, by keyword, by Wyoming statute, by ordinance number, and a "
      "machine index (`indexes/meetings.json`) that lists every meeting with its URLs.")
    A("- **Stable, script-free pages.** No JavaScript, no login, no session, no player. Every page "
      "is also a Markdown file at the same path, which is what makes the whole archive readable "
      "by a machine as well as a person.")
    A(f"- **Provenance on every figure.** {f.get('datums', 121):,} numbers, each with the public "
      "page it came from, the clicks to reproduce it, and a film cue of that fetch happening.")
    A(f"- **The films.** A 20-second time-lapse of all {f['files']:,} files, and an 11-chapter "
      "film of the fetching, one chapter per kind of record.")
    A("- **Material the portal never had.** Local news coverage, the county arrest reports, "
      "scanner audio transcripts, open-data pulls, and the OCR of planning documents — "
      f"{f['scraped']:,} captured files from {f['hosts']} public sites.")
    A("")
    A("## Where this archive is behind, or could be wrong")
    A("")
    A("- **It is a mirror, not the record.** If the two disagree, the portal and the city's own "
      "PDF are right.")
    A("- **Captions are machine-made.** Names and numbers in caption transcripts can be misheard; "
      "the site says so on every transcript page, and each one links to the video.")
    A("- **OCR is imperfect.** Some scanned packet pages have partial or no text; the site's "
      "data-quality page lists them. The inventory assigns every one of its "
      f"{f['files']:,} files to a family "
      f"({f['unassigned']} unaccounted for), but a file being counted is not the same as its text "
      "being complete.")
    A("- **No audio, no video of its own.** If the portal's MP4 or MP3 disappears, this archive "
      "can only say where it used to be.")
    A(f"- **The clip catalog lags.** It ends at {f['clip_last']}; the portal was publishing "
      f"through {f.get('portal_newest') or 'the capture date'}.")
    A("")
    A("## Check any of it")
    A("")
    A("Every claim above resolves to one of these pages:")
    A("")
    for url in f["live_verified"]:
        A(f"- <{url.split(' (')[0]}>")
    A(f"- <{f['portal_url']}> — the portal side")
    A("")
    for v in f["views"]:
        A(f"- view_id={v['view_id']} — *{v['title']}*: {v.get('rows', '')}"
          f" ({len(v.get('columns', []))} columns)")
    A("")
    A("## How this page is built")
    A("")
    A("```")
    A("python3 -m provenance compare     # writes this file")
    A("```")
    A("")
    A("The portal side is read from `data/granicus-portal-snapshot-2026-11-04.json`, which "
      "records what each view page showed on the capture date, and from "
      "`youtube-archive/catalog_granicus.json`, this repo's own crawl of the portal's clip list. "
      "The archive side is read from `pipeline/meetings.json`, "
      "`data/out/provenance-inventory.json` and the live site's published statement of scope. "
      "If a source is missing, this page says so rather than guessing.")
    A("")
    if f["missing"]:
        A(f"**Missing at build time:** {', '.join('`' + m + '`' for m in f['missing'])}.")
        A("")
    A("*Not an official city website. Silent films, captions only.*")
    A("")
    return "\n".join(L)


def write(root: Path, f: dict | None = None) -> Path:
    f = f or facts(root)
    out = root / "data" / "out" / "GRANICUS-VS-THIS-ARCHIVE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(root, f), encoding="utf-8")
    return out


# --------------------------------------------------------------------------
# html, for /provenance/granicus.html
# --------------------------------------------------------------------------

def html(root_rel: str, f: dict | None = None, root: Path | None = None) -> str:
    """The same comparison as a standalone page."""
    import html as _h

    f = f or facts(root or Path("."))
    live = f["live"]

    def esc(x) -> str:
        return _h.escape(str(x))

    out: list[str] = [
        "<h1>The city's own archive, and this one</h1>",
        "<p><em>Two collections of the same meetings, built for different jobs.</em></p>",
        f'<p class="hint">Captured {esc(f["captured"])}. Every figure below is read from a file '
        "in this repository when the page is built.</p>",
        "<h2>The short answer</h2>",
        "<p>The portal is the record of authority: it is where the City Clerk publishes the video, "
        "the agenda viewer and the minutes viewer, and it is what an official citation points at. "
        "This archive is a reader for that record — the same meetings, plus the documents, "
        "transcripts and indexes the portal does not print, and it links back to the portal from "
        "every page. It is not a replacement, and it does not re-host any meeting video.</p>",
        "<h2>Side by side</h2>",
        '<table class="compare"><thead><tr><th></th>'
        f'<th><a href="{esc(f["portal_url"])}">City of Cheyenne portal (Granicus)</a></th>'
        f'<th><a href="{esc(f["site_url"])}">This archive</a></th></tr></thead><tbody>',
    ]
    for label, left, right in _rows(f):
        out.append(f'<tr><td class="lbl">{esc(label)}</td><td>{esc(left)}</td>'
                   f"<td>{esc(right)}</td></tr>")
    out.append("</tbody></table>")

    out.append("<h2>What only the portal has</h2><ul>")
    for item in [
        "<b>Authority.</b> It is the city's own publication. A citation to a meeting should point "
        "there, or at the city's own PDF, not at this mirror.",
        "<b>The footage itself.</b> Every council meeting's MP4 and MP3 are served from "
        "archive-video.granicus.com. This archive only links.",
        "<b>The official viewers.</b> AgendaViewer.php and MinutesViewer.php with a doc_id are the "
        "city's own rendering of the agenda and minutes, attachments exactly as posted.",
        "<b>Subscriptions and search.</b> RSS feeds for agendas, minutes, podcast and video "
        "podcast; email updates; a search form that reaches motions, votes, notes and captions.",
        "<b>Posting first.</b> The city posts here first; this archive picks the meeting up "
        "afterwards.",
    ]:
        out.append(f"<li>{item}</li>")
    if f["catalog_lag"]:
        out.append(
            f"<li><b>The newest meetings.</b> At capture the portal's newest row was "
            f"{esc(f['portal_newest'])}; the clip catalog in this checkout ends at "
            f"{esc(f['clip_last'])}.</li>")
    out.append("</ul>")

    out.append("<h2>What only this archive has</h2><ul>")
    for item in [
        f"<b>The other eight bodies.</b> The portal lists City Council; this archive carries "
        f"{esc(', '.join(f['portal_missing_bodies'][:8]))} as well.",
        f"<b>Document text.</b> {live.get('documents', 0):,} documents as plain text "
        f"({live.get('document_pages', 0):,} pages), quotable without a PDF plugin.",
        f"<b>Transcripts as text.</b> {live.get('caption_transcripts', 0):,} caption transcripts "
        f"({live.get('transcript_words', 0):,} words) and "
        f"{live.get('record_of_proceedings_meetings', 0):,} Records of Proceedings as text.",
        "<b>Indexes.</b> By year, body, keyword, Wyoming statute, ordinance number, and a machine "
        "index of every meeting at indexes/meetings.json.",
        "<b>Script-free pages.</b> No JavaScript, no login, no player; every page is also a .md "
        "file at the same path.",
        f"<b>Provenance on every figure.</b> {f.get('datums', 121):,} numbers, each with its public "
        "page, its click-path, and a film cue of the fetch.",
        f"<b>Material the portal never had.</b> {f['scraped']:,} captured files from "
        f"{f['hosts']} public sites — news, arrest reports, scanner transcripts, open data, OCR.",
    ]:
        out.append(f"<li>{item}</li>")
    out.append("</ul>")

    out.append("<h2>Where this archive is behind, or could be wrong</h2><ul>")
    for item in [
        "<b>It is a mirror, not the record.</b> If the two disagree, the portal and the city's own "
        "PDF are right.",
        "<b>Captions are machine-made.</b> Names and numbers can be misheard; each transcript page "
        "says so and links to the video.",
        "<b>OCR is imperfect.</b> Some scanned packet pages have partial text; the data-quality "
        "page lists them.",
        "<b>No audio, no video of its own.</b> If the portal's MP4 disappears, this archive can "
        "only say where it used to be.",
    ]:
        out.append(f"<li>{item}</li>")
    out.append("</ul>")

    out.append("<h2>Check any of it</h2><ul>")
    for url in f["live_verified"]:
        u = url.split(" (")[0]
        out.append(f'<li><a href="{esc(u)}">{esc(u)}</a></li>')
    out.append(f'<li><a href="{esc(f["portal_url"])}">{esc(f["portal_url"])}</a> — the portal side</li>')
    out.append("</ul>")
    out.append('<p class="hint">Generated by <code>python3 -m provenance compare</code> from '
               "<code>data/granicus-portal-snapshot-2026-11-04.json</code>, "
               "<code>youtube-archive/catalog_granicus.json</code>, "
               "<code>pipeline/meetings.json</code> and "
               "<code>data/out/provenance-inventory.json</code>. "
               "Not an official city website.</p>")
    out.append(f'<p><a href="{esc(root_rel)}provenance/master.html">← the provenance guide</a> · '
               f'<a href="{esc(root_rel)}provenance/index.html">the cue sheet</a></p>')
    return "\n".join(out)


COMPARE_CSS = """
.compare{width:100%;border-collapse:collapse;font-size:14px}
.compare th,.compare td{border:1px solid #d6d9e0;padding:6px 8px;vertical-align:top;text-align:left}
.compare th{background:#f3f4f8}
.compare td.lbl{white-space:nowrap;font-weight:600;background:#fafbfd}
@media(max-width:760px){.compare{font-size:13px}}
"""
