"""Detect every scraped dataset this checkout (and its sibling repos) consist of.

The scanner is deliberately dumb and total: it walks *every* file in the repo,
assigns each one to exactly one data family by path pattern, and reports what is
left over. Nothing is allowed to silently fall out of the accounting — the
unassigned bucket is part of the output, so a reader can see that 100% of the
tree was classified.

Each family carries the provenance chain used by the film: where the bytes
originate (public site + URL + the file in this repo that proves it), what a
human would have had to do by hand to assemble it, and where it lives now.
"""

from __future__ import annotations

import collections
import fnmatch
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from . import origins

EXCLUDE_PATHS = {"data/out/preview"}

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "_site",
}


@dataclass
class Family:
    key: str
    title: str
    data_class: str  # scraped | derived | generated | code
    unit: str
    destination: str
    patterns: list[str]
    origin_key: str | None = None
    seconds_per_unit: float = 0.0
    actions_per_unit: float = 0.0
    page: str = "list"
    accent: str = "#4cc9f0"
    caption: str = ""
    # filled in by the scanner
    files: int = 0
    bytes: int = 0
    units: int = 0
    samples: list[str] = field(default_factory=list)
    ext_counts: dict[str, int] = field(default_factory=dict)
    host_hits: list[origins.UrlHit] = field(default_factory=list)
    unit_note: str = ""

    def match(self, relpath: str) -> bool:
        return any(fnmatch.fnmatch(relpath, p) for p in self.patterns)

    @property
    def manual_seconds(self) -> float:
        return self.units * self.seconds_per_unit

    @property
    def manual_actions(self) -> float:
        return self.units * self.actions_per_unit


# --------------------------------------------------------------------------
# The families, in the order the film walks through them.
# --------------------------------------------------------------------------

FAMILIES: list[Family] = [
    Family(
        key="meeting_calendar",
        title="Meeting calendar & meeting days",
        data_class="scraped",
        unit="meeting day",
        destination="data/snapshots/ · 2026-09-14-council/meetings/",
        patterns=[
            "2026-09-14-council/meetings/*/*.json",
            "2026-09-14-council/meetings/*/*.md",
            "pipeline/meetings.json",
            "pipeline/docs/*/*.html",
            "pipeline/docs/*.html",
        ],
        origin_key="meeting_calendar",
        seconds_per_unit=40.0,
        actions_per_unit=5,
        page="list",
        accent="#4cc9f0",
        caption=(
            "Every body, every meeting night: Council, Finance, Public Services, "
            "Committee of the Whole, Work Sessions — pulled off the city's agenda listing."
        ),
    ),
    Family(
        key="supporting_documents",
        title="Supporting documents",
        data_class="scraped",
        unit="attachment",
        destination="artifacts/Cheyenne_Audit_raw/",
        patterns=[
            "artifacts/Cheyenne_Audit_raw/*Supporting_Document*",
            "artifacts/Cheyenne_Audit_raw/*.html",
        ],
        origin_key="supporting_documents",
        seconds_per_unit=60.0,
        actions_per_unit=7,
        page="doc",
        accent="#f9844a",
        caption=(
            "Staff reports, plats, ordinances, correspondence — every attachment "
            "behind every item, each one its own click."
        ),
    ),
    Family(
        key="agenda_documents",
        title="Agenda packets",
        data_class="scraped",
        unit="agenda file",
        destination="artifacts/Cheyenne_Audit_raw/",
        patterns=[
            "artifacts/Cheyenne_Audit_raw/*.pdf",
            "2026-09-14-council/meetings/*/pdf/*.pdf",
        ],
        origin_key="agenda_documents",
        seconds_per_unit=45.0,
        actions_per_unit=6,
        page="doc",
        accent="#f9c74f",
        caption=(
            "The packet itself: open the date, open the file, download it, name it, "
            "file it. One per meeting, hundreds of meetings."
        ),
    ),
    Family(
        key="minutes_and_notes",
        title="Minutes & meeting notes",
        data_class="scraped",
        unit="meeting document",
        destination="uploads/",
        patterns=[
            "uploads/[!.]*",
            "2026-09-14-council/meetings/minutes/*",
        ],
        origin_key="meeting_calendar",
        seconds_per_unit=50.0,
        actions_per_unit=5,
        page="doc",
        accent="#90be6d",
        caption=(
            "The clerk's minutes and the running notes, saved as plain text so the "
            "search index can read what a PDF hides."
        ),
    ),
    Family(
        key="extracted_text",
        title="Extracted document text",
        data_class="scraped",
        unit="text extract",
        destination="data/text/",
        patterns=[
            "data/text/*",
            "2026-09-14-council/meetings/*/txt/*",
        ],
        origin_key="meeting_calendar",
        seconds_per_unit=25.0,
        actions_per_unit=3,
        page="doc",
        accent="#43aa8b",
        caption="Each captured document reduced to searchable text, page markers kept.",
    ),
    Family(
        key="meeting_video",
        title="Meeting tape",
        data_class="scraped",
        unit="meeting recording",
        destination="pipeline/videos/",
        patterns=[
            "pipeline/videos/*.mp4",
        ],
        origin_key="meeting_video",
        seconds_per_unit=180.0,
        actions_per_unit=9,
        page="video",
        accent="#f94144",
        caption=(
            "The tape. Pulled from the Granicus archive, never re-enacted: "
            "officials' voices are the real recordings or they are not used."
        ),
    ),
    Family(
        key="transcripts",
        title="Transcripts & caption tracks",
        data_class="scraped",
        unit="transcript",
        destination="pipeline/corpus_yt/",
        patterns=[
            "pipeline/corpus/*",
            "pipeline/corpus_clean/*",
            "pipeline/corpus_yt/*",
            "pipeline/cut_captions/*",
            "pipeline/docs/*.vtt",
            "pipeline/*.vtt",
            "*.vtt",
            "*.srt",
        ],
        origin_key="transcripts",
        seconds_per_unit=90.0,
        actions_per_unit=6,
        page="list",
        accent="#577590",
        caption=(
            "Auto-generated captions, converted to timestamped text. This is what "
            "makes a moment findable without scrubbing a four-hour tape."
        ),
    ),
    Family(
        key="video_catalog",
        title="Meeting video catalogue",
        data_class="scraped",
        unit="catalogued meeting",
        destination="youtube-archive/",
        patterns=[
            "youtube-archive/catalog_*",
            "pipeline/cityvideos.json",
            "youtube-archive/upload_plan.*",
            "youtube-archive/*audit*.json",
        ],
        origin_key="meeting_video",
        seconds_per_unit=30.0,
        actions_per_unit=3,
        page="table",
        accent="#9b5de5",
        caption=(
            "Date → clip ID → player → agenda → minutes. The map that keeps every "
            "future pull honest about which meeting it is looking at."
        ),
    ),
    Family(
        key="drive_corpus",
        title="Processed meetings database",
        data_class="scraped",
        unit="meeting record",
        destination="drive-import/",
        patterns=[
            "drive-import/*",
            "public/master_meetings_database_linked.json",
        ],
        origin_key="drive_corpus",
        seconds_per_unit=120.0,
        actions_per_unit=4,
        page="files",
        accent="#00bbf9",
        caption=(
            "720 meetings normalised in Google Drive: agendas, minutes, supporting "
            "documents and 39.9M characters of speech, linked into one record each."
        ),
    ),
    Family(
        key="news",
        title="News coverage",
        data_class="scraped",
        unit="article / digest item",
        destination="data/out/",
        patterns=[
            "intel_index.json",
            "data/out/digest-*",
            "public/feed.xml",
            "data/snapshots/*",
        ],
        origin_key="news",
        seconds_per_unit=30.0,
        actions_per_unit=3,
        page="list",
        accent="#f8961e",
        caption=(
            "Cap City News and the Tribune Eagle, pulled by RSS, quoted verbatim "
            "with the fetch timestamp kept."
        ),
    ),
    Family(
        key="arrests",
        title="Arrest reports (de-identified)",
        data_class="scraped",
        unit="record",
        destination="data/arrests/",
        patterns=["data/arrests/*"],
        origin_key="arrests",
        seconds_per_unit=120.0,
        actions_per_unit=6,
        page="table",
        accent="#ef476f",
        caption=(
            "The county's weekly arrest report. Charges kept verbatim, names sealed "
            "and released only through a reviewed request."
        ),
    ),
    Family(
        key="scanner",
        title="Scanner audio transcripts",
        data_class="scraped",
        unit="radio segment",
        destination="scanner-results/runs/",
        patterns=[
            "scanner-results/runs/*",
            "scanner-results/live-runs/*",
            "scanner-results/history/*",
            "scanner-results/recent/*",
            "scanner-results/latest.json",
        ],
        origin_key="scanner",
        seconds_per_unit=150.0,
        actions_per_unit=8,
        page="audio",
        accent="#ffd166",
        caption=(
            "Public-safety radio from Broadcastify feed 47003, transcribed locally. "
            "Flagged unverified because a machine heard it."
        ),
    ),
    Family(
        key="open_data",
        title="Open-data & records probes",
        data_class="scraped",
        unit="dataset probe",
        destination="scanner-results/socrata/",
        patterns=["scanner-results/socrata/*"],
        origin_key="open_data",
        seconds_per_unit=240.0,
        actions_per_unit=10,
        page="table",
        accent="#06d6a0",
        caption=(
            "Socrata datasets and the LETMSP dashboard, probed in the open. "
            "The API said 403; the report says so instead of pretending."
        ),
    ),
    Family(
        key="ocr",
        title="OCR of scanned documents",
        data_class="derived",
        unit="scanned document",
        destination="ai-record-ocr/",
        patterns=["ai-record-ocr/*"],
        origin_key="ocr",
        seconds_per_unit=300.0,
        actions_per_unit=6,
        page="doc",
        accent="#8d99ae",
        caption=(
            "Plans old enough to be photographs of paper. Page by page OCR, "
            "committed so the backlog survives a rerun."
        ),
    ),
    Family(
        key="rag_index",
        title="Search / RAG index",
        data_class="derived",
        unit="embedded chunk",
        destination="rag/",
        patterns=[
            "rag/vectordb_sample/*",
            "rag/*.json",
            "rag/*.jsonl",
        ],
        seconds_per_unit=0,
        actions_per_unit=0,
        page="files",
        accent="#b5179e",
        caption="Everything above, chunked and embedded so the console can answer from it.",
    ),
    Family(
        key="civicwatch",
        title="Civicwatch mirror",
        data_class="scraped",
        unit="civic record",
        destination="2026-09-14-council/civicwatch/",
        patterns=[
            "2026-09-14-council/civicwatch/data/*",
            "2026-09-14-council/civicwatch/models/*",
            "2026-09-14-council/civicwatch/*.txt",
            "2026-09-14-council/civicwatch/*.html",
            "2026-09-14-council/civicwatch/*.ipynb",
            "2026-09-14-council/civicwatch/*.py",
            "2026-09-14-council/civicwatch/*.sh",
        ],
        origin_key="transcripts",
        seconds_per_unit=60.0,
        actions_per_unit=4,
        page="files",
        accent="#4d908e",
        caption="A parallel capture of the same meetings, kept so the two can be diffed.",
    ),
    Family(
        key="derived_analysis",
        title="Analysis & dossiers written from the record",
        data_class="derived",
        unit="document",
        destination="repo root",
        patterns=[
            "*.md",
            "docs/*",
            "2026-09-14-council/*.md",
            "2026-09-14-council/civicwatch/briefs/*",
            "pipeline/*.md",
            "tools/*.md",
            "youtube-archive/docs/*",
            "youtube-archive/README.md",
        ],
        page="doc",
        accent="#adb5bd",
        caption="Not scraped: written from what the scraped record shows, with every claim sourced.",
    ),
    Family(
        key="silent_edits",
        title="Silent-edit diffs",
        data_class="derived",
        unit="version diff",
        destination="data/out/",
        patterns=["data/out/*.diff.txt"],
        page="doc",
        accent="#e07a5f",
        caption=(
            "The watchdog re-fetches every document and fingerprints it. When a page "
            "changes without notice, the diff is kept — that is the whole point."
        ),
    ),
    Family(
        key="meeting_derivatives",
        title="Meeting structure &amp; cut lists",
        data_class="derived",
        unit="derived record",
        destination="pipeline/",
        patterns=[
            "pipeline/*.json",
            "pipeline/asks/*",
            "pipeline/notebooklm/*",
            "pipeline/renders/*.txt",
            "pipeline/renders/*.html",
            "pipeline/pull_list.txt",
        ],
        page="table",
        accent="#7f5539",
        caption="Ordinance histories, interventions, pull lists — built from the transcripts and the tape.",
    ),
    Family(
        key="entities",
        title="Entity database",
        data_class="derived",
        unit="document profile",
        destination="Entity_Database/",
        patterns=["Entity_Database/*"],
        page="table",
        accent="#5f0f40",
        caption="Speakers, policies and places extracted from every document in the archive.",
    ),
    Family(
        key="civic_atlas",
        title="Civic atlas (experimental site)",
        data_class="generated",
        unit="page / asset",
        destination="civic_atlas/",
        patterns=["civic_atlas/*"],
        page="files",
        accent="#3a0ca3",
        caption="An experimental lens over the same record.",
    ),
    Family(
        key="agent",
        title="Field agent tooling",
        data_class="code",
        unit="file",
        destination="agent/",
        patterns=["agent/*"],
        page="files",
        accent="#495057",
        caption="",
    ),
    Family(
        key="repo_meta",
        title="Repo metadata &amp; local databases",
        data_class="code",
        unit="file",
        destination="repo root",
        patterns=[
            "*.db",
            "*.json",
            "data/*.log",
            "data/*.db-*",
            ".gitignore",
            ".cursorrules",
            "requirements.txt",
            "*requirements*.txt",
            "youtube-archive/.gitignore",
        ],
        page="files",
        accent="#343a40",
        caption="",
    ),

    Family(
        key="montage_reels",
        title="Edited reels cut from the tapes",
        data_class="derived",
        unit="film cut",
        destination="video/ · videos/",
        patterns=["videos/*", "video/*.mp4", "pipeline/build_reel*", "pipeline/renders/*.mp4"],
        page="files",
        accent="#9b5de5",
        caption="Clips cut out of the public meetings, with the source tape noted beside each cut.",
    ),
    Family(
        key="provenance_film",
        title="Provenance report &amp; this film",
        data_class="generated",
        unit="artifact",
        destination="data/out/ · video/",
        patterns=["data/out/provenance-*", "video/provenance-*", "video/clips/*",
                  "provenance/*", "tools/check_provenance.py", "rwc_provenance.py"],
        page="files",
        accent="#2b6cb0",
        caption="The inventory and this film, generated from the checkout itself.",
    ),
    Family(
        key="published_site",
        title="Published site & feeds",
        data_class="generated",
        unit="page",
        destination="pages/ · public/",
        patterns=["pages/*", "public/*.html", "public/*.xml", ".well-known/*", "locked-resource/*"],
        page="files",
        accent="#6c757d",
        caption="The public face: the console pages, the ledger, the RSS feed, the AI-readable mirror.",
    ),
    Family(
        key="code",
        title="Pipelines, scrapers & console code",
        data_class="code",
        unit="source file",
        destination="engine/ · tools/ · scripts/",
        patterns=[
            "engine/*",
            "tools/*",
            "scripts/*",
            "scrapers/*",
            "pipeline/*.py",
            "pipeline/*.sh",
            "promethean/*",
            "rag/*.py",
            "config/*",
            ".github/*",
            "deploy/*",
            "database/*",
            "*.py",
            "*.sh",
            "*.yml",
            "*.toml",
            "requirements.txt",
        ],
        page="files",
        accent="#495057",
        caption="The machinery that does the collecting on a six-hour cycle.",
    ),
]


# --------------------------------------------------------------------------
# Unit counting — some families' files are not their units.
# --------------------------------------------------------------------------


def _count_json_rows(path: Path) -> int:
    try:
        data = json.loads(path.read_text("utf-8", "ignore"))
    except Exception:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("records", "documents", "datasets", "items", "pages"):
            if isinstance(data.get(key), list):
                return len(data[key])
    return 0


def _count_lines(path: Path) -> int:
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _engine_db_units(root: Path) -> tuple[int, str]:
    db = root / "data" / "engine.db"
    if not db.exists():
        return 0, ""
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        docs = con.execute("select count(*) from documents").fetchone()[0]
        vers = con.execute("select count(*) from versions").fetchone()[0]
        alerts = con.execute("select count(*) from alerts").fetchone()[0]
        con.close()
        return docs, f"{docs:,} documents · {vers:,} versions · {alerts:,} alerts"
    except Exception:
        return 0, ""


_MANIFEST_CACHE: dict[str, dict] = {}


def _manifest_profile(root: Path) -> dict:
    key = str(root)
    if key in _MANIFEST_CACHE:
        return _MANIFEST_CACHE[key]
    prof: dict = {}
    man = root / "drive-import" / "manifest.json"
    if man.exists():
        try:
            d = json.loads(man.read_text("utf-8", "ignore"))
            prof = next(iter(d.get("imports", {}).values()), {}).get("profile", {}) or {}
        except Exception:
            prof = {}
    _MANIFEST_CACHE[key] = prof
    return prof


def count_units(fam: Family, paths: list[Path], root: Path) -> tuple[int, str]:
    key = fam.key
    prof = _manifest_profile(root)
    fields = prof.get("top_level_fields", {}) or {}
    if key == "agenda_documents" and fields.get("agendas"):
        n = int(fields["agendas"])
        return n, f"{n:,} agendas linked · {len(paths)} packet files committed here"
    if key == "supporting_documents" and fields.get("supporting_documents"):
        n = int(fields["supporting_documents"])
        return n, f"{n:,} meetings carry attachments · {len(paths)} committed here"
    if key == "minutes_and_notes" and fields.get("minutes"):
        n = int(fields["minutes"])
        return n, f"{n:,} minutes referenced · {len(paths)} saved as text here"
    if key == "arrests":
        for p in paths:
            if p.name == "records.json":
                n = _count_json_rows(p)
                if n:
                    return n, f"{n:,} de-identified records"
    if key == "open_data":
        for p in paths:
            if p.name == "datasets.json":
                n = _count_json_rows(p)
                if n:
                    return n, f"{n:,} datasets probed"
    if key == "drive_corpus":
        man = root / "drive-import" / "manifest.json"
        if man.exists():
            try:
                d = json.loads(man.read_text("utf-8", "ignore"))
                prof = next(iter(d.get("imports", {}).values()), {}).get("profile", {})
                n = prof.get("records", 0)
                if n:
                    return n, f"{n:,} meeting records · {prof.get('turn_text_chars', 0):,} chars of speech"
            except Exception:
                pass
    if key == "video_catalog":
        for p in paths:
            if fnmatch.fnmatch(p.name, "catalog_granicus*") and p.suffix == ".csv":
                n = max(0, _count_lines(p) - 1)
                if n:
                    return n, f"{n:,} meetings catalogued"
    if key == "meeting_calendar":
        meetings = 0
        cal = root / "pipeline" / "meetings.json"
        if cal.exists():
            try:
                meetings = len(json.loads(cal.read_text("utf-8", "ignore")).get("meetings", {}))
            except Exception:
                meetings = 0
        if meetings:
            return meetings, f"{meetings:,} meeting nights indexed · {len(paths)} city pages captured"
        return len(paths), f"{len(paths):,} captured city pages"
    if key == "news":
        idx = root / "intel_index.json"
        if idx.exists():
            try:
                d = json.loads(idx.read_text("utf-8", "ignore"))
                n = d.get("stats", {}).get("documents", 0)
                if n:
                    return n, f"{n:,} indexed documents"
            except Exception:
                pass
    if key == "ocr":
        return len(paths), f"{len(paths):,} scanned documents OCR'd"
    if key == "rag_index":
        for p in paths:
            if p.suffix == ".jsonl":
                n = _count_lines(p)
                if n:
                    return n, f"{n:,} embedded chunks"
    if key == "transcripts":
        total = 0
        for p in paths[:400]:
            if p.suffix in {".txt", ".vtt", ".srt"}:
                total += _count_lines(p)
        if total:
            return len(paths), f"{len(paths):,} files · {total:,} lines"
    if key == "published_site" or key == "code":
        return len(paths), ""
    if key == "derived_analysis":
        return len(paths), ""
    return len(paths), ""


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------


@dataclass
class Inventory:
    root: Path
    generated_at: str
    families: list[Family]
    unassigned: dict
    total_files: int
    total_bytes: int
    upstreams: list[dict]
    engine_ledger: dict
    host_totals: list[dict]

    # -- aggregates -------------------------------------------------------
    @property
    def scraped(self) -> list[Family]:
        return [f for f in self.families if f.data_class == "scraped"]

    @property
    def data_families(self) -> list[Family]:
        return [f for f in self.families if f.data_class != "code"]

    @property
    def scraped_files(self) -> int:
        return sum(f.files for f in self.scraped)

    @property
    def scraped_bytes(self) -> int:
        return sum(f.bytes for f in self.scraped)

    @property
    def manual_seconds(self) -> float:
        return sum(f.manual_seconds for f in self.families)

    @property
    def manual_seconds_scraped(self) -> float:
        """Hand-work for data that actually had to be fetched (not derived here)."""
        return sum(f.manual_seconds for f in self.families if f.data_class == "scraped")

    @property
    def manual_actions_scraped(self) -> float:
        return sum(f.manual_actions for f in self.families if f.data_class == "scraped")

    @property
    def manual_actions(self) -> float:
        return sum(f.manual_actions for f in self.families)

    def family(self, key: str) -> Family:
        for f in self.families:
            if f.key == key:
                return f
        raise KeyError(key)

    # -- serialisation ----------------------------------------------------
    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "repo": str(self.root),
            "totals": {
                "files": self.total_files,
                "bytes": self.total_bytes,
                "families": len(self.families),
                "scraped_files": self.scraped_files,
                "scraped_bytes": self.scraped_bytes,
                "estimated_manual_seconds": round(self.manual_seconds),
                "estimated_manual_actions": round(self.manual_actions),
            },
            "engine_ledger": self.engine_ledger,
            "upstream_repos": self.upstreams,
            "source_hosts": self.host_totals,
            "unassigned": self.unassigned,
            "families": [
                {
                    "key": f.key,
                    "title": f.title,
                    "class": f.data_class,
                    "unit": f.unit,
                    "units": f.units,
                    "unit_note": f.unit_note,
                    "files": f.files,
                    "bytes": f.bytes,
                    "destination": f.destination,
                    "origin": origins.curated(f.origin_key) if f.origin_key else None,
                    "origin_hosts": origins.origin_table(f.host_hits, limit=5),
                    "evidence_samples": f.samples[:8],
                    "extensions": f.ext_counts,
                    "manual_estimate": {
                        "seconds_per_unit": f.seconds_per_unit,
                        "actions_per_unit": f.actions_per_unit,
                        "seconds_total": round(f.manual_seconds),
                        "actions_total": round(f.manual_actions),
                    },
                }
                for f in self.families
            ],
        }


DATE_RE = re.compile(r"(20\d{2})[-_.](\d{2})[-_.](\d{2})|(\d{2})-(\d{2})-(\d{2})\b")


def _year_of(name: str) -> int | None:
    m = DATE_RE.search(name)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    yy = int(m.group(6))
    return 2000 + yy if yy < 70 else 1900 + yy


def scan(root: Path, generated_at: str | None = None) -> Inventory:
    root = root.resolve()
    per_family: dict[str, list[Path]] = collections.defaultdict(list)
    sizes: dict[int, int] = {}
    unassigned: collections.Counter[str] = collections.Counter()
    unassigned_bytes = 0
    unassigned_files = 0
    total_files = 0
    total_bytes = 0

    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for name in files:
            p = Path(base) / name
            try:
                size = p.stat().st_size
            except OSError:
                continue
            rel = p.relative_to(root).as_posix()
            if any(rel == ex or rel.startswith(ex + "/") for ex in EXCLUDE_PATHS):
                continue
            total_files += 1
            total_bytes += size
            sizes[id(p)] = size
            for fam in FAMILIES:
                if fam.match(rel):
                    per_family[fam.key].append(p)
                    break
            else:
                unassigned[p.suffix.lower() or "(none)"] += 1
                unassigned_bytes += size
                unassigned_files += 1

    all_hosts: collections.Counter[str] = collections.Counter()
    for fam in FAMILIES:
        paths = per_family.get(fam.key, [])
        fam.files = len(paths)
        fam.bytes = sum(sizes.get(id(p), 0) for p in paths)
        fam.ext_counts = dict(
            collections.Counter(p.suffix.lower() or "(none)" for p in paths).most_common(6)
        )
        fam.samples = sorted(
            str(p.relative_to(root).as_posix()) for p in paths
        )[:8]
        units, note = count_units(fam, paths, root)
        fam.units = units
        fam.unit_note = note
        if fam.origin_key is None and fam.data_class == "scraped":
            fam.host_hits = origins.family_hosts(paths, limit=6)
            for hit in fam.host_hits:
                all_hosts[hit.host] += hit.count
        elif fam.data_class == "scraped":
            fam.host_hits = origins.family_hosts(paths, limit=6)
            for hit in fam.host_hits:
                all_hosts[hit.host] += hit.count

    engine_units, engine_note = _engine_db_units(root)
    engine_ledger = {
        "documents": engine_units,
        "note": engine_note,
        "source": "data/engine.db (FTS5 full-text index + version history)",
    }

    # Only hosts in the curated catalogue count as *source sites*; CDN/analytics
    # noise is excluded so the headline number means something.
    host_totals = []
    for h, c in all_hosts.most_common():
        if h not in origins.HOSTS and ("www." + h) not in origins.HOSTS:
            continue
        name, kind, _note = origins.display_host(h)
        host_totals.append({"host": h, "name": name, "kind": kind, "count": c})
        if len(host_totals) >= 16:
            break

    return Inventory(
        root=root,
        generated_at=generated_at or "",
        families=FAMILIES,
        unassigned={
            "files": unassigned_files,
            "bytes": unassigned_bytes,
            "by_extension": dict(unassigned.most_common(10)),
        },
        total_files=total_files,
        total_bytes=total_bytes,
        upstreams=origins.repo_upstreams(root),
        engine_ledger=engine_ledger,
        host_totals=host_totals,
    )
