"""Rate-limited ingestion with Chrome TLS transport and bounded redirects.

Robots policy checks are not performed by this collector. Fixture ingestion,
redaction, normalized document identity and per-source caps remain supported.
"""
from __future__ import annotations
import hashlib
import re
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree
from . import db, redact

_LAST_HIT: dict[str, float] = {}

class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._buf = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self._href = dict(attrs).get('href')
            self._buf = []
    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self._href is not None:
            self.links.append((self._href, ' '.join(self._buf).strip()))
            self._href = None

class _TextStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript') and self.skip:
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
    def text(self):
        return re.sub(r'\n{3,}', '\n\n', '\n'.join(p.strip() for p in self.parts if p.strip()))

def html_to_text(html: str) -> str:
    parser = _TextStripper()
    parser.feed(html)
    return parser.text()

def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc

def _wait(url: str, cfg: dict):
    host = _host(url)
    delay = max(3.0, float(cfg['identity'].get('delay_seconds_per_host', 3)))
    gap = time.monotonic() - _LAST_HIT.get(host, 0.0)
    if gap < delay:
        time.sleep(delay - gap)
    _LAST_HIT[host] = time.monotonic()

def fetch(url: str, cfg: dict) -> bytes | None:
    from curl_cffi import requests
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        return None
    strict = cfg['identity'].get('strict_web')
    if strict and parsed.scheme != 'https':
        return None
    _wait(url, cfg)
    body = bytearray()
    def receive(chunk):
        if len(body) + len(chunk) > 20_000_000:
            raise ValueError('Response exceeds 20 MB limit')
        body.extend(chunk)
    try:
        response = requests.get(
            url, impersonate='chrome', allow_redirects=True, max_redirects=5,
            timeout=30, content_callback=receive,
            headers={'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9'},
            curl_options={84: 2 if strict else 3, 85: 2 if strict else 3})
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f'HTTP {response.status_code} at {response.url}')
        print(f'    [transport] {url} -> {response.url}: HTTP {response.status_code}')
        return bytes(body)
    except Exception as exc:
        print(f'    [fetch] {url}: {exc}')
        return None

def _matches(href: str, text: str, patterns: list[str]) -> bool:
    target = f'{href} {text}'.lower()
    return any(re.search(p.lower(), target) for p in patterns)

_TRACKER_PARAMS = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid', 'dimension', 'w', 'h', 'v'}

def _normalize_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKER_PARAMS]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ''))

def _is_htmlish(url: str, raw: bytes) -> bool:
    if url.lower().split('?')[0].endswith(('.html', '.htm', '/')):
        return True
    head = raw[:512].lstrip().lower()
    return head.startswith(b'<!doctype') or head.startswith(b'<html')

def _hashable_bytes(url: str, raw: bytes) -> bytes:
    if _is_htmlish(url, raw):
        text = html_to_text(raw.decode('utf-8', errors='replace'))
        text = re.sub(r'[ \t]+', ' ', text)
        return re.sub(r'\n\s*\n+', '\n', text).strip().encode('utf-8')
    return raw

def _ingest_one(conn, source: str, url: str, title: str, raw: bytes, published_at: str = '') -> str:
    url = _normalize_url(url)
    sealed_names = []
    if redact.is_arrest_document(url=url, title=title):
        try:
            raw, sealed_names = redact.redact_bytes(raw, url=url, title=title)
        except redact.RedactionError as exc:
            return f'REFUSED (redaction failed, names would leak): {exc}'
    sha = hashlib.sha256(_hashable_bytes(url, raw)).hexdigest()
    name = re.sub(r'[^A-Za-z0-9._-]', '_', Path(urllib.parse.urlsplit(url).path).name or 'index.html')
    local = str(db.SNAP_DIR / f'{sha[:12]}_{name[-80:]}')
    Path(local).write_bytes(raw)
    if sealed_names:
        redact.seal_names(sealed_names, url=url, title=title, source=source, capture=Path(local).name)
    doc = db.get_document_by_url(conn, url)
    if doc is None:
        doc_id = db.insert_document(conn, source, url, title or url, local, sha, len(raw), published_at)
        db.enqueue_job(conn, 'extract', {'document_id': doc_id})
        return f'NEW doc #{doc_id}: {title or url}'
    if doc['sha256'] != sha:
        seq = db.bump_hash(conn, doc['id'], sha, local, len(raw))
        db.enqueue_job(conn, 'diff', {'document_id': doc['id'], 'seq': seq})
        db.enqueue_job(conn, 'extract', {'document_id': doc['id']})
        return f"CHANGED doc #{doc['id']} (silent-edit candidate, seq {seq})"
    db.touch_checked(conn, doc['id'])
    return f"unchanged doc #{doc['id']}"

def crawl_html_site(conn, source: dict, cfg: dict):
    raw = fetch(source['url'], cfg)
    if raw is None:
        return 0
    parser = _LinkParser()
    parser.feed(raw.decode('utf-8', errors='replace'))
    patterns = cfg.get('document_link_patterns', [])
    cap = int(cfg['identity'].get('max_docs_per_source_per_run', 40))
    hits = 0
    seen = set()
    base = _normalize_url(source['url'])
    for href, text in parser.links:
        if hits >= cap:
            break
        full = _normalize_url(urllib.parse.urljoin(source['url'], href))
        if full in seen or full == base or not _matches(full, text, patterns):
            continue
        seen.add(full)
        body = fetch(full, cfg)
        if body is None:
            continue
        print('    ' + _ingest_one(conn, source['name'], full, text, body))
        hits += 1
    return hits

def crawl_rss_feed(conn, source: dict, cfg: dict):
    raw = fetch(source['url'], cfg)
    if raw is None:
        return 0
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        print(f"    [rss] parse error {source['url']}: {exc}")
        return 0
    hits = 0
    cap = int(cfg['identity'].get('max_docs_per_source_per_run', 40))
    for item in root.iter('item'):
        if hits >= cap:
            break
        link = item.findtext('link') or ''
        if not link:
            continue
        body = fetch(link, cfg)
        if body is None:
            continue
        title = item.findtext('title') or ''
        published = item.findtext('pubDate') or ''
        print('    ' + _ingest_one(conn, source['name'], link, title, body, published))
        hits += 1
    return hits

def crawl_fixture(conn, source_name: str, fixture_dir: str) -> int:
    hits = 0
    for path in sorted(Path(fixture_dir).iterdir()):
        if path.suffix.lower() not in ('.html', '.htm', '.txt'):
            continue
        print('    ' + _ingest_one(conn, source_name, f'fixture://{source_name}/{path.name}', path.stem, path.read_bytes()))
        hits += 1
    return hits

def crawl_all(conn) -> int:
    cfg = db.load_config()
    db.sync_sources(conn)
    total = 0
    for source in cfg.get('sources', []):
        if not source.get('enabled'):
            print(f"[skip] {source['name']} (disabled — see notes)")
            continue
        print(f"[crawl] {source['name']} -> {source['url']}")
        try:
            if source.get('type') == 'rss':
                total += crawl_rss_feed(conn, source, cfg)
            else:
                total += crawl_html_site(conn, source, cfg)
        except Exception as exc:
            print(f"[source failed] {source['name']}: {exc}")
    return total
