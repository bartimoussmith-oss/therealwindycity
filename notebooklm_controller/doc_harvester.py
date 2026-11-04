#!/usr/bin/env python3
"""
doc_harvester.py — Fetch the Granicus agenda page for each meeting and extract
every linked supporting document (staff reports, packet pages, MetaViewer
attachments, DocumentViewer PDFs).

Granicus renders agendas/minutes/packets as HTML pages, not PDFs, so the
supporting-document links are only discoverable by fetching the AgendaViewer
page and scraping its <a href="MetaViewer.php?meta_id=..."> and
DocumentViewer/.pdf links.

Each returned doc spec:
  {
    "url": "https://cheyenne.granicus.com/MetaViewer.php?meta_id=...",
    "kind": "metaviewer" | "pdf" | "agenda" | "minutes",
    "label": "<link text>",
    "local": "/abs/path/to/...html",   # saved copy, or None if fetch failed
    "fetched": True/False,
  }

Politeness: custom identifying User-Agent, >=3s between hits per host (the
repo's existing crawl-delay contract), stdlib-only urllib. Fails gracefully
when the host is unreachable (this sandbox) — callers should treat missing
docs as "to be fetched from Granicus when network allows".
"""
from __future__ import annotations

import re
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, unquote
from pathlib import Path
from typing import Optional

BASE = "https://cheyenne.granicus.com"
UA = {"User-Agent": "therealwindycity-notebooklm-controller/1.0 (+supporting-docs-harvest)"}
POLITENESS = 3.0  # seconds between hits to the same host
_LAST_HIT: dict[str, float] = {}

LINK_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
METAVIEWER_RE = re.compile(r"MetaViewer\.php", re.I)
DOCVIEWER_RE = re.compile(r"DocumentViewer\.php", re.I)
PDF_RE = re.compile(r"\.pdf\b", re.I)


def _clean(text: str) -> str:
    text = TAG_RE.sub("", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip()


def _polite_get(url: str, timeout: int = 20) -> Optional[urllib.request.addinfourl]:
    """GET with per-host politeness delay. Returns response or None on failure."""
    host = urlparse(url).hostname or ""
    now = time.monotonic()
    last = _LAST_HIT.get(host, 0)
    delay = max(0, POLITENESS - (now - last))
    if delay:
        time.sleep(delay)
    try:
        req = urllib.request.Request(url, headers=UA)
        resp = urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
        print(f"[doc_harvester] fetch failed {url}: {e}")
        return None
    _LAST_HIT[host] = time.monotonic()
    return resp


def _fetch_text(url: str) -> Optional[str]:
    resp = _polite_get(url)
    if resp is None:
        return None
    try:
        data = resp.read()
    except Exception as e:
        print(f"[doc_harvester] read failed {url}: {e}")
        return None
    finally:
        resp.close()
    # Granicus serves UTF-8 HTML; fall back to latin-1 if needed.
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _save(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _AgendaLinkParser(HTMLParser):
    """Collect (href, label) pairs from an agenda page."""
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._in_a = False
        self._href: Optional[str] = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in_a = True
            self._href = dict(attrs).get("href")
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            if self._href:
                self.links.append((self._href, "".join(self._buf)))
            self._href = None
            self._buf = []

    def handle_data(self, data):
        if self._in_a:
            self._buf.append(data)


def harvest_supporting_docs(meeting: dict, out_dir: Path) -> list[dict]:
    """
    Fetch the meeting's agenda page and return every linked supporting document.

    Also saves a local copy of the agenda page (and any successfully fetched
    MetaViewer/PDF pages) under out_dir/sources/ so they become part of the
    studio artifact package.
    """
    docs: list[dict] = []
    agenda_url = meeting.get("agenda_url")
    clip_id = meeting.get("clip_id")
    date = meeting.get("date", "")

    if not agenda_url:
        return docs

    sources_dir = out_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    # --- fetch the agenda page itself ---
    agenda_html = _fetch_text(agenda_url)
    if agenda_html is None:
        print(f"[doc_harvester] could not fetch agenda for clip {clip_id}: {agenda_url}")
        return docs

    _save(sources_dir / f"{date}_clip{clip_id}_agenda.html", agenda_html)
    docs.append({
        "url": agenda_url,
        "kind": "agenda",
        "label": "Meeting agenda (Granicus AgendaViewer)",
        "local": str(sources_dir / f"{date}_clip{clip_id}_agenda.html"),
        "fetched": True,
    })

    # --- extract every link on the agenda page ---
    parser = _AgendaLinkParser()
    parser.feed(agenda_html)
    seen: set[str] = {agenda_url}
    meta_count = 0
    pdf_count = 0

    for href, raw_label in parser.links:
        href = href.replace("&amp;", "&")
        abs_url = urljoin(agenda_url, href)
        label = _clean(raw_label) or Path(urlparse(abs_url).path).name or abs_url

        # skip duplicates and the page itself
        if abs_url in seen:
            continue
        seen.add(abs_url)

        is_metaviewer = bool(METAVIEWER_RE.search(abs_url))
        is_docviewer = bool(DOCVIEWER_RE.search(abs_url))
        is_pdf = bool(PDF_RE.search(abs_url))

        if not (is_metaviewer or is_docviewer or is_pdf):
            continue  # internal / navigation links only

        if is_metaviewer:
            kind = "metaviewer"
            meta_count += 1
            local_name = f"{date}_clip{clip_id}_meta{meta_count:02d}.html"
        elif is_docviewer or is_pdf:
            kind = "pdf"
            pdf_count += 1
            local_name = f"{date}_clip{clip_id}_doc{pdf_count:02d}.pdf"
        else:
            continue

        # try to fetch a local copy (best effort; PDFs may be large)
        local_path = None
        fetched = False
        try:
            resp = _polite_get(abs_url)
            if resp is not None:
                data = resp.read()
                ctype = (resp.headers.get("content-type") or "").lower()
                dest = sources_dir / local_name
                if "text/html" in ctype or not data.lower().startswith(b"%PDF"):
                    dest.write_text(_clean(agenda_html) if False else data.decode("utf-8", errors="replace"), encoding="utf-8")
                else:
                    dest.write_bytes(data)
                local_path = str(dest)
                fetched = True
                resp.close()
        except Exception as e:
            print(f"[doc_harvester] doc fetch failed {abs_url}: {e}")

        docs.append({
            "url": abs_url,
            "kind": kind,
            "label": label,
            "local": local_path,
            "fetched": fetched,
        })

    print(f"[doc_harvester] clip {clip_id}: agenda + {meta_count} metaviewer + {pdf_count} pdf "
          f"= {len(docs)} document(s)")
    return docs


def harvest_for_meeting(meeting: dict, artifacts_root: Path) -> list[dict]:
    """Convenience: locate the artifact dir and harvest supporting docs into it."""
    date = meeting.get("date", "")
    body = meeting.get("body", "")
    clip_id = meeting.get("clip_id", "")
    art_dir = artifacts_root / f"{date}-{body}-{clip_id}"
    return harvest_supporting_docs(meeting, art_dir)
