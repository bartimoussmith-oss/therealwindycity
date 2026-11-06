"""Where the data actually came from.

Two jobs:

1. `HOSTS` — a small curated catalogue of the public-facing sites this archive
   pulls from, with the human-readable name shown on screen in the film.
2. `scan_urls()` — walks the files that belong to a data family, pulls every
   absolute URL out of them, and counts hosts. That is the *evidence*: a host is
   only credited with being an origin if it appears in the repo's own files.

Nothing here reaches the network. The inventory is derived entirely from what is
already on disk.
"""

from __future__ import annotations

import collections
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s\"'<>)\]}`,;]+", re.IGNORECASE)

# host -> (display name, short kind, note)
HOSTS: dict[str, tuple[str, str, str]] = {
    "www.cheyennecity.org": (
        "City of Cheyenne",
        "OpenCities CMS",
        "Agenda/minutes listings, news releases, clerk notices.",
    ),
    "cheyennecity.org": (
        "City of Cheyenne",
        "OpenCities CMS",
        "Agenda/minutes listings, news releases, clerk notices.",
    ),
    "cheyenne.granicus.com": (
        "Granicus — Cheyenne",
        "meeting portal",
        "Clip pages and AgendaViewer; the packets/minutes PDFs the city links to.",
    ),
    "archive-video.granicus.com": (
        "Granicus video archive",
        "media origin",
        "The MP4 renditions of each meeting.",
    ),
    "archive-stream.granicus.com": (
        "Granicus stream archive",
        "media origin",
        "HLS playlists for the same meetings.",
    ),
    "www.youtube.com": (
        "YouTube — City of Cheyenne",
        "video platform",
        "Meeting tapes and their auto-generated captions.",
    ),
    "youtu.be": ("YouTube", "video platform", "Short links to the meeting tapes."),
    "archive.org": (
        "Internet Archive",
        "public archive",
        "cochwy-* city media items and metadata.",
    ),
    "capcity.news": (
        "Cap City News",
        "local news",
        "The beat reporter on warrants, moratorium, referendum, Latigo, arrests.",
    ),
    "www.wyomingnews.com": (
        "Wyoming Tribune Eagle",
        "local news",
        "TownNews search-RSS feed.",
    ),
    "www.broadcastify.com": (
        "Broadcastify",
        "scanner audio",
        "Feed 47003 — Laramie County public-safety radio archive.",
    ),
    "audio.broadcastify.com": (
        "Broadcastify audio",
        "scanner audio",
        "The archived MP3 segments themselves.",
    ),
    "laramiecountywy-sheriff.data.socrata.com": (
        "Laramie County Sheriff — Socrata",
        "open data portal",
        "Incidents and cases datasets; the API answered 403 to this project.",
    ),
    "laramiecounty-letmsp.connect.socrata.com": (
        "Laramie County LETMSP (Socrata)",
        "records dashboard",
        "Tyler/LETMSP incident dashboard behind a login.",
    ),
    "cheyennewy.workflow.opengov.com": (
        "OpenGov — Cheyenne",
        "permitting / records",
        "Permit and case records for annexation and zoning filings.",
    ),
    "www.laramiecountywy.gov": (
        "Laramie County",
        "county site",
        "Commissioners' agendas (path unverified — left disabled).",
    ),
    "www.cheyennebopu.org": (
        "Cheyenne BOPU",
        "utility board",
        "Board minutes and the fill-and-flush discharge policy.",
    ),
    "www.plancheyenne.org": (
        "PlanCheyenne",
        "planning",
        "Comprehensive plan and zoning source documents.",
    ),
    "docs.google.com": (
        "Google Drive",
        "working corpus",
        "The WindyCityMeetings processed database (720 caption transcripts).",
    ),
    "drive.google.com": (
        "Google Drive",
        "working corpus",
        "Shared source files behind the meetings database.",
    ),
    "sos.wyo.gov": ("Wyoming Secretary of State", "state records", "Business entity filings."),
    "wyobiz.wyo.gov": ("WyoBiz", "state records", "Registered-agent / entity lookups."),
    "law.justia.com": ("Justia", "case law", "Wyoming statutes and decisions cited in filings."),
    "edocket.access.gpo.gov": ("GPO eDocket", "federal records", "Federal register citations."),
    "www.sam.gov": ("SAM.gov", "federal records", "Contractor registrations."),
    "github.com": ("GitHub", "the archive itself", "The six sibling repos that hold the raw pulls."),
    "bartimoussmith-oss.github.io": (
        "Published AI-readable record",
        "this site",
        "The static mirror built from everything above.",
    ),
}

# Hosts that are page furniture, not data origins.
NOISE_HOSTS = {
    "w3.org",
    "www.w3.org",
    "schema.org",
    "example.invalid",
    "localhost",
    "127.0.0.1",
    "creativecommons.org",
    "github.com",
    "raw.githubusercontent.com",
    "bartimoussmith-oss.github.io",
    "i0.wp.com",
    "s0.wp.com",
    "s.w.org",
    "yoast.com",
    "csp.withgoogle.com",
    "s.go-mpulse.net",
    "s2.go-mpulse.net",
    "ad.broadstreetads.com",
    "www.novapdf.com",
    "restream.io",
    "bit.ly",
    "microsoft.com",
    "www.microsoft.com",
    "investor.darden.com",
    "www.surveymonkey.com",
    "fonts.googleapis.com",
    "cdn.jsdelivr.net",
    "platform.twitter.com",
    "bloximages.chicago2.vip.townnews.com",
    "c0.wp.com",
    "www.facebook.com",
    "facebook.com",
    "twitter.com",
    "wyomingnews-wy.newsmemory.com",
    "apg05.newzware.com",
    "www.googletagmanager.com",
    "fonts.gstatic.com",
    "ajax.googleapis.com",
    "www.google-analytics.com",
}

TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".txt",
    ".csv",
    ".py",
    ".yml",
    ".yaml",
    ".html",
    ".htm",
    ".js",
    ".mjs",
    ".sql",
    ".srt",
    ".vtt",
    ".xml",
    ".log",
    ".ipynb",
}


@dataclass
class UrlHit:
    host: str
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"host": self.host, "count": self.count, "examples": self.examples[:6]}


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def display_host(host: str) -> tuple[str, str, str]:
    if host in HOSTS:
        return HOSTS[host]
    bare = host[4:] if host.startswith("www.") else host
    for key, val in HOSTS.items():
        if key.lstrip("www.") == bare:
            return val
    return (host, "source site", "")


def looks_like_text(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= 12 * 1024 * 1024
    except OSError:
        return False


def scan_paths(
    paths: list[Path],
    max_files: int = 400,
    sample_bytes: int = 640_000,
) -> list[UrlHit]:
    """Count URL hosts across a bounded sample of a family's files."""
    counts: collections.Counter[str] = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    seen = 0
    for p in paths:
        if seen >= max_files:
            break
        if not looks_like_text(p):
            continue
        seen += 1
        try:
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                blob = fh.read(sample_bytes)
        except OSError:
            continue
        for m in URL_RE.finditer(blob):
            url = m.group(0).rstrip(".,")
            h = host_of(url)
            if not h or h in NOISE_HOSTS:
                continue
            counts[h] += 1
            if len(examples[h]) < 4 and url not in examples[h]:
                examples[h].append(url)
    return [
        UrlHit(host=h, count=c, examples=examples[h])
        for h, c in counts.most_common()
    ]


def family_hosts(paths: list[Path], limit: int = 8, max_files: int = 300) -> list[UrlHit]:
    hits = scan_paths(paths, max_files=max_files)
    return [h for h in hits if h.count >= 1][:limit]


# --------------------------------------------------------------------------
# Explicit, hand-checked provenance for families whose files are binary or
# whose origin is documented in the repo's own manifests rather than in URLs.
# --------------------------------------------------------------------------

CURATED: dict[str, dict] = {
    "meeting_calendar": {
        "site": "City of Cheyenne — Minutes and Agendas",
        "url": "https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas",
        "portal": "www.cheyennecity.org",
        "evidence": "config/sources.json → sources[0] (CONFIRMED live 2026-09-05)",
        "note": "Council, Finance, Public Services, Committee of the Whole, Work Sessions.",
    },
    "agenda_documents": {
        "site": "Granicus — Cheyenne AgendaViewer",
        "url": "https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126",
        "portal": "cheyenne.granicus.com",
        "evidence": "youtube-archive/catalog_granicus.csv → agenda_url column",
        "note": "The city links each packet PDF out to Granicus; robots.txt refuses bots.",
    },
    "supporting_documents": {
        "site": "Granicus — Agenda Supporting Documents",
        "url": "https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126",
        "portal": "cheyenne.granicus.com",
        "evidence": "artifacts/Cheyenne_Audit_raw/*Agenda_Supporting_Document*.pdf (MetaID/Attachment IDs)",
        "note": "Staff reports, plats, ordinances — the attachments behind each agenda item.",
    },
    "meeting_video": {
        "site": "Granicus video archive + City YouTube",
        "url": "https://archive-video.granicus.com/cheyenne/",
        "portal": "archive-video.granicus.com",
        "evidence": "youtube-archive/catalog_granicus.csv → mp4_url / player_url",
        "note": "Full tapes; clips are cut from these files, never re-enacted.",
    },
    "transcripts": {
        "site": "YouTube auto-captions (City of Cheyenne channel)",
        "url": "https://www.youtube.com/@CityofCheyenne",
        "portal": "www.youtube.com",
        "evidence": "pipeline/cityvideos.json + pipeline/corpus_yt/*.txt",
        "note": "Caption tracks converted to timestamped text so moments are findable without video.",
    },
    "news": {
        "site": "Cap City News + Wyoming Tribune Eagle",
        "url": "https://capcity.news/feed",
        "portal": "capcity.news",
        "evidence": "config/sources.json → cap_city_news_rss, wte_local_rss",
        "note": "WordPress /feed for Cap City; TownNews search-RSS for the Tribune Eagle.",
    },
    "arrests": {
        "site": "Laramie County weekly arrest report (via Cap City News)",
        "url": "https://capcity.news/",
        "portal": "capcity.news",
        "evidence": "data/arrests/records.json → record.source_url / source_sha256",
        "note": "De-identified public tier; names sealed behind an issue request.",
    },
    "scanner": {
        "site": "Broadcastify — Laramie County feed 47003",
        "url": "https://www.broadcastify.com/archives/feed/47003/",
        "portal": "www.broadcastify.com",
        "evidence": "scanner-results/runs/*/transcript.json → source segments",
        "note": "Archived radio segments, transcribed locally with whisper; review required.",
    },
    "open_data": {
        "site": "Laramie County Sheriff Socrata + LETMSP",
        "url": "https://laramiecountywy-sheriff.data.socrata.com/",
        "portal": "laramiecountywy-sheriff.data.socrata.com",
        "evidence": "scanner-results/socrata/datasets.json + network.json",
        "note": "Probed honestly: the API answered 403 and the dashboard needed a login.",
    },
    "drive_corpus": {
        "site": "Google Drive — WindyCityMeetings",
        "url": "https://drive.google.com/drive/folders/WindyCityMeetings",
        "portal": "docs.google.com",
        "evidence": "drive-import/manifest.json → source_path /content/drive/MyDrive/WindyCityMeetings/",
        "note": "720 normalised meeting records with 39.9M characters of caption text.",
    },
    "ocr": {
        "site": "Six sibling archive repos (scanned planning documents)",
        "url": "https://github.com/therealwindycity",
        "portal": "github.com/therealwindycity",
        "evidence": "ai-record-ocr/*.json keys are sha1 names from tools/ai_record_extract.py",
        "note": "Scans with no text layer — OCR'd page by page and committed incrementally.",
    },
}


def curated(key: str) -> dict | None:
    return CURATED.get(key)


def origin_table(host_hits: list[UrlHit], limit: int = 6) -> list[dict]:
    out = []
    for hit in host_hits[:limit]:
        name, kind, note = display_host(hit.host)
        out.append(
            {
                "host": hit.host,
                "name": name,
                "kind": kind,
                "note": note,
                "count": hit.count,
                "examples": hit.examples[:3],
            }
        )
    return out


def repo_upstreams(root: Path) -> list[dict]:
    """Sibling repos this checkout depends on, found in its own docs."""
    pat = re.compile(r"github\.com/therealwindycity/([A-Za-z0-9._-]+)")
    found: collections.Counter[str] = collections.Counter()
    for base, dirs, files in os.walk(root):
        if any(part in base for part in (".git", "node_modules", "__pycache__")):
            continue
        for f in files:
            p = Path(base) / f
            if p.suffix.lower() not in {".md", ".py", ".yml", ".yaml", ".json"}:
                continue
            try:
                if p.stat().st_size > 2_000_000:
                    continue
                blob = p.read_text("utf-8", "ignore")
            except OSError:
                continue
            for m in pat.finditer(blob):
                name = m.group(1).rstrip(".")
                if name and not name.endswith((".git",)):
                    found[name] += 1
    return [{"repo": k, "mentions": v} for k, v in found.most_common()]
