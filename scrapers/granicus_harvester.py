#!/usr/bin/env python3
"""Granicus agenda/attachment harvester: idempotent, bounded and resumable.

What changed on 2026-11-13 and why (see tests/test_granicus_harvester.py):

* The scheduled "Promethean Recurring Harvest" never finished. It walked every
  agenda and every attachment of two Granicus views on each run, with no time
  budget, was killed by GitHub at the six-hour job limit, and therefore never
  reached its commit step. A run now has a wall-clock budget, a cap on new
  documents, a delay between requests, and a progress table so the next run
  continues where this one stopped instead of starting over.
* The same file published under two URLs hit the UNIQUE constraint on
  ``attachment_sha256``. The exception was caught one level too high, so the
  remaining attachments of that agenda were skipped. Inserts are now
  ``ON CONFLICT DO NOTHING`` per document and the second URL is recorded as an
  alias of the first.
* "Promethean Autonomous Granicus Harvester" passed ``--committee`` and
  ``--date``, which this script did not accept (argparse exit 2), and did not
  install pdfplumber/pytesseract/pdf2image, which were imported at module
  level. Both options exist now and the PDF/OCR libraries are optional.
* A fresh database lacked ``robots_advisory_ignored`` and
  ``document_tamper_log``. The schema is ensured here on every start.

Unchanged on purpose: the tamper check (a known URL whose bytes change is
logged, never overwritten), the hash column (SHA-512 for new rows, legacy
SHA-256 rows upgraded in place once re-verified), the artifacts layout, and
the robots policy (robots.txt is read and the result is recorded per row in
``robots_advisory_ignored``; pass ``--respect-robots`` to stop instead).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
SCHEMA_PATH = REPO_ROOT / "database" / "schema_rhetorical_profiling.sql"
HEADERS = {"User-Agent": "Promethean_CivicWatch_Auditor/4.4 (+https://github.com/bartimoussmith-oss/therealwindycity)"}

AGENDA_LINK_RE = re.compile(
    r'((?:https?:)?//[^"\'\s<>]+/(?:GeneratedAgendaViewer|AgendaViewer|MinutesViewer)\.php\?[^"\'\s<>]+)', re.I)
PDF_LINK_RE = re.compile(r'href=["\']([^"\']+(?:meta_id=|ViewAttachment|\.pdf)[^"\']*)["\']', re.I)
HTML_PDF_RE = re.compile(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', re.I)

DEFAULT_MAX_SECONDS = float(os.environ.get("HARVEST_MAX_SECONDS", "1200"))   # 20 minutes per invocation
DEFAULT_MAX_NEW = int(os.environ.get("HARVEST_MAX_NEW", "200"))              # new documents per invocation
DEFAULT_DELAY = float(os.environ.get("HARVEST_DELAY_SECONDS", "2.0"))        # pause between requests
MAX_PDF_BYTES = int(os.environ.get("HARVEST_MAX_PDF_BYTES", str(60 * 1024 * 1024)))
MAX_OCR_PAGES = int(os.environ.get("HARVEST_MAX_OCR_PAGES", "25"))

# Additive migrations. Every statement is safe to run on every start.
_MIGRATIONS = (
    """CREATE TABLE IF NOT EXISTS document_tamper_log (
        tamper_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER, source_url TEXT, original_hash TEXT, new_hash TEXT,
        detected_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    # One row per (url, new_hash): re-running after a change is detected must not log it again.
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_tamper_once
        ON document_tamper_log (source_url, new_hash)""",
    """CREATE TABLE IF NOT EXISTS document_aliases (
        source_url TEXT PRIMARY KEY, item_id INTEGER NOT NULL, content_hash TEXT NOT NULL,
        first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS harvest_progress (
        endpoint_url TEXT PRIMARY KEY, root_url TEXT NOT NULL, status TEXT NOT NULL,
        documents_seen INTEGER DEFAULT 0, last_crawled_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_governance_source_url ON governance_items (source_url)""",
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create or upgrade the tables this harvester writes to. Idempotent."""
    has_items = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='governance_items'").fetchone()
    if not has_items:
        if not SCHEMA_PATH.exists():
            raise RuntimeError(f"governance_items is missing and {SCHEMA_PATH} was not found")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(governance_items)")}
    if "robots_advisory_ignored" not in columns:
        conn.execute("ALTER TABLE governance_items ADD COLUMN robots_advisory_ignored INTEGER DEFAULT 0")
    try:
        for statement in _MIGRATIONS:
            conn.execute(statement)
    except sqlite3.IntegrityError:
        # A database written by the old harvester can hold duplicate tamper rows; keep them,
        # skip the uniqueness index, and rely on the explicit existence check in _record_tamper.
        for statement in _MIGRATIONS:
            if "idx_tamper_once" not in statement:
                conn.execute(statement)
    conn.commit()


def audit_robots_txt(target_url: str) -> bool:
    parsed = urllib.parse.urlparse(target_url)
    parser = RobotFileParser()
    try:
        response = requests.get(f"{parsed.scheme}://{parsed.netloc}/robots.txt", headers=HEADERS, timeout=15)
        if response.status_code >= 400:
            return True
        parser.parse(response.text.splitlines())
        return parser.can_fetch(HEADERS["User-Agent"], target_url)
    except Exception:
        return True


def extract_true_text(pdf_bytes: bytes) -> str:
    """Best-effort text. Never raises and never returns None (FTS5 rows must not be NULL)."""
    text = ""
    try:
        import pdfplumber  # optional
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        try:
            from pypdf import PdfReader  # optional fallback
            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
        except Exception as exc:  # includes ImportError
            print(f"[!] Text extraction unavailable: {exc}")
    except Exception as exc:
        print(f"[!] Text extraction error: {exc}")
    if len(text.strip()) < 50 and shutil.which("tesseract") and shutil.which("pdftoppm"):
        try:
            import pytesseract
            from pdf2image import convert_from_bytes
            print("[*] Scanned PDF detected. Engaging OCR...")
            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=MAX_OCR_PAGES)
            text = "\n".join(pytesseract.image_to_string(image) for image in images)
        except Exception as exc:
            print(f"[!] OCR error: {exc}")
    return (text or "").strip()


class _Budget:
    def __init__(self, max_seconds: float, max_new: int, delay: float):
        self.deadline = time.monotonic() + max_seconds if max_seconds > 0 else None
        self.max_new, self.delay, self.new = max_new, max(delay, 0.0), 0
        self._last = 0.0

    def exhausted(self) -> bool:
        return (self.deadline is not None and time.monotonic() >= self.deadline) or (0 < self.max_new <= self.new)

    def wait(self) -> None:
        pause = self.delay - (time.monotonic() - self._last)
        if pause > 0:
            time.sleep(pause)
        self._last = time.monotonic()


def _get(session, url: str, budget: _Budget, timeout: int, limit: int | None = None):
    """GET with the politeness delay and an optional size cap. Returns (response, body)."""
    budget.wait()
    response = session.get(url, timeout=timeout, stream=limit is not None)
    if limit is None:
        return response, response.content
    chunks, size = [], 0
    for chunk in response.iter_content(65536):
        size += len(chunk)
        if size > limit:
            response.close()
            raise ValueError(f"document larger than {limit} bytes")
        chunks.append(chunk)
    return response, b"".join(chunks)


def _known(cur, url: str):
    row = cur.execute(
        "SELECT item_id, attachment_sha256 FROM governance_items WHERE source_url = ? ORDER BY item_id LIMIT 1",
        (url,)).fetchone()
    if row:
        return row
    return cur.execute("SELECT item_id, content_hash FROM document_aliases WHERE source_url = ?", (url,)).fetchone()


def _record_tamper(cur, item_id, url, old_hash, new_hash) -> bool:
    seen = cur.execute(
        "SELECT 1 FROM document_tamper_log WHERE source_url = ? AND new_hash = ?", (url, new_hash)).fetchone()
    if seen:
        return False
    cur.execute(
        "INSERT INTO document_tamper_log (item_id, source_url, original_hash, new_hash) VALUES (?, ?, ?, ?)",
        (item_id, url, old_hash, new_hash))
    return True


def _ingest_pdf(cur, pdf_url, file_bytes, out_dir, meta, stats, budget) -> None:
    sha512_hash = hashlib.sha512(file_bytes).hexdigest()
    existing = _known(cur, pdf_url)
    if existing:
        item_id, old_hash = existing
        old_hash = old_hash or ""
        compare_hash = hashlib.sha256(file_bytes).hexdigest() if len(old_hash) == 64 else sha512_hash
        if old_hash != compare_hash:
            if _record_tamper(cur, item_id, pdf_url, old_hash, sha512_hash):
                print(f"[!] CHANGED SINCE FIRST CAPTURE: {pdf_url}")
                Path(out_dir, f"TAMPERED_{sha512_hash[:12]}.pdf").write_bytes(file_bytes)
                stats["changed"] += 1
            else:
                stats["unchanged"] += 1  # the same change was already logged by an earlier run
        else:
            if len(old_hash) == 64:  # re-verified legacy SHA-256 row: upgrade in place
                try:
                    cur.execute("UPDATE governance_items SET attachment_sha256 = ? WHERE item_id = ?",
                                (sha512_hash, item_id))
                except sqlite3.IntegrityError:
                    pass  # another row already carries these bytes; leave the legacy hash
            stats["unchanged"] += 1
        return

    duplicate = cur.execute(
        "SELECT item_id FROM governance_items WHERE attachment_sha256 IN (?, ?) ORDER BY item_id LIMIT 1",
        (sha512_hash, hashlib.sha256(file_bytes).hexdigest())).fetchone()
    if duplicate:  # identical bytes already archived under another URL
        cur.execute("INSERT OR IGNORE INTO document_aliases (source_url, item_id, content_hash) VALUES (?, ?, ?)",
                    (pdf_url, duplicate[0], sha512_hash))
        stats["aliases"] += 1
        return

    file_name = f"{out_dir}/{sha512_hash[:12]}.pdf"
    Path(file_name).write_bytes(file_bytes)
    cur.execute(
        """INSERT INTO governance_items
               (meeting_date, committee_or_body, title, attachment_sha256, local_pdf_path, source_url,
                robots_advisory_ignored, extracted_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(attachment_sha256) DO NOTHING""",
        (meta["date"], meta["committee"], meta["title"], sha512_hash, file_name, pdf_url,
         meta["advisory_flag"], extract_true_text(file_bytes) or ""))
    if cur.rowcount:
        stats["new"] += 1
        budget.new += 1
    else:
        stats["aliases"] += 1


def harvest_and_ingest(target_url, prefix="Cheyenne_Historical", historical=False, *, committee="Cheyenne Records",
                       meeting_date=None, max_seconds=None, max_new=None, delay=None, respect_robots=False,
                       db_path=None) -> dict:
    """Harvest one Granicus publisher/agenda URL. Returns a summary dict; never raises for remote errors."""
    stats = {"root": target_url, "endpoints_listed": 0, "endpoints_crawled": 0, "endpoints_remaining": 0,
             "new": 0, "unchanged": 0, "aliases": 0, "changed": 0, "errors": 0, "known_not_refetched": 0,
             "budget_exhausted": False, "reachable": False, "robots_allowed": None}
    budget = _Budget(DEFAULT_MAX_SECONDS if max_seconds is None else max_seconds,
                     DEFAULT_MAX_NEW if max_new is None else max_new,
                     DEFAULT_DELAY if delay is None else delay)
    db_file = db_path or DB_PATH
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=60)
    try:
        ensure_schema(conn)
        cur = conn.cursor()
        session = requests.Session()
        session.headers.update(HEADERS)

        stats["robots_allowed"] = audit_robots_txt(target_url)
        if respect_robots and not stats["robots_allowed"]:
            print(f"[*] robots.txt disallows {target_url}; --respect-robots is set, nothing fetched.")
            return stats
        meta = {"date": meeting_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "committee": committee or "Cheyenne Records", "title": "Extracted Document",
                "advisory_flag": 0 if stats["robots_allowed"] else 1}

        try:
            response, body = _get(session, target_url, budget, 30)
            response.raise_for_status()
        except Exception as exc:
            print(f"[!] Target unreachable {target_url}: {exc}")
            return stats
        stats["reachable"] = True
        listing = body.decode(response.encoding or "utf-8", "replace")

        endpoints = [target_url]
        for match in AGENDA_LINK_RE.findall(listing):
            full_url = urllib.parse.urljoin(target_url, match.strip("'\" ").replace("&amp;", "&"))
            if full_url not in endpoints:
                endpoints.append(full_url)
        stats["endpoints_listed"] = len(endpoints)

        # Never-crawled agendas first (in listing order), then the least recently verified ones.
        crawled = dict(cur.execute("SELECT endpoint_url, last_crawled_at FROM harvest_progress WHERE root_url = ?",
                                   (target_url,)))
        # The listing itself is always scanned (it is already downloaded and may link new files).
        # Without --historical, known agendas and known documents are not fetched again.
        fresh = [url for url in endpoints if url not in crawled and url != target_url]
        stale = sorted((url for url in endpoints if url in crawled and url != target_url), key=lambda url: crawled[url])
        queue = [target_url] + fresh + (stale if historical else [])

        out_dir = f"artifacts/{prefix}_raw"
        os.makedirs(out_dir, exist_ok=True)

        for position, url in enumerate(queue):
            if budget.exhausted():
                stats["budget_exhausted"] = True
                stats["endpoints_remaining"] = len(queue) - position
                break
            seen, status = 0, "ok"
            try:
                if url == target_url:
                    page = listing
                else:
                    page_response, page_body = _get(session, url, budget, 25)
                    page_response.raise_for_status()
                    page = page_body.decode(page_response.encoding or "utf-8", "replace")
                for pdf_match in dict.fromkeys(PDF_LINK_RE.findall(page)):
                    if budget.exhausted():
                        status = "partial"
                        break
                    pdf_url = urllib.parse.urljoin(url, pdf_match.replace("&amp;", "&"))
                    if not historical and _known(cur, pdf_url):
                        stats["known_not_refetched"] += 1
                        continue
                    try:  # one bad attachment must not cost the rest of the agenda
                        pdf_response, content = _get(session, pdf_url, budget, 30, MAX_PDF_BYTES)
                        if "text/html" in pdf_response.headers.get("Content-Type", ""):
                            bypass = HTML_PDF_RE.search(content.decode("utf-8", "replace"))
                            if bypass:
                                pdf_url = urllib.parse.urljoin(pdf_url, bypass.group(1).replace("&amp;", "&"))
                                pdf_response, content = _get(session, pdf_url, budget, 30, MAX_PDF_BYTES)
                        if content[:4] == b"%PDF":
                            seen += 1
                            _ingest_pdf(cur, pdf_url, content, out_dir, meta, stats, budget)
                            conn.commit()
                    except Exception as exc:
                        conn.rollback()
                        stats["errors"] += 1
                        status = "partial"
                        print(f"[!] Document skipped {pdf_url}: {exc}")
            except Exception as exc:
                conn.rollback()
                stats["errors"] += 1
                status = "error"
                print(f"[!] Pipeline exception at {url}: {exc}")
            if status == "partial" and budget.exhausted():
                stats["budget_exhausted"] = True
                stats["endpoints_remaining"] = len(queue) - position
                break  # not recorded as crawled: the next run retries this agenda first
            cur.execute(
                """INSERT INTO harvest_progress (endpoint_url, root_url, status, documents_seen, last_crawled_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(endpoint_url) DO UPDATE SET root_url = excluded.root_url, status = excluded.status,
                       documents_seen = excluded.documents_seen, last_crawled_at = excluded.last_crawled_at""",
                (url, target_url, status, seen, datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
            stats["endpoints_crawled"] += 1
        return stats
    finally:
        conn.commit()
        conn.close()
        print("[summary] " + json.dumps(stats, sort_keys=True))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url")
    parser.add_argument("--prefix", default="Cheyenne_Historical")
    parser.add_argument("--historical", action="store_true",
                        help="after new agendas, re-verify previously crawled ones with the remaining budget")
    parser.add_argument("--committee", default="Cheyenne Records", help="body recorded on new rows")
    parser.add_argument("--date", default=None, help="meeting date (YYYY-MM-DD) recorded on new rows; default today (UTC)")
    parser.add_argument("--max-seconds", type=float, default=None, help=f"wall-clock budget (default {DEFAULT_MAX_SECONDS:.0f}; 0 = none)")
    parser.add_argument("--max-new", type=int, default=None, help=f"new documents per run (default {DEFAULT_MAX_NEW}; 0 = none)")
    parser.add_argument("--delay", type=float, default=None, help=f"seconds between requests (default {DEFAULT_DELAY})")
    parser.add_argument("--respect-robots", action="store_true", help="fetch nothing when robots.txt disallows the target")
    args = parser.parse_args(argv)
    if args.date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("--date must be YYYY-MM-DD")
    stats = harvest_and_ingest(args.url, args.prefix, args.historical, committee=args.committee,
                               meeting_date=args.date, max_seconds=args.max_seconds, max_new=args.max_new,
                               delay=args.delay, respect_robots=args.respect_robots)
    if stats["robots_allowed"] is False and args.respect_robots:
        return 0
    return 0 if stats["reachable"] else 1


if __name__ == "__main__":
    sys.exit(main())
