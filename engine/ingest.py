"""Module 1 — Ingestion: robots-aware, rate-limited, stdlib-only harvester.

Rules enforced here (see LEGAL.md): robots.txt + crawl-delay respected, custom
identifying User-Agent, per-host minimum delay, document-types only, hard caps.
Sources of type 'fixture' read a LOCAL directory — used by run.py selftest to
prove the pipeline offline.
"""
from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
import urllib.robotparser
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from . import db

_LAST_HIT: dict[str, float] = {}
_ROBOTS: dict[str, urllib.robotparser.RobotFileParser] = {}


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []  # (href, text)
        self._href = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._buf).strip()))
            self._href = None


class _TextStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(
            p.strip() for p in self.parts if p.strip()))


def html_to_text(html: str) -> str:
    p = _TextStripper()
    p.feed(html)
    return p.text()


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc


def _allowed(url: str, cfg: dict) -> bool:
    host = _host(url)
    if host not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        scheme = urllib.parse.urlsplit(url).scheme or "https"
        robots_url = f"{scheme}://{host}/robots.txt"
        try:  # fetch robots ourselves: robotparser.read() has no timeout and can hang
            req = urllib.request.Request(
                robots_url, headers={"User-Agent": cfg["identity"]["user_agent"]})
            with urllib.request.urlopen(req, timeout=15) as resp:
                rp.parse(resp.read().decode("utf-8", errors="replace").splitlines())
        except Exception:
            rp = urllib.robotparser.RobotFileParser()  # unreadable = permit, stay slow
        _ROBOTS[host] = rp
    ua = cfg["identity"]["user_agent"]
    try:
        return _ROBOTS[host].can_fetch(ua, url)
    except Exception:
        return True


def _wait(url: str, cfg: dict):
    host = _host(url)
    delay = float(cfg["identity"].get("delay_seconds_per_host", 3))
    rp = _ROBOTS.get(host)
    if rp is not None:
        cd = rp.crawl_delay(cfg["identity"]["user_agent"])
        if cd:
            delay = max(delay, float(cd))
    last = _LAST_HIT.get(host, 0.0)
    gap = time.monotonic() - last
    if gap < delay:
        time.sleep(delay - gap)
    _LAST_HIT[host] = time.monotonic()


def fetch(url: str, cfg: dict) -> bytes | None:
    if not _allowed(url, cfg):
        print(f"    [robots] disallowed: {url}")
        return None
    _wait(url, cfg)
    req = urllib.request.Request(url, headers={
        "User-Agent": cfg["identity"]["user_agent"],
        "Accept": "*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"    [fetch] {url}: {e}")
        return None


def _matches(href: str, text: str, patterns: list[str]) -> bool:
    target = f"{href} {text}".lower()
    return any(re.search(p.lower(), target) for p in patterns)


_TRACKER_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "fbclid", "gclid", "dimension", "w", "h", "v"}


def _normalize_url(url: str) -> str:
    """Stable identity for a document: drop fragments and cache-busting/tracker
    query params so the same civic file doesn't mint a new DB row every crawl."""
    parts = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
         if k.lower() not in _TRACKER_PARAMS]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path,
         urllib.parse.urlencode(q), ""))


def _is_htmlish(url: str, raw: bytes) -> bool:
    if url.lower().split("?")[0].endswith((".html", ".htm", "/")):
        return True
    head = raw[:512].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def _hashable_bytes(url: str, raw: bytes) -> bytes:
    """Fingerprint rule: binary files hash raw bytes; HTML pages hash the
    normalized extracted TEXT (whitespace collapsed, boilerplate-safe), since
    CMS pages embed rotating nonces that are not content changes."""
    if _is_htmlish(url, raw):
        text = html_to_text(raw.decode("utf-8", errors="replace"))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text).strip()
        return text.encode("utf-8")
    return raw


def _ingest_one(conn, source: str, url: str, title: str, raw: bytes,
                published_at: str = "") -> str:
    url = _normalize_url(url)
    sha = hashlib.sha256(_hashable_bytes(url, raw)).hexdigest()
    name = re.sub(r"[^A-Za-z0-9._-]", "_",
                  Path(urllib.parse.urlsplit(url).path).name or "index.html")
    local = str(db.SNAP_DIR / f"{sha[:12]}_{name[-80:]}")
    Path(local).write_bytes(raw)
    doc = db.get_document_by_url(conn, url)
    if doc is None:
        doc_id = db.insert_document(conn, source, url, title or url, local,
                                    sha, len(raw), published_at)
        db.enqueue_job(conn, "extract", {"document_id": doc_id})
        return f"NEW doc #{doc_id}: {title or url}"
    if doc["sha256"] != sha:
        seq = db.bump_hash(conn, doc["id"], sha, local, len(raw))
        db.enqueue_job(conn, "diff", {"document_id": doc["id"], "seq": seq})
        db.enqueue_job(conn, "extract", {"document_id": doc["id"]})
        return f"CHANGED doc #{doc['id']} (silent-edit candidate, seq {seq})"
    db.touch_checked(conn, doc["id"])
    return f"unchanged doc #{doc['id']}"


def crawl_html_site(conn, source: dict, cfg: dict):
    raw = fetch(source["url"], cfg)
    if raw is None:
        return 0
    html = raw.decode("utf-8", errors="replace")
    # The poll page itself is transient navigation — we index the child
    # documents it links to, not the nav page.
    parser = _LinkParser()
    parser.feed(html)
    pats = cfg.get("document_link_patterns", [])
    cap = int(cfg["identity"].get("max_docs_per_source_per_run", 40))
    hits = 0
    seen: set[str] = set()
    base = _normalize_url(source["url"])
    for href, text in parser.links:
        if hits >= cap:
            break
        full = _normalize_url(urllib.parse.urljoin(source["url"], href))
        # skip dupes in-page and self-links (language pickers, #main-content, etc.)
        if full in seen or full == base or not _matches(full, text, pats):
            continue
        seen.add(full)
        body = fetch(full, cfg)
        if body is None:
            continue
        result = _ingest_one(conn, source["name"], full, text, body)
        print(f"    {result}")
        hits += 1
    return hits


def crawl_rss_feed(conn, source: dict, cfg: dict):
    raw = fetch(source["url"], cfg)
    if raw is None:
        return 0
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as e:
        print(f"    [rss] parse error {source['url']}: {e}")
        return 0
    hits = 0
    cap = int(cfg["identity"].get("max_docs_per_source_per_run", 40))
    for item in root.iter("item"):
        if hits >= cap:
            break
        link = item.findtext("link") or ""
        title = item.findtext("title") or ""
        pub = item.findtext("pubDate") or ""
        if not link:
            continue
        body = fetch(link, cfg)
        if body is None:
            continue
        result = _ingest_one(conn, source["name"], link, title, body, pub)
        print(f"    {result}")
        hits += 1
    return hits


def crawl_fixture(conn, source_name: str, fixture_dir: str) -> int:
    """Offline loader used by run.py selftest. Treats each file in the
    directory as a published document at fixture://<name>."""
    hits = 0
    for fp in sorted(Path(fixture_dir).iterdir()):
        if fp.suffix.lower() not in (".html", ".htm", ".txt"):
            continue
        url = f"fixture://{source_name}/{fp.name}"
        raw = fp.read_bytes()
        result = _ingest_one(conn, source_name, url, fp.stem, raw)
        print(f"    {result}")
        hits += 1
    return hits


def crawl_all(conn) -> int:
    cfg = db.load_config()
    db.sync_sources(conn)
    total = 0
    for s in cfg.get("sources", []):
        if not s.get("enabled"):
            print(f"[skip] {s['name']} (disabled — see notes)")
            continue
        print(f"[crawl] {s['name']} -> {s['url']}")
        if s.get("type") == "rss":
            total += crawl_rss_feed(conn, s, cfg)
        else:
            total += crawl_html_site(conn, s, cfg)
    return total
