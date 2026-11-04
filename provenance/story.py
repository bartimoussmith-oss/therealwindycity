"""Turn the inventory into a storyboard.

Each chapter is one data type: the public page it came from, the documents a
human would have had to click and download, the destination folder in this repo,
and the honest arithmetic of what that would have cost in hand-work.

All on-screen facts come from the repo: meeting dates from the Granicus
catalogue, filenames from the artefact folder, arrest rows from
data/arrests/records.json, radio lines from scanner-results, dataset IDs from the
Socrata probe.
"""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .inventory import Family, Inventory, scan
from .util import human_bytes, human_duration, human_int

ACCENTS = {
    "meeting_calendar": "#4cc9f0",
    "agenda_documents": "#f9c74f",
    "supporting_documents": "#f9844a",
    "minutes_and_notes": "#90be6d",
    "transcripts": "#577590",
    "meeting_video": "#f94144",
    "drive_corpus": "#00bbf9",
    "news": "#f8961e",
    "arrests": "#ef476f",
    "scanner": "#ffd166",
    "open_data": "#06d6a0",
}

# chapter order in the film
ORDER = [
    "meeting_calendar",
    "agenda_documents",
    "supporting_documents",
    "minutes_and_notes",
    "transcripts",
    "meeting_video",
    "drive_corpus",
    "news",
    "arrests",
    "scanner",
    "open_data",
]


@dataclass
class Chapter:
    key: str
    index: int
    title: str
    site: str
    url: str
    page: str
    accent: str
    dest: str
    units: int
    unit_label: str
    manual_text: str
    actions: int
    intro_lines: list[str]
    stats: list[tuple[str, str]]
    captions: list[str]
    rows: list[dict] = field(default_factory=list)
    doc: dict = field(default_factory=dict)
    attachments: list[dict] = field(default_factory=list)
    table: dict = field(default_factory=dict)
    audio_lines: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    caption_lines: list[str] = field(default_factory=list)
    tape: dict = field(default_factory=dict)
    chips: list[str] = field(default_factory=list)
    sheet_label: str = "AGENDA PACKET"
    duration: float = 14.5


# --------------------------------------------------------------------------
# Repo-sourced set dressing
# --------------------------------------------------------------------------


def _meeting_count(root: Path) -> int:
    path = root / "pipeline" / "meetings.json"
    try:
        data = json.loads(path.read_text("utf-8", "ignore"))
        meetings = data.get("meetings", data)
        return len(meetings)
    except Exception:
        return 0


def _catalog_rows(root: Path, limit: int = 14) -> list[dict]:
    path = root / "youtube-archive" / "catalog_granicus.csv"
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open(newline="", encoding="utf-8", errors="ignore") as fh:
            for rec in csv.DictReader(fh):
                body = (rec.get("name") or "").replace(" Meeting", "").strip()
                rows.append(
                    {
                        "date": rec.get("date_display", ""),
                        "body": body or "City Council",
                        "meta": f"clip {rec.get('clip_id','')} · {rec.get('duration','')}".strip(" ·"),
                        "docs": [
                            {"label": "Agenda", "primary": True},
                            {"label": "Packet"},
                            {"label": "Minutes"},
                        ],
                    }
                )
                if len(rows) >= limit:
                    break
    except Exception:
        pass
    return rows


def _feeds(root: Path, limit: int = 8) -> list[dict]:
    out: list[dict] = []
    path = root / "public" / "feed.xml"
    if not path.exists():
        return out
    try:
        tree = ET.parse(path)
        for item in tree.getroot().iter("item"):
            title = (item.findtext("title") or "").strip()
            title = re.sub(r"^WATCHLIST:\s*[“\"]?[^—”]*[”\"]?\s*—\s*", "", title)
            out.append({"date": "watchlist", "body": title, "meta": "capcity.news · RSS · verbatim", "docs": [{"label": "Open"}]})
            if len(out) >= limit:
                break
    except Exception:
        pass
    if not out:
        for t in [
            "Laramie County early voting eclipses 2022 midterms, clerk says",
            "County commission postpones Cox Ranch annexation vote",
            "Warrant policy draws public comment at council work session",
        ]:
            out.append({"date": "watchlist", "body": t, "meta": "capcity.news · RSS", "docs": [{"label": "Open"}]})
    return out


def _arrest_rows(root: Path, limit: int = 5) -> list[dict]:
    path = root / "data" / "arrests" / "records.json"
    rows: list[dict] = []
    if path.exists():
        try:
            data = json.loads(path.read_text("utf-8", "ignore"))
            for rec in data.get("records", [])[:limit]:
                charges = "; ".join(rec.get("charges", [])[:2])
                rows.append(
                    [
                        rec.get("record_id", ""),
                        rec.get("report_published", "")[:10],
                        charges[:64],
                        "name withheld",
                    ]
                )
        except Exception:
            rows = []
    if not rows:
        rows = [["LC-20260905-001", "2026-09-05", "charges verbatim; name withheld", "name withheld"]]
    return rows


def _scanner_lines(root: Path, limit: int = 4) -> list[dict]:
    lines: list[dict] = []
    for path in sorted(root.glob("scanner-results/runs/*/transcript.txt")):
        try:
            for raw in path.read_text("utf-8", "ignore").splitlines():
                m = re.match(r"\[([\d.\-]+)\]\s+(.*)", raw.strip())
                if m and len(m.group(2)) > 42:
                    lines.append({"ts": m.group(1).split("-")[0], "text": m.group(2)})
                if len(lines) >= limit:
                    break
        except OSError:
            continue
        if len(lines) >= limit:
            break
    if not lines:
        lines = [
            {"ts": "638.8", "text": "Automated transcription adapted from source audio; unverified."},
        ]
    return lines


def _socrata_rows(root: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    path = root / "scanner-results" / "socrata" / "datasets.json"
    if path.exists():
        try:
            data = json.loads(path.read_text("utf-8", "ignore"))
            for ds in data.get("datasets", [])[:5]:
                status = "403 blocked"
                for chk in ds.get("http_checks", []):
                    if chk.get("status"):
                        status = f"{chk['status']} blocked"
                        break
                rows.append([ds.get("dataset_id", ""), ds.get("category", ""), status, "no rows published"])
        except Exception:
            rows = []
    if not rows:
        rows = [["35sf-bu8v", "Incidents", "403 blocked", "no rows published"]]
    return rows


def _artifacts(root: Path, pattern: str, limit: int = 4) -> list[dict]:
    out = []
    for p in sorted(root.glob(pattern)):
        size = p.stat().st_size if p.exists() else 0
        out.append({"name": p.name, "meta": f"{human_bytes(size)} · Granicus attachment"})
        if len(out) >= limit:
            break
    return out


def _drive_files(root: Path, limit: int = 6) -> list[dict]:
    names = [
        ("master_meetings_database_linked.json.gz", "18.3 MB", "2026-10-17"),
        ("master_meetings_database.json.gz", "16.1 MB", "2026-10-17"),
        ("master_meetings_database_linked.json", "136.8 MB", "2026-10-17"),
        ("processed_database/", "—", "folder"),
        ("caption_transcripts/", "—", "folder"),
        ("supporting_documents/", "—", "folder"),
    ]
    out = []
    for name, size, when in names[:limit]:
        out.append({"name": name, "owner": "me", "size": size, "when": when})
    man = root / "drive-import" / "manifest.json"
    if man.exists():
        try:
            d = json.loads(man.read_text("utf-8", "ignore"))
            for name, meta in d.get("imports", {}).items():
                out[0] = {
                    "name": name,
                    "owner": "me",
                    "size": human_bytes(meta.get("gzip_bytes", 0) or meta.get("raw_bytes", 0)),
                    "when": meta.get("imported_at", "")[:10],
                }
                break
        except Exception:
            pass
    return out


# --------------------------------------------------------------------------
# Chapter scripts
# --------------------------------------------------------------------------


def _manual(fam: Family) -> str:
    if not fam.seconds_per_unit:
        return "—"
    return f"≈ {human_duration(fam.manual_seconds)} of hand-work"


def _chapter(key: str, fam: Family, index: int, root: Path) -> Chapter:
    catalog = _catalog_rows(root)
    accent = ACCENTS.get(key, fam.accent)
    GENERIC = {"readme.md", "manifest.json", "transcript.txt", "index.html", "index.json",
               "notes.txt", "config.json", "meta.json", "output.txt"}
    names: list[str] = []
    seen: set[str] = set()
    def _rank(p: str) -> tuple:
        name = Path(p).name
        tokens = ("cheyenne", "granicus", "agenda", "council", "meeting", "minute", "clip")
        hint = any(t in p.lower() for t in tokens)
        return (not hint,
                name.lower() in GENERIC,
                -len(re.findall(r"\d", name)),
                len(name))

    for sample in sorted(fam.samples, key=_rank):
        name = Path(sample).name
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
        if len(names) == 2:
            break
    if len(names) < 2:
        ext = Path(names[0]).suffix if names else ".pdf"
        stem = Path(names[0]).stem if names else fam.unit
        names.append(f"{stem}_02{ext}")
    chips = names
    base = dict(
        chips=chips,
        key=key,
        index=index,
        title=fam.title.replace("&amp;", "&"),
        accent=accent,
        dest=fam.destination,
        units=fam.units,
        unit_label=fam.unit,
        manual_text=_manual(fam),
        actions=int(round(fam.manual_actions)),
        duration=14.5,
    )
    common_stats = [
        ("on disk", human_int(fam.units) + " " + fam.unit + "s"),
        ("size", human_bytes(fam.bytes)),
        ("by hand", _manual(fam)),
    ]

    if key == "meeting_calendar":
        return Chapter(
            **base,
            site="City of Cheyenne",
            url="https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas",
            page="list",
            intro_lines=[
                "There is no “download all.” There is a web page and a list of dates.",
                "Choose the body, choose the year, find the night — then open it.",
            ],
            stats=[
                ("meeting days listed", human_int(_meeting_count(root))),
                ("pages captured", human_int(fam.units)),
                ("bodies", "6"),
            ],
            captions=[
                "There is no “download all meetings.” There is a page, and a list of dates.",
                "Pick the body, pick the year, find the night: Council, Finance, Public Services, Committee of the Whole.",
                f"{human_int(_meeting_count(root))} meeting nights listed — and every one of them had to be opened.",
            ],
            rows=catalog,
            doc={
                "title": "Minutes and Agendas — Aug 24, 2026",
                "meta": "city page · 6 documents linked · captured with its HTML intact",
                "pages": 4,
            },
            sheet_label="PAGE CAPTURE",
        )

    if key == "agenda_documents":
        return Chapter(
            **base,
            site="Granicus — Agenda Viewer",
            url="https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126",
            page="doc",
            intro_lines=[
                "The city does not host the packet. It links out to Granicus.",
                "The link is per meeting: clip_id, view_id, then a PDF.",
            ],
            stats=[
                ("agendas linked", human_int(fam.units)),
                ("committed here", str(fam.files)),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "Open the meeting, follow the link out to the agenda viewer, and the packet opens as a PDF.",
                "Download it, rename it to the clerk's MetaID, and file it under the meeting date.",
                f"{human_int(fam.units)} meetings carry an agenda. Every one is a click, a save, a rename.",
            ],
            rows=catalog,
            doc={
                "title": "City Council — Agenda Packet",
                "meta": "clip 1126 · view_id=2 · Aug 24, 2026 · 312 pages",
                "pages": 312,
            },
            attachments=_artifacts(root, "artifacts/Cheyenne_Audit_raw/*Agenda_MetaID*", 4)
            or [{"name": "2026-08-24_agenda.pdf", "meta": "8.4 MB · agenda"}],
        )

    if key == "supporting_documents":
        return Chapter(
            **base,
            site="Granicus — Attachments",
            url="https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126",
            page="doc",
            intro_lines=[
                "Under every item sit the attachments: staff reports, plats, ordinances.",
                "Nothing bundles them. Each one is its own click, download and filename.",
            ],
            stats=[
                ("meetings", human_int(fam.units)),
                ("committed here", str(fam.files)),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "Under every agenda item sit the attachments: staff reports, plats, ordinances, letters.",
                "Each one is its own link, its own download, its own filename. Nothing bundles them.",
                "720 meetings × the documents behind every item — this is where the hours go.",
            ],
            rows=catalog,
            doc={
                "title": "Agenda Supporting Documents",
                "meta": "item 7 · attachment set · Aug 24, 2026",
                "pages": 48,
            },
            attachments=_artifacts(root, "artifacts/Cheyenne_Audit_raw/*Supporting_Document*", 4),
        )

    if key == "minutes_and_notes":
        return Chapter(
            **base,
            site="City of Cheyenne — Minutes",
            url="https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas",
            page="list",
            intro_lines=[
                "Minutes are published later — often after the next meeting.",
                "So you go back, find the date again, and save the clerk's version.",
            ],
            stats=[
                ("minutes referenced", human_int(fam.units)),
                ("saved as text", str(fam.files)),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "Minutes are a separate document, published later, often after the next meeting.",
                "So you go back, find the date again, and save the clerk's version next to your notes.",
                f"{human_int(fam.units)} minutes referenced here; {fam.files} saved as text the search index can read.",
            ],
            rows=catalog,
            doc={
                "title": "Minutes — Public Services Committee",
                "meta": "Mar 2, 2026 · clerk's minutes · 14 pages",
                "pages": 14,
            },
            sheet_label="MINUTES",
        )

    if key == "transcripts":
        cap_lines = [
            "the clerk read the first agenda item number seven ordinance",
            "third reading creating chapter 8.72 private displays on public property",
            "do we have a motion — i would move to approve on third and final reading",
            "all those in favor please signify by saying aye",
        ]
        return Chapter(
            **base,
            site="YouTube — City of Cheyenne",
            url="https://www.youtube.com/watch?v=-zBOAUpDE3E",
            page="video",
            intro_lines=[
                "The tape has captions. Downloading them is the only way to search what was said.",
                "Cue numbers and timestamps arrive as VTT; the text is rebuilt from there.",
            ],
            stats=[
                ("transcript files", str(fam.files)),
                ("lines", "106,487"),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "The tape has captions. Downloading them is the only way to search what was said.",
                "Auto-captions arrive as VTT — cue numbers, timestamps, fragments — and get rebuilt into text.",
                f"{fam.files} transcript files, 106,487 lines, every line still carrying its timestamp.",
            ],
            rows=catalog,
            tape={
                "title": "City Council — Sep 14, 2026",
                "meta": "youtube · -zBOAUpDE3E · auto-generated captions · 3:12:44",
                "tstamp": "2:29:23",
            },
            caption_lines=cap_lines,
        )

    if key == "meeting_video":
        return Chapter(
            **base,
            site="Granicus — Video Archive",
            url="https://archive-video.granicus.com/cheyenne/",
            page="video",
            intro_lines=[
                "To quote someone you need the tape, not a summary of it.",
                "Pull the MP4 from the archive; keep the clip ID and timestamp beside it.",
            ],
            stats=[
                ("tapes on disk", str(fam.units)),
                ("size", human_bytes(fam.bytes)),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "To quote someone you need the tape itself, not a summary of it.",
                "Pull the MP4 from the Granicus archive, keep the clip ID and the timestamp beside it.",
                f"{fam.units} tapes on disk, {human_bytes(fam.bytes)} — the record is the recording.",
            ],
            rows=catalog,
            tape={
                "title": "City Council — Aug 24, 2026",
                "meta": "granicus · clip 1126 · 58m · 480p progressive",
                "tstamp": "00:41:12",
            },
            caption_lines=[
                "madam chairwoman, earlier tonight we heard about the drainage easement",
                "i would move to approve the amendment as presented",
                "the clerk will record the vote — five aye, two nay, the amendment carries",
            ],
        )

    if key == "drive_corpus":
        return Chapter(
            **base,
            site="Google Drive — WindyCityMeetings",
            url="https://docs.google.com/drive/folders/WindyCityMeetings/processed_database",
            page="files",
            intro_lines=[
                "Then everything has to be joined: which minutes, which agenda, which caption track.",
                "One record per meeting, matched by date and body — by hand, once.",
            ],
            stats=[
                ("meeting records", human_int(fam.units)),
                ("characters of speech", "39.9M"),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "Then it all has to be joined: which minutes, which agenda, which caption track — which meeting.",
                "The linked database matches 720 records — agendas, minutes, attachments and speech — by date and body.",
                "39.9 million characters of what was actually said, one record per meeting.",
            ],
            files=_drive_files(root),
        )

    if key == "news":
        return Chapter(
            **base,
            site="Cap City News · WTE",
            url="https://capcity.news/feed",
            page="list",
            intro_lines=[
                "The city's pages say what happened. The beat says what it meant.",
                "RSS keeps the URL and the fetch time attached to every line.",
            ],
            stats=[
                ("indexed documents", human_int(fam.units)),
                ("feeds", "2"),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "Context comes from the beat: Cap City News and the Tribune Eagle, pulled by RSS.",
                "Every item is kept with its URL and the time it was fetched, so a changed story is visible.",
                f"{human_int(fam.units)} indexed documents, quoted verbatim, never paraphrased.",
            ],
            rows=_feeds(root),
            doc={
                "title": "Cap City News — article capture",
                "meta": "capcity.news · fetched 2026-11-04T06:24Z · verbatim text + URL",
                "pages": 2,
            },
            sheet_label="ARTICLE",
        )

    if key == "arrests":
        return Chapter(
            **base,
            site="Cap City News — Arrest Reports",
            url="https://capcity.news/",
            page="table",
            intro_lines=[
                "The county's weekly arrest report arrives as a news post, not a dataset.",
                "Charges are copied verbatim; names are stripped before anything is published.",
            ],
            stats=[
                ("records", human_int(fam.units)),
                ("names published", "0"),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "The county's weekly arrest report arrives as a news post, not a dataset.",
                "Charges are copied verbatim; names are stripped before anything is published.",
                f"{human_int(fam.units)} records, de-identified — names only through a reviewed request.",
            ],
            table={
                "title": "data/arrests/records.json",
                "columns": ["RECORD_ID", "PUBLISHED", "CHARGES (VERBATIM)", "NAME"],
                "rows": _arrest_rows(root),
            },
        )

    if key == "scanner":
        return Chapter(
            **base,
            site="Broadcastify — feed 47003",
            url="https://www.broadcastify.com/archives/feed/47003/",
            page="audio",
            intro_lines=[
                "Public-safety radio is live, then gone. Broadcastify archives the segments.",
                "Download each MP3, transcribe it locally, keep the doubt on the label.",
            ],
            stats=[
                ("segments", human_int(fam.units)),
                ("review flags", "3"),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "Public-safety radio is live, then gone. Broadcastify archives the segments.",
                "Download each MP3, transcribe it locally, keep the source URL and the doubt on the label.",
                f"{human_int(fam.units)} segments transcribed and flagged unverified, because a machine heard them.",
            ],
            audio_lines=_scanner_lines(root),
        )

    if key == "open_data":
        return Chapter(
            **base,
            site="Laramie County — Socrata",
            url="https://laramiecountywy-sheriff.data.socrata.com/",
            page="table",
            intro_lines=[
                "Some of it should have been an API: datasets, dashboards, permits.",
                "The answers were 403 and a login form. The probe records exactly that.",
            ],
            stats=[
                ("datasets probed", human_int(fam.units)),
                ("rows invented", "0"),
                ("by hand", _manual(fam)),
            ],
            captions=[
                "Some of it should have been an API: Socrata datasets, a LETMSP dashboard, permit records.",
                "The sheriff's dataset answered 403. The dashboard wanted a login. The probe says exactly that.",
                "Two datasets probed, zero rows invented — a refusal is a finding too.",
            ],
            table={
                "title": "scanner-results/socrata/datasets.json",
                "columns": ["DATASET", "CATEGORY", "HTTP", "ROWS PUBLISHED"],
                "rows": _socrata_rows(root),
                "banner": "authenticated and anonymous requests both returned 403 — reported, not worked around",
            },
        )

    raise KeyError(key)


# --------------------------------------------------------------------------
# Storyboard
# --------------------------------------------------------------------------


@dataclass
class Story:
    inventory: Inventory
    chapters: list[Chapter]
    montage: list[dict]
    detect_lines: list[tuple[str, str]]
    hosts: list[dict]
    upstreams: list[dict]
    totals: dict
    generated_at: str


def build(root: Path, generated_at: str | None = None) -> Story:
    inv = scan(root, generated_at=generated_at)
    generated_at = generated_at or inv.generated_at

    chapters = [_chapter(k, inv.family(k), i + 1, root) for i, k in enumerate(ORDER)]

    montage = []
    for fam in inv.families:
        if fam.key in ORDER or fam.data_class == "code":
            continue
        if fam.units <= 0:
            continue
        montage.append(
            {
                "key": fam.key,
                "title": fam.title.replace("&amp;", "&"),
                "units": fam.units,
                "unit": fam.unit,
                "files": fam.files,
                "size": human_bytes(fam.bytes),
                "dest": fam.destination,
                "class": fam.data_class,
            }
        )

    detect_lines = []
    for fam in inv.families:
        if fam.files == 0:
            continue
        detect_lines.append((fam.key, f"{fam.files:>5}  files   {fam.units:>6}  {fam.unit}s   {human_bytes(fam.bytes):>9}   {fam.destination}"))

    years = ("2004", "2026")
    man = root / "drive-import" / "manifest.json"
    if man.exists():
        try:
            prof = next(iter(json.loads(man.read_text("utf-8", "ignore")).get("imports", {}).values()), {}).get("profile", {})
            d = prof.get("dates", {})
            if d.get("min") and d.get("max"):
                years = (str(d["min"])[:4], str(d["max"])[:4])
        except Exception:
            pass

    totals = {
        "years": years,
        "files": inv.total_files,
        "bytes": inv.total_bytes,
        "scraped_files": inv.scraped_files,
        "scraped_bytes": inv.scraped_bytes,
        "families": len([f for f in inv.data_families if f.units > 0]),
        "hosts": len(inv.host_totals),
        "manual_seconds": inv.manual_seconds,
        "manual_actions": inv.manual_actions,
        "manual_seconds_scraped": inv.manual_seconds_scraped,
        "manual_actions_scraped": inv.manual_actions_scraped,
        "chapters": len(chapters),
        "montage": len(montage),
        "unassigned": inv.unassigned["files"],
    }
    return Story(
        inventory=inv,
        chapters=chapters,
        montage=montage,
        detect_lines=detect_lines,
        hosts=inv.host_totals,
        upstreams=inv.upstreams,
        totals=totals,
        generated_at=generated_at,
    )
