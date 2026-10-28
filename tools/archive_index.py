#!/usr/bin/env python3
"""Index the cold Cheyenne archive: enumerate, date, extract, search.

Six repositories (therealwindycity/cheyenne-archives-2008-2013 …
-2025-2026) hold 5,140 PDF blobs totalling 6,970,150,704 bytes — 18 years of
council agendas, packets, supporting documents and minutes. They have no
workflows, no Pages and no full-text search, so the largest body of primary
records in this ecosystem is the least reachable part of it. This tool makes it
reachable.

Stages (each independently runnable and resumable):

  catalog   Enumerate every blob via the Git trees API, parse the date out of
            the path, classify the document, and write a catalog + a Frictionless
            Data Package descriptor. No file content is downloaded.
  extract   Fetch PDFs and pull their text layer. Resumable: an already-cached
            extraction is never re-fetched. Bounded by --limit and --max-bytes
            so a full 6.97 GB run is a deliberate choice, not an accident.
  index     Build a sharded inverted index over the extracted text.
  search    Query the index; every hit carries its source locator.

Date parsing is the load-bearing part. Every folder is named
"<unix_epoch><pretty date> - <body>", e.g.
"1641801600Jan 10, 2022 - City Council Meeting". The epoch prefix is
authoritative and the pretty date is cross-checked against it; a disagreement
is recorded as a conflict rather than silently resolved, because a date is the
one field a researcher cannot recover if it is wrong.

Honesty rules, matching the repository's existing conventions:
  * coverage is reported as enumerated / extracted / failed / skipped, never as
    a single percentage that hides which stage is incomplete;
  * a PDF with no text layer is recorded as "image-only, needs OCR", not as
    empty and not as a failure;
  * extraction method and tool version are recorded per document, so a reader
    knows whether text came from a PDF text layer or from OCR.

Stdlib only for catalog/index/search. `extract` needs pypdf (pip install pypdf)
and degrades to a clear message without it. Network access is limited to
api.github.com and raw.githubusercontent.com.

Examples:
  python tools/archive_index.py catalog --out data/archive-index
  python tools/archive_index.py extract --out data/archive-index --limit 20
  python tools/archive_index.py index   --out data/archive-index
  python tools/archive_index.py search  --out data/archive-index "reappropriation"
  python tools/archive_index.py coverage --out data/archive-index
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ARCHIVE_REPOS: tuple[str, ...] = (
    "therealwindycity/cheyenne-archives-2008-2013",
    "therealwindycity/cheyenne-archives-2014-2017",
    "therealwindycity/cheyenne-archives-2018-2021",
    "therealwindycity/cheyenne-archives-2022",
    "therealwindycity/cheyenne-archives-2023-2024",
    "therealwindycity/cheyenne-archives-2025-2026",
)

API_ROOT = "https://api.github.com"
RAW_ROOT = "https://raw.githubusercontent.com"
USER_AGENT = "therealwindycity-archive-index/1.0 (public-records research; contact repo owner)"

# "<epoch><Month Day, Year> - <body>" with an arbitrary number of spaces.
FOLDER_RE = re.compile(
    r"^(?P<epoch>\d{9,11})(?P<month>[A-Z][a-z]{2,8})\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})\s*-\s*(?P<body>.+?)\s*$"
)
PRETTY_RE = re.compile(r"^(?P<month>[A-Z][a-z]+)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})$")

_FULL_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December")
# Both full and three-letter abbreviated forms occur in the archive, sometimes
# with double spaces ("Jun  9, 2008"). Accepting only full names silently drops
# every month that abbreviates, which is eleven of twelve.
MONTHS = {m: i for i, m in enumerate(_FULL_MONTHS, start=1)}
MONTHS.update({m[:3]: i for i, m in enumerate(_FULL_MONTHS, start=1)})
# "Mar" and "May" both start with "Ma"; the dict update above is keyed on the
# exact three-letter form so there is no ambiguity, but "June"/"July" both give
# "Jun"/"Jul" distinctly. September appears as both "Sep" and "Sept" upstream.
MONTHS["Sept"] = 9

# Document classes inferred from the file name. Deliberately a closed vocabulary
# with an explicit "other" bucket: an unrecognised name must be visible as
# unrecognised, not folded into a guess.
DOC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("minutes", re.compile(r"\bminutes\b", re.I)),
    ("agenda", re.compile(r"\bagenda\b", re.I)),
    ("proposed-substitute", re.compile(r"proposed\s+(amended\s+)?substitute", re.I)),
    ("approved-substitute", re.compile(r"approved\s+substitute", re.I)),
    ("amended-exhibit", re.compile(r"amended\s+exhibit", re.I)),
    ("exhibit", re.compile(r"\bexhibit\b", re.I)),
    ("resolution", re.compile(r"\bresolution\b", re.I)),
    ("ordinance", re.compile(r"\bordinance\b", re.I)),
    ("contract", re.compile(r"\bcontract\b|\bagreement\b", re.I)),
    ("staff-report", re.compile(r"staff\s+report", re.I)),
    ("budget", re.compile(r"\bbudget\b|(?i:appropriat)", re.I)),
    ("supporting-document", re.compile(r"supporting\s+document", re.I)),
)

# Body names are normalised so that "City Council Meeting" and "City Council"
# group together, while anything unrecognised stays verbatim.
BODY_ALIASES = {
    "city council meeting": "city-council",
    "city council": "city-council",
    "cheyenne city council": "city-council",
    "cheyenne city council meeting": "city-council",
    "council meeting": "city-council",
}

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'\-]{1,}")
# Words that carry no retrieval signal in municipal records. Kept short and
# explicit: an aggressive stoplist silently destroys recall for exactly the
# procedural vocabulary ("motion", "seconded", "objection") that matters here.
STOPWORDS = frozenset("""a an and are as at be by for from has have in is it its of on or
that the to was were with""".split())

MIN_TOKEN_LEN = 3
# Shard the index by first letter so a single JSON file never grows past a
# size that a browser or a Pages artifact can reasonably carry.
SHARD_COUNT = 16


def http_get(url: str, timeout: int = 60, accept: str = "application/vnd.github+json") -> bytes:
    """GET a URL with a real user agent. Raises on any non-2xx."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Encoding": "gzip",
    })
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith(API_ROOT):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    return raw


def api_json(url: str) -> dict | list:
    return json.loads(http_get(url).decode("utf-8"))


# raw.githubusercontent.com is the natural host for blob bytes, but it is not
# reachable from every restricted environment, whereas api.github.com usually
# is. The contents endpoint returns base64 inline up to 1 MB, so the two are
# used together: API first for small files, raw for large ones, and a fetch
# failure is recorded per document rather than aborting the run.
CONTENTS_MAX_BYTES = 1_000_000


def api_contents_url(repo: str, path: str, ref: str = "HEAD") -> str:
    return f"{API_ROOT}/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}"


def fetch_blob(record: dict, timeout: int = 60) -> tuple[bytes, str]:
    """Download one blob. Returns (bytes, transport_used). Raises on failure."""
    import base64
    size = int(record.get("bytes") or 0)
    errors: list[str] = []
    if size <= CONTENTS_MAX_BYTES:
        try:
            meta = api_json(api_contents_url(record["repository"], record["path"]))
            if meta.get("encoding") == "base64" and meta.get("content"):
                return base64.b64decode(meta["content"]), "api-contents-base64"
            errors.append(f"api-contents:unexpected-encoding:{meta.get('encoding')}")
        except Exception as exc:  # noqa: BLE001 - recorded, then the fallback runs
            errors.append(f"api-contents:{type(exc).__name__}")
    try:
        return http_get(record["raw_url"], timeout=timeout,
                        accept="application/octet-stream"), "raw-githubusercontent"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"raw:{type(exc).__name__}")
    raise RuntimeError("; ".join(errors) or "no transport succeeded")


# --------------------------------------------------------------------------
# date parsing
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Path-scheme parsing
#
# The archive is not one naming scheme; it is five, accumulated over 18 years.
# Parsing only the first one silently loses 59% of the bytes, which is exactly
# what happened on the first run of this tool (456 folders parsed, 3,207 files
# left undated). Every record therefore carries `scheme`, so a consumer can see
# which parser produced its date, and `date_ambiguous` where the source name
# genuinely does not determine one.
# --------------------------------------------------------------------------

SCHEMES = ("epoch-folder", "agenda-packet", "agenda-packet-dir", "planning-commission",
           "county-commissioners", "municipal-docs", "repo-root-file", "unparsed")

# municipal-docs/ files are prefixed with the committee that met. Treating "cow"
# as the only prefix left 415 of 439 files undated; these are the real ones.
MUNICIPAL_BODIES = {
    "cow": ("committee-of-the-whole", "Committee of the Whole"),
    "fc": ("finance-committee", "Finance Committee"),
    "psc": ("public-services-committee", "Public Services Committee"),
    "ws": ("work-session", "Work Session"),
    "bopu": ("board-of-public-utilities", "Board of Public Utilities"),
    "city": ("city-council", "City Council"),
}


def _iso_or_none(text: str) -> str | None:
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def parse_epoch_folder(name: str) -> dict:
    """Parse "<epoch><Month[ abbr] Day, Year> - <body>".

    Both full and abbreviated month names occur, sometimes with double spaces
    ("Jun  9, 2008"). The epoch prefix is authoritative for ordering and the
    pretty date is cross-checked against it; a disagreement of more than a day
    is recorded as a conflict rather than silently averaged away, because a
    meeting date is the one field a researcher cannot recover if it is wrong.
    """
    match = FOLDER_RE.match(name)
    if not match:
        return {"parsed": False, "scheme": "unparsed",
                "reason": "folder-name-pattern-mismatch", "raw": name}
    epoch = int(match.group("epoch"))
    month_name = match.group("month")
    day = int(match.group("day"))
    year = int(match.group("year"))
    body_raw = match.group("body").strip()
    if month_name not in MONTHS:
        return {"parsed": False, "scheme": "unparsed",
                "reason": f"unknown-month:{month_name}", "raw": name}
    try:
        from_epoch = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
        from_pretty = dt.datetime(year, MONTHS[month_name], day, tzinfo=dt.timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        return {"parsed": False, "scheme": "unparsed",
                "reason": f"date-out-of-range:{exc}", "raw": name}

    delta_days = abs((from_epoch - from_pretty).days)
    body_key = BODY_ALIASES.get(body_raw.lower(), _slug(body_raw))
    return {
        "parsed": True,
        "scheme": "epoch-folder",
        "epoch": epoch,
        "date": from_pretty.date().isoformat(),
        "date_epoch_utc": from_epoch.date().isoformat(),
        "date_conflict": delta_days > 1,
        "date_conflict_days": delta_days,
        "date_ambiguous": False,
        "body_raw": body_raw,
        "body": body_key,
        "raw": name,
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unknown"


# agenda-packets/ holds three coexisting filename shapes for the same meeting:
#   CHEY-2012-10-22_Agenda.pdf      (ISO prefix)
#   Agenda_CHEY-2013-10-04.pdf      (ISO suffix)
#   CHEY-2012-10-22_packet-10.pdf   (ISO prefix + part number)
PACKET_ISO_RE = re.compile(r"CHEY-(?P<date>\d{4}-\d{2}-\d{2})")
PACKET_PART_RE = re.compile(r"packet-(?P<part>\d+)", re.I)


# agenda-packets/ has TWO coexisting shapes. The flat one puts the date in the
# filename (CHEY-2012-10-22_Agenda.pdf). The nested one puts it in the directory
# (agenda-packets/2022-11-14_City Council Meeting - Nov 14, 2022/Attachments/
# Supporting Document.pdf) and the filename carries no date at all. Reading only
# the filename leaves the entire Attachments tier undated.
PACKET_DIR_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<body>.+?)\s*-\s*(?P<month>[A-Z][a-z]{2,8})\.?\s*"
    r"(?P<day>\d{1,2}),\s*(?P<year>\d{4})$")


def parse_agenda_packet_dir(path: str) -> dict:
    parts = path.split("/")
    dirname = parts[1] if len(parts) > 2 else ""
    match = PACKET_DIR_RE.match(dirname)
    filename = path.rsplit("/", 1)[-1]
    if not match:
        return {"parsed": False, "scheme": "agenda-packet-dir",
                "reason": "no-ISO-date-in-directory-name", "raw": dirname or filename}
    date = _iso_or_none(match.group("date"))
    if not date:
        return {"parsed": False, "scheme": "agenda-packet-dir",
                "reason": f"invalid-iso-date:{match.group('date')}", "raw": dirname}
    month_name = match.group("month")
    pretty = None
    if month_name in MONTHS:
        try:
            pretty = dt.date(int(match.group("year")), MONTHS[month_name],
                             int(match.group("day"))).isoformat()
        except ValueError:
            pretty = None
    body_raw = match.group("body").strip()
    tier = parts[2] if len(parts) > 3 else None
    return {
        "parsed": True, "scheme": "agenda-packet-dir", "date": date,
        "date_pretty_in_dir": pretty,
        "date_conflict": bool(pretty and pretty != date),
        "date_conflict_days": (abs((dt.date.fromisoformat(pretty)
                                    - dt.date.fromisoformat(date)).days)
                               if pretty and pretty != date else 0),
        "date_ambiguous": False,
        "body": BODY_ALIASES.get(body_raw.lower(), _slug(body_raw)),
        "body_raw": body_raw,
        "attachment_tier": tier,
        "label": _slug(filename.rsplit(".", 1)[0]),
        "raw": path,
    }


def parse_agenda_packet(path: str) -> dict:
    filename = path.rsplit("/", 1)[-1]
    match = PACKET_ISO_RE.search(filename)
    if not match:
        # Fall back to the directory shape before declaring the record undated.
        nested = parse_agenda_packet_dir(path)
        if nested["parsed"]:
            return nested
        return {"parsed": False, "scheme": "agenda-packet",
                "reason": "no-CHEY-ISO-date-in-filename-and-no-ISO-directory",
                "raw": filename}
    date = _iso_or_none(match.group("date"))
    if not date:
        return {"parsed": False, "scheme": "agenda-packet",
                "reason": f"invalid-iso-date:{match.group('date')}", "raw": filename}
    part = PACKET_PART_RE.search(filename)
    stem = filename.rsplit(".", 1)[0]
    residue = PACKET_ISO_RE.sub("", stem)
    residue = PACKET_PART_RE.sub("", residue).strip("_- ")
    return {
        "parsed": True,
        "scheme": "agenda-packet",
        "date": date,
        "date_ambiguous": False,
        "body": "city-council",
        "body_raw": "Cheyenne City Council (inferred from CHEY- packet prefix)",
        "packet_part": int(part.group("part")) if part else None,
        "label": _slug(residue) if residue else None,
        "raw": filename,
    }


def parse_date_subdir(path: str, body: str, body_raw: str, scheme: str) -> dict:
    """planning-commission/2024-01-11/Agenda.pdf and Board_of_County_Commissioners/…"""
    parts = path.split("/")
    if len(parts) < 3:
        return {"parsed": False, "scheme": scheme,
                "reason": "no-date-subdirectory", "raw": path}
    date = _iso_or_none(parts[1])
    if not date:
        return {"parsed": False, "scheme": scheme,
                "reason": f"non-iso-subdirectory:{parts[1]}", "raw": path}
    return {"parsed": True, "scheme": scheme, "date": date, "date_ambiguous": False,
            "body": body, "body_raw": body_raw, "raw": path}


# municipal-docs/ is the one genuinely ambiguous scheme. Both shapes occur:
#   cow-05-21-2025-agenda.pdf  -> month=05 day=21 year=2025  (month-first)
#   cow-02-23-22-agenda.pdf    -> month=02 day=23 year=2022   (month-first, 2-digit year)
# The two-digit form is only readable as month-first because 23 cannot be a
# month, but that is an inference from one field, not a guarantee across the
# corpus. A file named cow-03-04-22 would be genuinely undecidable, so any
# record where both fields are <= 12 is flagged ambiguous rather than guessed.
# Every numeric component is greedy and the year carries a `not followed by a
# digit` guard. A lazy or unguarded pattern lets "cow-06-04-2025" match as
# month=06 day=0 year=4-20 and emit 2020-06-04: a plausible, wrong, undetectable
# date. Verified against cow-06-04-2025, cow-02-23-22, fc-01-04-22, psc-sm-05-22-23.
COW_RE = re.compile(
    r"(?P<prefix>cow|fc|psc|ws|bopu|city)(?:-[a-z]+)*"
    r"-(?P<a>\d{1,2})-(?P<b>\d{1,2})-(?P<year>\d{4}|\d{2})(?!\d)",
    re.I)


def parse_municipal_docs(path: str) -> dict:
    filename = path.rsplit("/", 1)[-1]
    match = COW_RE.search(filename)
    if not match:
        return {"parsed": False, "scheme": "municipal-docs",
                "reason": "no-body-prefix-date-in-filename", "raw": filename}
    prefix = match.group("prefix").lower()
    body, body_raw = MUNICIPAL_BODIES.get(prefix, (_slug(prefix), prefix.upper()))
    a, b = int(match.group("a")), int(match.group("b"))
    year_raw = match.group("year")
    year = int(year_raw) if len(year_raw) == 4 else 2000 + int(year_raw)
    ambiguous = a <= 12 and b <= 12
    if b > 12 >= a:
        month, day = a, b
    elif a > 12 >= b:
        month, day = b, a
    elif ambiguous:
        # Both readings are calendrically valid. Assume month-first because every
        # unambiguous record in this directory is month-first, but SAY SO.
        month, day = a, b
    else:
        return {"parsed": False, "scheme": "municipal-docs",
                "reason": f"neither-field-is-a-month:{a},{b}", "raw": filename}
    try:
        date = dt.date(year, month, day).isoformat()
    except ValueError as exc:
        return {"parsed": False, "scheme": "municipal-docs",
                "reason": f"impossible-date:{exc}", "raw": filename}
    stem = filename.rsplit(".", 1)[0]
    label = _slug(COW_RE.sub("", stem).strip("-_ "))
    return {
        "parsed": True, "scheme": "municipal-docs", "date": date,
        "date_ambiguous": ambiguous,
        "date_ambiguity_note": ("month-first assumed from unambiguous siblings; both "
                                f"{a:02d} and {b:02d} are valid months"
                                if ambiguous else None),
        "two_digit_year": len(year_raw) == 2,
        "body": body,
        "body_raw": f"{body_raw} (inferred from {prefix}- filename prefix)",
        "body_prefix": prefix,
        "label": label or None,
        "raw": filename,
    }


def parse_record_path(path: str) -> dict:
    """Dispatch a tracked path to the parser that matches its scheme."""
    head, _, rest = path.partition("/")
    if not rest:
        return {"parsed": False, "scheme": "repo-root-file",
                "reason": "repository-root-file-not-a-meeting-record", "raw": path}
    if head == "agenda-packets":
        return parse_agenda_packet(path)
    if head == "municipal-docs":
        return parse_municipal_docs(path)
    if head == "planning-commission":
        return parse_date_subdir(path, "planning-commission",
                                 "Planning Commission", "planning-commission")
    if head == "Board_of_County_Commissioners":
        return parse_date_subdir(path, "board-of-county-commissioners",
                                 "Board of County Commissioners", "county-commissioners")
    return parse_epoch_folder(head)


def classify_document(filename: str) -> str:
    """Classify by file name, after normalising separators.

    Normalisation is load-bearing: archive names are underscore-joined
    ("CHEY-2012-10-22_Minutes.pdf") and `_` is a word character, so a raw
    \bminutes\b search finds no boundary and silently returns "other". Replacing
    every non-alphanumeric run with a space makes the word boundaries real.
    """
    stem = filename.rsplit(".", 1)[0]
    spaced = re.sub(r"[^A-Za-z0-9]+", " ", stem)
    for label, pattern in DOC_PATTERNS:
        if pattern.search(spaced):
            return label
    return "other"


def source_locator(repo: str, path: str, ref: str = "HEAD") -> dict:
    """A citation a researcher can actually follow, with the URL percent-encoded.

    Archive paths contain spaces and commas, so an unencoded URL is broken in
    every browser and every Markdown renderer.
    """
    encoded = urllib.parse.quote(path)
    return {
        "repository": repo,
        "ref": ref,
        "path": path,
        "raw_url": f"{RAW_ROOT}/{repo}/{ref}/{encoded}",
        "github_url": f"https://github.com/{repo}/blob/{ref}/{encoded}",
    }


# --------------------------------------------------------------------------
# stage: catalog
# --------------------------------------------------------------------------

def enumerate_repo(repo: str) -> tuple[list[dict], dict]:
    """List every blob in a repo via the trees API. Reports truncation honestly."""
    data = api_json(f"{API_ROOT}/repos/{repo}/git/trees/HEAD?recursive=1")
    truncated = bool(data.get("truncated"))
    blobs = [e for e in data.get("tree", []) if e.get("type") == "blob"]
    meta = {
        "repository": repo,
        "truncated": truncated,
        "blob_count": len(blobs),
        "blob_bytes": sum(int(b.get("size") or 0) for b in blobs),
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    return blobs, meta


def build_catalog(repos: tuple[str, ...] = ARCHIVE_REPOS,
                  progress=sys.stderr) -> dict:
    records: list[dict] = []
    repo_meta: list[dict] = []
    parse_failures: list[dict] = []
    date_conflicts: list[dict] = []
    ambiguous_dates: list[dict] = []

    for repo in repos:
        print(f"enumerating {repo} …", file=progress)
        blobs, meta = enumerate_repo(repo)
        if meta["truncated"]:
            print(f"  WARNING: {repo} tree was TRUNCATED by the API — catalog is "
                  f"incomplete for this repository", file=progress)
        for blob in blobs:
            path = blob["path"]
            size = int(blob.get("size") or 0)
            folder = path.split("/", 1)[0]
            parsed = parse_record_path(path)
            filename = path.rsplit("/", 1)[-1]
            ext = os.path.splitext(filename)[1].lower()
            doc_class = classify_document(filename)
            record = {
                "id": hashlib.sha256(f"{repo}\0{path}".encode()).hexdigest()[:24],
                "repository": repo,
                "path": path,
                "filename": filename,
                "bytes": size,
                "blob_sha": blob.get("sha"),
                "extension": ext,
                "document_class": doc_class,
                "meeting_folder": folder,
                "folder_parsed": parsed["parsed"],
                "scheme": parsed.get("scheme"),
            }
            if parsed["parsed"]:
                record.update({
                    "meeting_date": parsed["date"],
                    "body": parsed.get("body"),
                    "body_raw": parsed.get("body_raw"),
                    "date_ambiguous": bool(parsed.get("date_ambiguous")),
                })
                if parsed.get("date_epoch_utc"):
                    record["meeting_date_epoch_utc"] = parsed["date_epoch_utc"]
                    record["meeting_epoch"] = parsed.get("epoch")
                    record["date_conflict"] = bool(parsed.get("date_conflict"))
                for optional in ("packet_part", "label", "two_digit_year",
                                 "date_ambiguity_note", "body_prefix",
                                 "attachment_tier", "date_pretty_in_dir"):
                    if parsed.get(optional) is not None:
                        record[optional] = parsed[optional]
                if parsed.get("date_conflict"):
                    date_conflicts.append({
                        "repository": repo, "path": path, "scheme": parsed.get("scheme"),
                        "authoritative_says": parsed.get("date_epoch_utc") or parsed["date"],
                        "secondary_says": (parsed.get("date_pretty_in_dir")
                                           or parsed["date"]),
                        "delta_days": parsed.get("date_conflict_days"),
                    })
                if parsed.get("date_ambiguous"):
                    ambiguous_dates.append({
                        "repository": repo, "path": path, "date": parsed["date"],
                        "note": parsed.get("date_ambiguity_note")})
            else:
                record["folder_parse_reason"] = parsed["reason"]
                parse_failures.append({
                    "repository": repo, "folder": folder, "path": path,
                    "scheme": parsed.get("scheme"), "reason": parsed["reason"]})
            record.update(source_locator(repo, path))
            records.append(record)
        repo_meta.append(meta)

    by_class: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    by_body: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    by_ext: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    by_year: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    for r in records:
        for table, key in ((by_class, r["document_class"]),
                           (by_ext, r["extension"] or "(none)"),
                           (by_body, r.get("body") or "(unparsed-folder)")):
            table[key]["files"] += 1
            table[key]["bytes"] += r["bytes"]
        if r.get("meeting_date"):
            year = r["meeting_date"][:4]
            by_year[year]["files"] += 1
            by_year[year]["bytes"] += r["bytes"]

    by_scheme: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    for r in records:
        by_scheme[r.get("scheme") or "unparsed"]["files"] += 1
        by_scheme[r.get("scheme") or "unparsed"]["bytes"] += r["bytes"]

    dates = sorted(r["meeting_date"] for r in records if r.get("meeting_date"))
    return {
        "schema": "archive-catalog-v1",
        "generated_by": "tools/archive_index.py catalog",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "repositories": repo_meta,
        "totals": {
            "records": len(records),
            "bytes": sum(r["bytes"] for r in records),
            "truncated_repositories": [m["repository"] for m in repo_meta if m["truncated"]],
            "folders_parsed": sum(1 for r in records if r["folder_parsed"]),
            "folders_unparsed": len(parse_failures),
            "distinct_meeting_folders": len({r["meeting_folder"] for r in records}),
            "distinct_meeting_folders_parsed":
                len({r["meeting_folder"] for r in records if r["folder_parsed"]}),
            "date_conflicts": len(date_conflicts),
            "earliest_meeting_date": dates[0] if dates else None,
            "latest_meeting_date": dates[-1] if dates else None,
            "distinct_meeting_dates": len(set(dates)),
            "distinct_bodies": len({r.get("body") for r in records if r.get("body")}),
            "ambiguous_dates": len(ambiguous_dates),
            "two_digit_year_records": sum(1 for r in records if r.get("two_digit_year")),
            "undated_records": sum(1 for r in records if not r.get("meeting_date")),
        },
        "by_scheme": sorted(({"key": k, **v} for k, v in by_scheme.items()),
                            key=lambda d: -d["bytes"]),
        "by_document_class": sorted(({"key": k, **v} for k, v in by_class.items()),
                                    key=lambda d: -d["bytes"]),
        "by_body": sorted(({"key": k, **v} for k, v in by_body.items()),
                          key=lambda d: -d["bytes"]),
        "by_extension": sorted(({"key": k, **v} for k, v in by_ext.items()),
                               key=lambda d: -d["bytes"]),
        "by_year": sorted(({"key": k, **v} for k, v in by_year.items()), key=lambda d: d["key"]),
        "folder_parse_failure_summary": [
            {"reason": reason, "occurrences": count}
            for reason, count in collections.Counter(
                f["reason"] for f in parse_failures).most_common()],
        "folder_parse_failures_sample": sorted(
            {f.get("path") or f["folder"] for f in parse_failures})[:100],
        "folder_parse_failures_distinct": len({f["folder"] for f in parse_failures}),
        "date_conflicts": date_conflicts[:200],
        "ambiguous_dates": ambiguous_dates[:200],
        "records": records,
    }


def datapackage(catalog: dict) -> dict:
    """Emit a Frictionless Data Package descriptor for the catalog.

    Frictionless is chosen because it is a published standard that existing
    civic-data tooling already reads, and because its `schema` block forces an
    explicit type per field — which is exactly the guard the ecosystem lacks
    (a scraped Windows Media Player error string is currently a `date` field in
    a sibling repository). Source-local IDs are preserved verbatim: `path`,
    `blob_sha` and `repository` are never renamed or rewritten.
    """
    fields = [
        {"name": "id", "type": "string", "constraints": {"required": True, "minLength": 24,
                                                         "maxLength": 24},
         "description": "Stable derived record ID: sha256(repository + NUL + path)[:24]."},
        {"name": "repository", "type": "string", "constraints": {"required": True,
                                                                 "enum": list(ARCHIVE_REPOS)},
         "description": "Source-local repository. Preserved verbatim."},
        {"name": "path", "type": "string", "constraints": {"required": True},
         "description": "Source-local path. Preserved verbatim, spaces and commas included."},
        {"name": "filename", "type": "string", "constraints": {"required": True}},
        {"name": "bytes", "type": "integer", "constraints": {"required": True, "minimum": 0}},
        {"name": "blob_sha", "type": "string",
         "description": "Git blob SHA-1 from the trees API. Content-addressed provenance."},
        {"name": "extension", "type": "string"},
        {"name": "document_class", "type": "string", "constraints": {
            "enum": [label for label, _ in DOC_PATTERNS] + ["other"]},
            "description": "Inferred from the file name. 'other' means unrecognised, not absent."},
        {"name": "meeting_date", "type": "date", "format": "%Y-%m-%d",
         "description": "Parsed from the folder's pretty date, cross-checked against the epoch."},
        {"name": "meeting_date_epoch_utc", "type": "date", "format": "%Y-%m-%d",
         "description": "Parsed from the folder's leading unix epoch. Authoritative for ordering."},
        {"name": "meeting_epoch", "type": "integer", "minimum": 0},
        {"name": "body", "type": "string",
         "description": "Normalised meeting body. Unnormalised values stay verbatim."},
        {"name": "body_raw", "type": "string"},
        {"name": "date_conflict", "type": "boolean",
         "description": "True when the epoch and the pretty date disagree by more than a day."},
        {"name": "folder_parsed", "type": "boolean", "constraints": {"required": True}},
        {"name": "scheme", "type": "string", "constraints": {"required": True,
                                                             "enum": list(SCHEMES)},
         "description": "Which path parser produced this record's date."},
        {"name": "date_ambiguous", "type": "boolean",
         "description": "True when the source name does not determine a unique date."},
        {"name": "packet_part", "type": "integer", "minimum": 0},
        {"name": "body_prefix", "type": "string",
         "description": "Filename prefix that identified the meeting body."},
        {"name": "attachment_tier", "type": "string"},
        {"name": "label", "type": "string"},
        {"name": "raw_url", "type": "string", "format": "uri"},
        {"name": "github_url", "type": "string", "format": "uri"},
    ]
    return {
        "name": "cheyenne-council-archive-catalog",
        "title": "Cheyenne City Council public records archive catalog, 2008-2026",
        "licenses": [{"name": "CC0-1.0",
                      "title": "Public records; catalog metadata waived to the public domain."}],
        "sources": [{"title": r["repository"],
                     "path": f"https://github.com/{r['repository']}"}
                    for r in catalog["repositories"]],
        "created": catalog["generated_at"],
        "resources": [{
            "name": "archive-catalog",
            "path": "catalog.json",
            "format": "json",
            "mediatype": "application/json",
            "schema": {"fields": fields, "primaryKey": "id"},
            "stats": {
                "records": catalog["totals"]["records"],
                "bytes": catalog["totals"]["bytes"],
            },
        }],
        "custom": {
            "provenance": {
                "method": "GitHub Git trees API, recursive, at HEAD",
                "truncated_repositories": catalog["totals"]["truncated_repositories"],
                "date_derivation": "epoch prefix authoritative; pretty date cross-checked",
                "text_extraction": "not performed by the catalog stage",
            },
            "completeness": {
                "full_historical_coverage": False,
                "statement": ("Enumerates every blob the trees API returned at generation time "
                              "for the six declared repositories. It does not establish that "
                              "those repositories contain every Cheyenne council record, and "
                              "no repository here is a system of record."),
            },
        },
    }


def stage_catalog(args) -> int:
    catalog = build_catalog(tuple(args.repo) if args.repo else ARCHIVE_REPOS)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "catalog.json").write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8")
    (out / "datapackage.json").write_text(json.dumps(datapackage(catalog), indent=2) + "\n",
                                          encoding="utf-8")
    t = catalog["totals"]
    print(f"cataloged {t['records']:,} blobs / {t['bytes']:,} bytes "
          f"({t['bytes'] / 1e9:.2f} GB) across {len(catalog['repositories'])} repositories")
    print(f"  meeting dates  {t['distinct_meeting_dates']:,} distinct "
          f"({t['earliest_meeting_date']} → {t['latest_meeting_date']})")
    print(f"  bodies         {t['distinct_bodies']:,}")
    print(f"  dated records {t['records'] - t['undated_records']:,} of {t['records']:,}   "
          f"undated {t['undated_records']:,}   ambiguous {t['ambiguous_dates']:,}   "
          f"conflicts {t['date_conflicts']:,}")
    print("  by path scheme:")
    for row in catalog["by_scheme"]:
        print(f"    {row['key']:24s} {row['files']:5,d} files  {row['bytes'] / 1e9:6.2f} GB")
    if t["undated_records"]:
        print("  UNPARSED REASONS:")
        for row in catalog.get("folder_parse_failure_summary", [])[:8]:
            print(f"    {row['occurrences']:6,d}  {row['reason']}")
    if t["ambiguous_dates"]:
        print(f"  NOTE: {t['ambiguous_dates']:,} records carry an AMBIGUOUS date — both "
              f"numeric fields are valid months. Month-first was assumed from unambiguous "
              f"siblings and flagged, never silently guessed.")
    if t["two_digit_year_records"]:
        print(f"  NOTE: {t['two_digit_year_records']:,} records use a two-digit year and "
              f"were resolved as 20xx.")
    if t["truncated_repositories"]:
        print(f"  WARNING truncated: {', '.join(t['truncated_repositories'])}")
    print(f"  wrote {out}/catalog.json and {out}/datapackage.json")
    return 0


# --------------------------------------------------------------------------
# stage: extract
# --------------------------------------------------------------------------

def load_catalog(out: Path) -> dict:
    fp = out / "catalog.json"
    if not fp.exists():
        raise SystemExit(f"no catalog at {fp} — run `archive_index.py catalog` first")
    return json.loads(fp.read_text(encoding="utf-8"))


def pdf_text(data: bytes) -> tuple[str, str]:
    """Return (text, method). Never raises: a broken PDF is a finding."""
    try:
        import pypdf  # noqa: PLC0415  (optional dependency, imported lazily)
    except ImportError:
        return "", "unavailable:pypdf-not-installed"
    try:
        import io
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return "", "failed:encrypted"
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        text = "\n".join(pages)
    except Exception as exc:
        return "", f"failed:{type(exc).__name__}"
    method = f"pypdf-{getattr(pypdf, '__version__', 'unknown')}"
    if not text.strip():
        # A PDF that parses cleanly but yields no text is scanned imagery. That
        # is a different finding from a parse failure and must not be conflated.
        return "", f"image-only-needs-ocr:{method}"
    return text, f"text-layer:{method}"


def stage_extract(args) -> int:
    out = Path(args.out)
    cache = out / "text"
    cache.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(out)
    records = catalog["records"]

    if args.body:
        records = [r for r in records if r.get("body") in set(args.body)]
    if args.year:
        years = set(args.year)
        records = [r for r in records if (r.get("meeting_date") or "")[:4] in years]
    if args.doc_class:
        classes = set(args.doc_class)
        records = [r for r in records if r["document_class"] in classes]
    records = [r for r in records if r["extension"] == ".pdf"]
    records.sort(key=lambda r: (r.get("meeting_date") or "", r["path"]))

    state_fp = out / "extract-state.json"
    state = json.loads(state_fp.read_text()) if state_fp.exists() else {"documents": {}}

    todo = []
    for r in records:
        cached = cache / f"{r['id']}.json.gz"
        if cached.exists():
            continue
        todo.append(r)
        if args.limit and len(todo) >= args.limit:
            break

    fetched_bytes = 0
    ok = failed = image_only = 0
    for i, r in enumerate(todo, start=1):
        if args.max_bytes and fetched_bytes >= args.max_bytes:
            print(f"  stopping: --max-bytes {args.max_bytes:,} reached", file=sys.stderr)
            break
        try:
            data, transport = fetch_blob(r, timeout=args.timeout)
        except Exception as exc:  # noqa: BLE001 - a fetch failure is a finding
            failed += 1
            state["documents"][r["id"]] = {
                "path": r["path"], "repository": r["repository"],
                "method": f"fetch-failed:{str(exc)[:160]}", "chars": 0}
            print(f"  [{i}/{len(todo)}] FETCH FAILED {r['path'][:70]} — {exc}", file=sys.stderr)
            time.sleep(args.delay)
            continue
        fetched_bytes += len(data)
        text, method = pdf_text(data)
        if method.startswith("image-only"):
            image_only += 1
        elif method.startswith("failed") or method.startswith("unavailable"):
            failed += 1
        else:
            ok += 1
        payload = {
            "id": r["id"], "repository": r["repository"], "path": r["path"],
            "meeting_date": r.get("meeting_date"), "body": r.get("body"),
            "document_class": r["document_class"], "bytes": r["bytes"],
            "blob_sha": r.get("blob_sha"), "method": method, "transport": transport,
            "chars": len(text), "text": text,
            "raw_url": r["raw_url"], "github_url": r["github_url"],
            "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        with gzip.open(cache / f"{r['id']}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(payload, fh)
        state["documents"][r["id"]] = {
            "path": r["path"], "repository": r["repository"], "method": method,
            "chars": len(text)}
        print(f"  [{i}/{len(todo)}] {method.split(':')[0]:22s} {len(text):7,d} chars  "
              f"{r.get('meeting_date') or '????-??-??'}  {r['filename'][:52]}", file=sys.stderr)
        if args.delay:
            time.sleep(args.delay)

    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    state_fp.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    print(f"\nextracted this run: {ok} with text, {image_only} image-only (needs OCR), "
          f"{failed} failed; {fetched_bytes:,} bytes fetched")
    print(f"cached total: {len(state['documents']):,} of {len(records):,} matching records "
          f"({100 * len(state['documents']) / max(len(records), 1):.1f}%)")
    if image_only:
        print(f"NOTE: {image_only} documents are scanned imagery. They are recorded, not "
              f"silently dropped — an OCR pass is required to make them searchable.")
    return 0


# --------------------------------------------------------------------------
# stage: index
# --------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower())
            if len(t) >= MIN_TOKEN_LEN and t not in STOPWORDS]


def shard_of(token: str) -> int:
    return int(hashlib.sha256(token.encode()).hexdigest(), 16) % SHARD_COUNT


def stage_index(args) -> int:
    out = Path(args.out)
    cache = out / "text"
    index_dir = out / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        raise SystemExit(f"no extracted text at {cache} — run `archive_index.py extract` first")

    postings: dict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    doc_meta: list[dict] = []
    lengths: dict[str, int] = {}

    files = sorted(cache.glob("*.json.gz"))
    for fp in files:
        with gzip.open(fp, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        text = doc.get("text") or ""
        tokens = tokenize(text)
        if not tokens:
            doc_meta.append({
                "id": doc["id"], "path": doc["path"], "repository": doc["repository"],
                "meeting_date": doc.get("meeting_date"), "body": doc.get("body"),
                "document_class": doc.get("document_class"), "chars": 0, "tokens": 0,
                "searchable": False, "method": doc.get("method"),
                "raw_url": doc.get("raw_url"), "github_url": doc.get("github_url")})
            continue
        tf = collections.Counter(tokens)
        lengths[doc["id"]] = len(tokens)
        for token, count in tf.items():
            postings[token][doc["id"]].append(count)
        doc_meta.append({
            "id": doc["id"], "path": doc["path"], "repository": doc["repository"],
            "meeting_date": doc.get("meeting_date"), "body": doc.get("body"),
            "document_class": doc.get("document_class"), "chars": len(text),
            "tokens": len(tokens), "distinct_tokens": len(tf), "searchable": True,
            "method": doc.get("method"),
            "raw_url": doc.get("raw_url"), "github_url": doc.get("github_url")})

    shards: list[dict] = []
    for i in range(SHARD_COUNT):
        shard_tokens = {t: dict(d) for t, d in postings.items() if shard_of(t) == i}
        if not shard_tokens:
            continue
        fp = index_dir / f"shard-{i:02d}.json.gz"
        with gzip.open(fp, "wt", encoding="utf-8") as fh:
            json.dump(shard_tokens, fh)
        shards.append({"shard": i, "path": str(fp.relative_to(out)),
                       "tokens": len(shard_tokens),
                       "postings": sum(len(d) for d in shard_tokens.values()),
                       "bytes": fp.stat().st_size})

    total_tokens = sum(lengths.values())
    avg_len = total_tokens / max(len(lengths), 1)
    stats = {
        "schema": "archive-index-stats-v1",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "documents": len(doc_meta),
        "searchable_documents": sum(1 for d in doc_meta if d["searchable"]),
        "unsearchable_documents": sum(1 for d in doc_meta if not d["searchable"]),
        "distinct_tokens": len(postings),
        "total_tokens": total_tokens,
        "average_document_length_tokens": round(avg_len, 2),
        "shard_count": len(shards),
        "shards": shards,
        "index_bytes": sum(s["bytes"] for s in shards),
    }
    with gzip.open(index_dir / "docs.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(doc_meta, fh)
    (index_dir / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    (out / "bm25-params.json").write_text(json.dumps(
        {"k1": args.k1, "b": args.b, "avgdl": avg_len, "N": len(lengths),
         "doc_lengths": lengths}, indent=1) + "\n", encoding="utf-8")

    print(f"indexed {stats['searchable_documents']:,} searchable documents "
          f"({stats['unsearchable_documents']:,} unsearchable) → "
          f"{stats['distinct_tokens']:,} distinct tokens across {len(shards)} shards")
    print(f"  index size {stats['index_bytes']:,} bytes")
    return 0


# --------------------------------------------------------------------------
# stage: search
# --------------------------------------------------------------------------

def bm25_search(query: str, out: Path, k: int = 10, k1: float = 1.5, b: float = 0.75,
                body: str | None = None, year: str | None = None,
                doc_class: str | None = None) -> dict:
    index_dir = out / "index"
    stats_fp = index_dir / "stats.json"
    if not stats_fp.exists():
        raise SystemExit(f"no index at {index_fp_name(index_dir)} — run `archive_index.py index`")
    stats = json.loads(stats_fp.read_text())
    params = json.loads((out / "bm25-params.json").read_text())
    with gzip.open(index_dir / "docs.json.gz", "rt", encoding="utf-8") as fh:
        doc_meta = {d["id"]: d for d in json.load(fh)}
    lengths = params["doc_lengths"]
    avgdl = params["avgdl"] or 1.0
    N = params["N"] or 1

    tokens = sorted(set(tokenize(query)))
    if not tokens:
        return {"query": query, "tokens": [], "hits": [], "total": 0,
                "note": "query produced no searchable tokens"}

    wanted_shards = sorted({shard_of(t) for t in tokens})
    shard_data: dict[int, dict] = {}
    for i in wanted_shards:
        fp = index_dir / f"shard-{i:02d}.json.gz"
        if fp.exists():
            with gzip.open(fp, "rt", encoding="utf-8") as fh:
                shard_data[i] = json.load(fh)

    scores: dict[str, float] = collections.defaultdict(float)
    matched: dict[str, list[str]] = collections.defaultdict(list)
    for token in tokens:
        shard = shard_data.get(shard_of(token), {})
        postings = shard.get(token)
        if not postings:
            continue
        df = len(postings)
        idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
        for doc_id, counts in postings.items():
            tf = sum(counts)
            dl = lengths.get(doc_id, avgdl)
            denom = tf + k1 * (1 - b + b * (dl / avgdl))
            scores[doc_id] += idf * (tf * (k1 + 1)) / denom
            matched[doc_id].append(token)

    filtered = []
    for doc_id, score in scores.items():
        meta = doc_meta.get(doc_id)
        if not meta:
            continue
        if body and meta.get("body") != body:
            continue
        if year and not (meta.get("meeting_date") or "").startswith(year):
            continue
        if doc_class and meta.get("document_class") != doc_class:
            continue
        filtered.append((score, doc_id, meta))
    filtered.sort(key=lambda t: (-t[0], t[2].get("meeting_date") or "", t[1]))

    hits = []
    for score, doc_id, meta in filtered[:k]:
        hits.append({
            "score": round(score, 4),
            "matched_tokens": sorted(matched[doc_id]),
            "token_coverage": round(len(matched[doc_id]) / len(tokens), 3),
            **{key: meta.get(key) for key in
               ("id", "meeting_date", "body", "document_class", "path", "repository",
                "raw_url", "github_url", "method")},
        })
    return {
        "query": query,
        "tokens": tokens,
        "total": len(filtered),
        "returned": len(hits),
        "hits": hits,
        "index_built_at": stats["built_at"],
        "searchable_documents": stats["searchable_documents"],
        "coverage_warning": (
            f"Only {stats['searchable_documents']:,} of {stats['documents']:,} extracted "
            f"documents are searchable, and extraction may cover only part of the catalog. "
            f"Absence of a hit is NOT evidence that the archive does not contain it."
            if stats["unsearchable_documents"] else
            "Extraction may cover only part of the catalog. Absence of a hit is NOT "
            "evidence that the archive does not contain it."),
    }


def index_fp_name(index_dir: Path) -> str:
    return str(index_dir / "stats.json")


def stage_search(args) -> int:
    result = bm25_search(args.query, Path(args.out), k=args.k, body=args.body,
                         year=args.year, doc_class=args.doc_class)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"query: {result['query']!r}  tokens: {', '.join(result['tokens']) or '(none)'}")
    print(f"matches: {result['total']:,}   showing {result['returned']}")
    for i, h in enumerate(result["hits"], start=1):
        print(f"\n{i}. score {h['score']}  coverage {h['token_coverage']}  "
              f"[{','.join(h['matched_tokens'])}]")
        print(f"   {h['meeting_date'] or '????-??-??'}  {h['body'] or '?'}  "
              f"{h['document_class']}")
        print(f"   {h['repository']}: {h['path'][:110]}")
        print(f"   {h['raw_url'][:130]}")
    print(f"\nWARNING: {result['coverage_warning']}")
    return 0


def stage_coverage(args) -> int:
    out = Path(args.out)
    catalog = load_catalog(out)
    state_fp = out / "extract-state.json"
    state = json.loads(state_fp.read_text()) if state_fp.exists() else {"documents": {}}
    stats_fp = out / "index" / "stats.json"
    stats = json.loads(stats_fp.read_text()) if stats_fp.exists() else None

    total = len(catalog["records"])
    pdfs = sum(1 for r in catalog["records"] if r["extension"] == ".pdf")
    extracted = len(state["documents"])
    methods = collections.Counter(d["method"].split(":")[0] for d in state["documents"].values())
    report = {
        "schema": "archive-coverage-v1",
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "catalog": {
            "records": total,
            "bytes": catalog["totals"]["bytes"],
            "pdf_records": pdfs,
            "repositories": len(catalog["repositories"]),
            "truncated_repositories": catalog["totals"]["truncated_repositories"],
            "folders_unparsed": catalog["totals"]["folders_unparsed"],
            "distinct_meeting_folders": catalog["totals"]["distinct_meeting_folders"],
            "distinct_meeting_folders_parsed":
                catalog["totals"]["distinct_meeting_folders_parsed"],
            "folder_parse_failure_summary":
                catalog["totals"].get("folder_parse_failure_summary", []),
            "date_conflicts": catalog["totals"]["date_conflicts"],
            "date_range": [catalog["totals"]["earliest_meeting_date"],
                           catalog["totals"]["latest_meeting_date"]],
        },
        "extraction": {
            "documents": extracted,
            "pdf_coverage_percent": round(100 * extracted / pdfs, 2) if pdfs else 0.0,
            "by_method": dict(methods),
        },
        "index": ({
            "searchable_documents": stats["searchable_documents"],
            "unsearchable_documents": stats["unsearchable_documents"],
            "distinct_tokens": stats["distinct_tokens"],
        } if stats else None),
        "honest_statement": (
            "Coverage is reported per stage because a single percentage would hide which "
            "stage is incomplete. Enumeration is complete for the six declared repositories "
            "(no truncation reported). Extraction and indexing cover only what has actually "
            "been fetched. Nothing here establishes that these repositories contain every "
            "Cheyenne council record."),
    }
    (out / "coverage.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="stage", required=True)

    c = sub.add_parser("catalog", help="enumerate all archive repos (no content download)")
    c.add_argument("--out", default="data/archive-index")
    c.add_argument("--repo", action="append", help="restrict to a repo (repeatable)")
    c.set_defaults(func=stage_catalog)

    e = sub.add_parser("extract", help="fetch PDFs and extract text (resumable, bounded)")
    e.add_argument("--out", default="data/archive-index")
    e.add_argument("--limit", type=int, default=0, help="max documents to fetch this run")
    e.add_argument("--max-bytes", type=int, default=0, help="stop after this many fetched bytes")
    e.add_argument("--body", action="append", help="restrict to a meeting body (repeatable)")
    e.add_argument("--year", action="append", help="restrict to a year (repeatable)")
    e.add_argument("--doc-class", action="append", help="restrict to a document class")
    e.add_argument("--delay", type=float, default=1.0, help="seconds between fetches")
    e.add_argument("--timeout", type=int, default=60)
    e.set_defaults(func=stage_extract)

    i = sub.add_parser("index", help="build the sharded BM25 index over extracted text")
    i.add_argument("--out", default="data/archive-index")
    i.add_argument("--k1", type=float, default=1.5)
    i.add_argument("--b", type=float, default=0.75)
    i.set_defaults(func=stage_index)

    s = sub.add_parser("search", help="query the index")
    s.add_argument("query")
    s.add_argument("--out", default="data/archive-index")
    s.add_argument("--k", type=int, default=10)
    s.add_argument("--body")
    s.add_argument("--year")
    s.add_argument("--doc-class")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=stage_search)

    v = sub.add_parser("coverage", help="report per-stage coverage honestly")
    v.add_argument("--out", default="data/archive-index")
    v.set_defaults(func=stage_coverage)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
